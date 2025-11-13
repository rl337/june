"""Agent registry and lifecycle management for June.

Provides agent registration, status tracking, and lifecycle management
with integration to persistent storage.
"""
import logging
from typing import Any, Dict, List, Optional

from june_agent_state.models import (
    AgentCapabilities,
    AgentState,
    AgentStatus,
)
from june_agent_state.storage import AgentStateStorage

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry for managing agent registration and lifecycle."""

    def __init__(self, storage: AgentStateStorage):
        """
        Initialize agent registry.

        Args:
            storage: AgentStateStorage instance for persistence
        """
        self.storage = storage
        logger.info("Agent registry initialized")

    async def register_agent(
        self,
        agent_id: str,
        capabilities: Optional[List[AgentCapabilities]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentState:
        """
        Register a new agent or update existing agent registration.

        Args:
            agent_id: Unique agent identifier
            capabilities: List of agent capabilities (optional)
            config: Agent configuration dictionary (optional)

        Returns:
            AgentState instance for the registered agent

        Raises:
            Exception: If registration fails
        """
        try:
            # Check if agent already exists
            existing_state = await self.storage.load_state(agent_id)

            if existing_state:
                logger.info(f"Agent {agent_id} already registered, updating registration")
                # Update existing state
                updates: Dict[str, Any] = {}

                if capabilities is not None:
                    updates["capabilities"] = capabilities

                if config is not None:
                    # Merge with existing config
                    current_config = existing_state.config
                    current_config.update(config)
                    updates["configuration"] = current_config

                # Ensure status is at least INIT if it's a new registration
                if existing_state.status == AgentStatus.ERROR:
                    updates["status"] = AgentStatus.INIT

                if updates:
                    updated_state = await self.storage.update_state(
                        agent_id, updates
                    )
                    if updated_state:
                        return updated_state

                return existing_state
            else:
                # Create new agent state
                logger.info(f"Registering new agent: {agent_id}")
                new_state = AgentState(
                    agent_id=agent_id,
                    current_task_id=None,
                    status=AgentStatus.INIT,
                    capabilities=capabilities or [],
                    config=config or {},
                )

                await self.storage.save_state(new_state)
                logger.info(f"Successfully registered agent: {agent_id}")
                return new_state

        except Exception as e:
            logger.error(f"Failed to register agent {agent_id}: {e}", exc_info=True)
            raise

    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent (mark as inactive and cleanup).

        Args:
            agent_id: Agent ID to unregister

        Returns:
            True if agent was unregistered, False if agent not found

        Raises:
            Exception: If unregistration fails
        """
        try:
            existing_state = await self.storage.load_state(agent_id)

            if existing_state is None:
                logger.warning(f"Attempted to unregister non-existent agent: {agent_id}")
                return False

            # Update status to indicate agent is no longer active
            # We don't delete the state, just mark it as inactive
            # This preserves history and metrics
            await self.storage.update_state(agent_id, {"status": AgentStatus.IDLE})

            logger.info(f"Unregistered agent: {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to unregister agent {agent_id}: {e}", exc_info=True)
            raise

    async def get_agent(self, agent_id: str) -> Optional[AgentState]:
        """
        Get agent state by ID.

        Args:
            agent_id: Agent ID to retrieve

        Returns:
            AgentState instance if found, None otherwise

        Raises:
            Exception: If retrieval fails
        """
        try:
            state = await self.storage.load_state(agent_id)
            return state

        except Exception as e:
            logger.error(f"Failed to get agent {agent_id}: {e}", exc_info=True)
            raise

    async def list_agents(
        self,
        status: Optional[AgentStatus] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[AgentState]:
        """
        List all registered agents with optional filtering.

        Args:
            status: Filter by agent status (optional)
            filters: Additional filter criteria (optional)
                - has_task: bool - filter agents with/without current task
                - capability: str - filter agents with specific capability

        Returns:
            List of AgentState instances matching criteria

        Raises:
            Exception: If query fails
        """
        try:
            # Get all agents, optionally filtered by status
            all_states = await self.storage.list_all_states(status=status)

            # Apply additional filters if provided
            if filters:
                filtered_states = []

                for state in all_states:
                    match = True

                    # Filter by has_task
                    if "has_task" in filters:
                        has_task = filters["has_task"]
                        if has_task and state.current_task_id is None:
                            match = False
                        elif not has_task and state.current_task_id is not None:
                            match = False

                    # Filter by capability
                    if "capability" in filters and match:
                        capability = filters["capability"]
                        has_capability = False
                        for cap in state.capabilities:
                            if capability in cap.tools:
                                has_capability = True
                                break
                        if not has_capability:
                            match = False

                    if match:
                        filtered_states.append(state)

                return filtered_states

            return all_states

        except Exception as e:
            logger.error(f"Failed to list agents: {e}", exc_info=True)
            raise

    async def update_agent_status(
        self, agent_id: str, status: AgentStatus
    ) -> Optional[AgentState]:
        """
        Update agent status.

        Args:
            agent_id: Agent ID to update
            status: New status

        Returns:
            Updated AgentState instance if found, None otherwise

        Raises:
            ValueError: If status transition is invalid
            Exception: If update fails
        """
        try:
            existing_state = await self.storage.load_state(agent_id)

            if existing_state is None:
                logger.warning(
                    f"Attempted to update status for non-existent agent: {agent_id}"
                )
                return None

            # Validate status transition
            current_status = existing_state.status

            # Define valid transitions (simplified - can be enhanced)
            valid_transitions = {
                AgentStatus.INIT: [AgentStatus.ACTIVE, AgentStatus.ERROR],
                AgentStatus.ACTIVE: [AgentStatus.IDLE, AgentStatus.ERROR],
                AgentStatus.IDLE: [AgentStatus.ACTIVE, AgentStatus.ERROR],
                AgentStatus.ERROR: [AgentStatus.INIT, AgentStatus.ACTIVE],
            }

            if status not in valid_transitions.get(current_status, []):
                logger.warning(
                    f"Invalid status transition for agent {agent_id}: "
                    f"{current_status.value} -> {status.value}"
                )
                # Allow the transition anyway but log warning
                # In production, might want to raise ValueError

            updated_state = await self.storage.update_state(agent_id, {"status": status})

            logger.info(
                f"Updated agent {agent_id} status: {current_status.value} -> {status.value}"
            )
            return updated_state

        except Exception as e:
            logger.error(
                f"Failed to update agent status for {agent_id}: {e}", exc_info=True
            )
            raise

    async def initialize_agent_on_startup(
        self,
        agent_id: str,
        capabilities: Optional[List[AgentCapabilities]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentState:
        """
        Initialize agent state on startup (recover or create).

        Args:
            agent_id: Agent ID
            capabilities: Agent capabilities (optional)
            config: Agent configuration (optional)

        Returns:
            AgentState instance

        Raises:
            Exception: If initialization fails
        """
        try:
            # Try to load existing state
            existing_state = await self.storage.load_state(agent_id)

            if existing_state:
                logger.info(f"Recovered state for agent {agent_id} on startup")
                # Update status to ACTIVE if it was IDLE or ERROR
                if existing_state.status in (AgentStatus.IDLE, AgentStatus.ERROR):
                    await self.storage.update_state(
                        agent_id, {"status": AgentStatus.ACTIVE}
                    )
                    existing_state.status = AgentStatus.ACTIVE

                # Update capabilities/config if provided
                if capabilities is not None or config is not None:
                    updates: Dict[str, Any] = {}
                    if capabilities is not None:
                        updates["capabilities"] = capabilities
                    if config is not None:
                        current_config = existing_state.config
                        current_config.update(config)
                        updates["configuration"] = current_config

                    if updates:
                        updated_state = await self.storage.update_state(
                            agent_id, updates
                        )
                        if updated_state:
                            return updated_state

                return existing_state
            else:
                # No existing state, create new
                logger.info(f"Initializing new agent {agent_id} on startup")
                return await self.register_agent(agent_id, capabilities, config)

        except Exception as e:
            logger.error(
                f"Failed to initialize agent {agent_id} on startup: {e}", exc_info=True
            )
            raise

    async def get_agent_by_capability(self, capability: str) -> List[AgentState]:
        """
        Get agents that have a specific capability.

        Args:
            capability: Capability name to search for

        Returns:
            List of AgentState instances with the capability

        Raises:
            Exception: If query fails
        """
        try:
            all_states = await self.storage.list_all_states()

            matching_agents = []
            for state in all_states:
                for cap in state.capabilities:
                    if capability in cap.tools:
                        matching_agents.append(state)
                        break

            logger.debug(f"Found {len(matching_agents)} agents with capability {capability}")
            return matching_agents

        except Exception as e:
            logger.error(
                f"Failed to get agents by capability {capability}: {e}", exc_info=True
            )
            raise

    async def get_available_agents(self) -> List[AgentState]:
        """
        Get list of available agents (status ACTIVE or IDLE).

        Returns:
            List of available AgentState instances

        Raises:
            Exception: If query fails
        """
        try:
            all_states = await self.storage.list_all_states()

            available_agents = [
                state
                for state in all_states
                if state.status in (AgentStatus.ACTIVE, AgentStatus.IDLE)
            ]

            logger.debug(f"Found {len(available_agents)} available agents")
            return available_agents

        except Exception as e:
            logger.error(f"Failed to get available agents: {e}", exc_info=True)
            raise
