"""Agent coordination and conflict prevention for June.

Provides coordination mechanisms to prevent conflicts between agents, coordinate
access to shared resources, and handle agent failures gracefully.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from june_agent_state.models import AgentStatus
from june_agent_state.registry import AgentRegistry
from june_agent_state.storage import AgentStateStorage

logger = logging.getLogger(__name__)


class ResourceLock:
    """Represents a lock on a shared resource."""

    def __init__(
        self,
        resource_id: str,
        agent_id: str,
        lock_type: str = "exclusive",
        expires_at: Optional[datetime] = None,
    ):
        """
        Initialize resource lock.

        Args:
            resource_id: Unique resource identifier
            agent_id: Agent holding the lock
            lock_type: Lock type ('exclusive' or 'shared')
            expires_at: Optional expiration time
        """
        self.resource_id = resource_id
        self.agent_id = agent_id
        self.lock_type = lock_type
        self.created_at = datetime.utcnow()
        self.expires_at = expires_at
        self._released = False

    def is_expired(self) -> bool:
        """Check if lock has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() >= self.expires_at

    def is_valid(self) -> bool:
        """Check if lock is valid (not expired or released)."""
        return not self._released and not self.is_expired()

    def release(self):
        """Mark lock as released."""
        self._released = True


class AgentCoordination:
    """Coordinates agent activities to prevent conflicts and manage shared resources."""

    def __init__(
        self,
        registry: AgentRegistry,
        storage: AgentStateStorage,
        default_lock_timeout_seconds: int = 3600,  # 1 hour
        load_locks_from_db: bool = True,
    ):
        """
        Initialize agent coordination.

        Args:
            registry: AgentRegistry instance
            storage: AgentStateStorage instance
            default_lock_timeout_seconds: Default timeout for resource locks
            load_locks_from_db: If True, load existing locks from database on first use
        """
        self.registry = registry
        self.storage = storage
        self.default_lock_timeout = default_lock_timeout_seconds
        self._resource_locks: Dict[str, List[ResourceLock]] = {}
        self._lock_mutex = asyncio.Lock()
        self._locks_loaded = not load_locks_from_db  # True if already loaded or disabled

    async def acquire_resource_lock(
        self,
        resource_id: str,
        agent_id: str,
        lock_type: str = "exclusive",
        timeout_seconds: Optional[int] = None,
        wait: bool = True,
        max_wait_seconds: int = 60,
    ) -> bool:
        """
        Acquire a lock on a shared resource.

        Args:
            resource_id: Resource to lock
            agent_id: Agent requesting the lock
            lock_type: 'exclusive' or 'shared'
            timeout_seconds: Lock timeout (uses default if None)
            wait: If True, wait for lock to become available
            max_wait_seconds: Maximum time to wait for lock

        Returns:
            True if lock acquired, False otherwise
        """
        async with self._lock_mutex:
            # Verify agent exists and is active
            agent_state = await self.registry.get_agent(agent_id)
            if agent_state is None:
                logger.warning(f"Agent {agent_id} not found, cannot acquire lock")
                return False

            if agent_state.status not in (AgentStatus.ACTIVE, AgentStatus.INIT):
                logger.warning(
                    f"Agent {agent_id} is not active (status: {agent_state.status}), "
                    f"cannot acquire lock"
                )
                return False

            # Load locks from DB if needed
            if not self._locks_loaded:
                await self._load_locks_from_db(resource_id)
            
            # Clean up expired locks
            await self._cleanup_expired_locks(resource_id)

            # Check if lock can be acquired
            existing_locks = self._resource_locks.get(resource_id, [])

            # For exclusive locks, no other locks allowed
            if lock_type == "exclusive":
                valid_locks = [l for l in existing_locks if l.is_valid()]
                if valid_locks:
                    if not wait:
                        logger.debug(
                            f"Resource {resource_id} is locked, cannot acquire exclusive lock"
                        )
                        return False

                    # Wait for lock to become available
                    wait_until = datetime.utcnow() + timedelta(seconds=max_wait_seconds)
                    while datetime.utcnow() < wait_until:
                        await asyncio.sleep(0.5)
                        await self._cleanup_expired_locks(resource_id)
                        valid_locks = [
                            l for l in self._resource_locks.get(resource_id, []) if l.is_valid()
                        ]
                        if not valid_locks:
                            break

                    # Check again after waiting
                    valid_locks = [
                        l for l in self._resource_locks.get(resource_id, []) if l.is_valid()
                    ]
                    if valid_locks:
                        logger.warning(
                            f"Could not acquire lock on {resource_id} after waiting"
                        )
                        return False

            # For shared locks, exclusive locks block, other shared locks allowed
            elif lock_type == "shared":
                exclusive_locks = [
                    l for l in existing_locks if l.is_valid() and l.lock_type == "exclusive"
                ]
                if exclusive_locks:
                    if not wait:
                        return False

                    # Wait for exclusive locks to be released
                    wait_until = datetime.utcnow() + timedelta(seconds=max_wait_seconds)
                    while datetime.utcnow() < wait_until:
                        await asyncio.sleep(0.5)
                        await self._cleanup_expired_locks(resource_id)
                        exclusive_locks = [
                            l
                            for l in self._resource_locks.get(resource_id, [])
                            if l.is_valid() and l.lock_type == "exclusive"
                        ]
                        if not exclusive_locks:
                            break

                    exclusive_locks = [
                        l
                        for l in self._resource_locks.get(resource_id, [])
                        if l.is_valid() and l.lock_type == "exclusive"
                    ]
                    if exclusive_locks:
                        logger.warning(
                            f"Could not acquire shared lock on {resource_id} - "
                            f"exclusive lock exists"
                        )
                        return False

            # Acquire the lock
            timeout = timeout_seconds or self.default_lock_timeout
            expires_at = datetime.utcnow() + timedelta(seconds=timeout)
            
            # Persist to database
            try:
                await self.storage.save_resource_lock(
                    resource_id, agent_id, lock_type, expires_at
                )
            except Exception as e:
                logger.error(
                    f"Failed to persist lock to database for resource {resource_id}: {e}",
                    exc_info=True,
                )
                # Continue with in-memory lock even if DB fails
                # This allows coordination to work even if DB is temporarily unavailable
            
            # Create in-memory lock object
            lock = ResourceLock(
                resource_id=resource_id,
                agent_id=agent_id,
                lock_type=lock_type,
                expires_at=expires_at,
            )

            if resource_id not in self._resource_locks:
                self._resource_locks[resource_id] = []
            self._resource_locks[resource_id].append(lock)

            logger.info(
                f"Agent {agent_id} acquired {lock_type} lock on resource {resource_id} "
                f"(expires: {expires_at.isoformat()})"
            )
            return True

    async def release_resource_lock(
        self, resource_id: str, agent_id: str
    ) -> bool:
        """
        Release a lock on a shared resource.

        Args:
            resource_id: Resource to unlock
            agent_id: Agent releasing the lock

        Returns:
            True if lock was released, False if not found
        """
        async with self._lock_mutex:
            # Release in database first
            db_released = False
            try:
                db_released = await self.storage.release_resource_lock(resource_id, agent_id)
            except Exception as e:
                logger.error(
                    f"Failed to release lock in database for resource {resource_id}: {e}",
                    exc_info=True,
                )
            
            # Release in-memory lock
            locks = self._resource_locks.get(resource_id, [])
            mem_released = False
            for lock in locks:
                if lock.agent_id == agent_id and lock.is_valid():
                    lock.release()
                    mem_released = True

            if db_released or mem_released:
                logger.info(
                    f"Agent {agent_id} released lock on resource {resource_id}"
                )
                return True

            logger.warning(
                f"Agent {agent_id} attempted to release non-existent lock on {resource_id}"
            )
            return False

    async def release_all_agent_locks(self, agent_id: str) -> int:
        """
        Release all locks held by an agent (e.g., on agent failure).

        Args:
            agent_id: Agent ID to release locks for

        Returns:
            Number of locks released
        """
        async with self._lock_mutex:
            # Release from database first
            db_count = 0
            try:
                db_count = await self.storage.release_all_agent_locks(agent_id)
            except Exception as e:
                logger.error(
                    f"Failed to release all locks in database for agent {agent_id}: {e}",
                    exc_info=True,
                )
            
            # Release from in-memory cache
            mem_count = 0
            for resource_id, locks in list(self._resource_locks.items()):
                for lock in locks:
                    if lock.agent_id == agent_id and lock.is_valid():
                        lock.release()
                        mem_count += 1

            released_count = max(db_count, mem_count)  # Use max to handle partial failures
            if released_count > 0:
                logger.info(f"Released {released_count} locks for agent {agent_id}")
            return released_count

    async def check_resource_available(
        self, resource_id: str, lock_type: str = "exclusive"
    ) -> bool:
        """
        Check if a resource is available for locking.

        Args:
            resource_id: Resource to check
            lock_type: Type of lock to check for

        Returns:
            True if resource is available, False otherwise
        """
        async with self._lock_mutex:
            # Load locks from DB if needed
            if not self._locks_loaded:
                await self._load_locks_from_db(resource_id)
            
            await self._cleanup_expired_locks(resource_id)
            existing_locks = self._resource_locks.get(resource_id, [])
            valid_locks = [l for l in existing_locks if l.is_valid()]

            if lock_type == "exclusive":
                return len(valid_locks) == 0
            elif lock_type == "shared":
                # Shared locks can coexist, but exclusive locks block
                exclusive_locks = [l for l in valid_locks if l.lock_type == "exclusive"]
                return len(exclusive_locks) == 0

            return False

    async def _load_locks_from_db(self, resource_id: Optional[str] = None):
        """Load locks from database into in-memory cache."""
        # Double-check pattern to avoid race conditions
        if self._locks_loaded:
            return
        
        async with self._lock_mutex:
            # Check again after acquiring lock
            if self._locks_loaded:
                return
            
            try:
                db_locks = await self.storage.get_active_resource_locks(resource_id)
                for lock_data in db_locks:
                    rid = lock_data["resource_id"]
                    if rid not in self._resource_locks:
                        self._resource_locks[rid] = []
                    
                    # Check if lock already exists in cache
                    existing = [
                        l for l in self._resource_locks[rid]
                        if l.agent_id == lock_data["agent_id"]
                        and l.lock_type == lock_data["lock_type"]
                        and not l.is_expired()
                    ]
                    if not existing:
                        lock = ResourceLock(
                            resource_id=rid,
                            agent_id=lock_data["agent_id"],
                            lock_type=lock_data["lock_type"],
                            expires_at=lock_data["expires_at"],
                        )
                        self._resource_locks[rid].append(lock)
                
                self._locks_loaded = True
            except Exception as e:
                logger.error(f"Failed to load locks from database: {e}", exc_info=True)
                # Continue without DB locks, but mark as loaded to avoid retrying
                self._locks_loaded = True

    async def get_resource_locks(self, resource_id: str) -> List[ResourceLock]:
        """
        Get all valid locks on a resource.

        Args:
            resource_id: Resource to query

        Returns:
            List of valid ResourceLock instances
        """
        async with self._lock_mutex:
            # Load locks from DB if needed
            if not self._locks_loaded:
                await self._load_locks_from_db(resource_id)
            
            await self._cleanup_expired_locks(resource_id)
            locks = self._resource_locks.get(resource_id, [])
            return [l for l in locks if l.is_valid()]

    async def coordinate_task_assignment(
        self, task_id: str, agent_id: str, required_resources: List[str]
    ) -> bool:
        """
        Coordinate task assignment by acquiring all required resources.

        Args:
            task_id: Task ID
            agent_id: Agent requesting task assignment
            required_resources: List of resource IDs required for the task

        Returns:
            True if all resources acquired, False otherwise
        """
        acquired_resources = []
        try:
            for resource_id in required_resources:
                if not await self.acquire_resource_lock(
                    resource_id, agent_id, lock_type="exclusive", wait=False
                ):
                    # Release any already-acquired resources
                    for acquired in acquired_resources:
                        await self.release_resource_lock(acquired, agent_id)
                    logger.warning(
                        f"Could not acquire all resources for task {task_id}, "
                        f"failed on {resource_id}"
                    )
                    return False
                acquired_resources.append(resource_id)

            logger.info(
                f"Successfully coordinated task {task_id} assignment for agent {agent_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"Error coordinating task {task_id} assignment: {e}", exc_info=True
            )
            # Release any acquired resources on error
            for resource_id in acquired_resources:
                await self.release_resource_lock(resource_id, agent_id)
            return False

    async def handle_agent_failure(
        self, agent_id: str, error_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Handle agent failure by cleaning up locks and updating state.

        Args:
            agent_id: Agent that failed
            error_info: Optional error information

        Returns:
            True if handled successfully, False otherwise
        """
        try:
            # Release all locks held by the agent
            locks_released = await self.release_all_agent_locks(agent_id)

            # Update agent status to ERROR
            await self.registry.update_agent_status(agent_id, AgentStatus.ERROR)

            # Record failure in execution history
            if error_info:
                from june_agent_state.models import AgentExecutionRecord, AgentExecutionOutcome

                record = AgentExecutionRecord(
                    agent_id=agent_id,
                    task_id=None,
                    action_type="agent_failure",
                    outcome=AgentExecutionOutcome.FAILURE,
                    duration_ms=None,
                    metadata=error_info,
                    created_at=datetime.utcnow(),
                )
                await self.storage.save_execution_record(record)

            logger.warning(
                f"Handled agent failure for {agent_id}: released {locks_released} locks"
            )
            return True
        except Exception as e:
            logger.error(f"Error handling agent failure for {agent_id}: {e}", exc_info=True)
            return False

    async def share_state_between_agents(
        self,
        source_agent_id: str,
        target_agent_id: str,
        state_data: Dict[str, Any],
        knowledge_key: Optional[str] = None,
    ) -> bool:
        """
        Share state/knowledge between agents via the knowledge cache.

        Args:
            source_agent_id: Source agent ID
            target_agent_id: Target agent ID
            state_data: State data to share
            knowledge_key: Optional key for the knowledge cache

        Returns:
            True if shared successfully, False otherwise
        """
        try:
            # Store in knowledge cache for target agent
            key = knowledge_key or f"shared_from_{source_agent_id}"
            await self.storage.save_knowledge(
                agent_id=target_agent_id,
                knowledge_key=key,
                knowledge_value=state_data,
            )

            logger.info(
                f"Shared state from {source_agent_id} to {target_agent_id} "
                f"(key: {key})"
            )
            return True
        except Exception as e:
            logger.error(
                f"Error sharing state from {source_agent_id} to {target_agent_id}: {e}",
                exc_info=True,
            )
            return False

    async def _cleanup_expired_locks(self, resource_id: Optional[str] = None):
        """
        Clean up expired locks for a resource or all resources.

        Args:
            resource_id: Specific resource to clean (None for all)
        """
        # Clean up in database
        try:
            await self.storage.cleanup_expired_locks()
        except Exception as e:
            logger.error(f"Failed to cleanup expired locks in database: {e}", exc_info=True)
        
        # Clean up in-memory cache
        resources_to_check = (
            [resource_id] if resource_id else list(self._resource_locks.keys())
        )

        for rid in resources_to_check:
            if rid not in self._resource_locks:
                continue

            locks = self._resource_locks[rid]
            valid_locks = [l for l in locks if l.is_valid()]

            # Remove invalid locks
            if len(valid_locks) != len(locks):
                self._resource_locks[rid] = valid_locks
                expired_count = len(locks) - len(valid_locks)
                if expired_count > 0:
                    logger.debug(
                        f"Cleaned up {expired_count} expired lock(s) for resource {rid}"
                    )

    async def check_task_assignment(self, task_id: str) -> Optional[str]:
        """
        Check which agent is assigned to a task.

        Args:
            task_id: Task ID to check

        Returns:
            Agent ID if task is assigned, None otherwise
        """
        try:
            # Query all agents to find one with this task
            all_agents = await self.registry.list_agents(
                filters={"has_task": True}
            )
            
            for agent in all_agents:
                if agent.current_task_id == task_id:
                    return agent.agent_id
            
            return None
        except Exception as e:
            logger.error(
                f"Failed to check task assignment for task {task_id}: {e}",
                exc_info=True,
            )
            return None

    async def assign_task_to_agent(self, task_id: str, agent_id: str) -> bool:
        """
        Assign a task to an agent with conflict prevention.

        Args:
            task_id: Task ID to assign
            agent_id: Agent ID to assign task to

        Returns:
            True if assignment successful, False if conflict detected or agent not found
        """
        try:
            # Check if task is already assigned to another agent
            assigned_agent = await self.check_task_assignment(task_id)
            if assigned_agent is not None and assigned_agent != agent_id:
                logger.warning(
                    f"Task {task_id} is already assigned to agent {assigned_agent}, "
                    f"cannot assign to {agent_id}"
                )
                return False
            
            # Verify agent exists and is active
            agent_state = await self.registry.get_agent(agent_id)
            if agent_state is None:
                logger.warning(f"Agent {agent_id} not found, cannot assign task")
                return False
            
            if agent_state.status not in (AgentStatus.ACTIVE, AgentStatus.INIT):
                logger.warning(
                    f"Agent {agent_id} is not active (status: {agent_state.status}), "
                    f"cannot assign task"
                )
                return False
            
            # Assign task by updating agent state
            await self.storage.update_state(agent_id, {"current_task_id": task_id})
            
            logger.info(f"Assigned task {task_id} to agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to assign task {task_id} to agent {agent_id}: {e}",
                exc_info=True,
            )
            return False
