"""Agent state persistence layer for June.

Provides database operations for agent state management including state persistence,
execution history, plans, and knowledge cache.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg
from pydantic import ValidationError

from june_agent_state.models import (
    AgentCapabilities,
    AgentExecutionOutcome,
    AgentExecutionRecord,
    AgentMetrics,
    AgentPlan,
    AgentState,
    AgentStatus,
)

logger = logging.getLogger(__name__)


class AgentStateStorage:
    """Storage layer for agent state persistence using PostgreSQL."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "june",
        user: str = "postgres",
        password: Optional[str] = None,
        connection_pool: Optional[asyncpg.Pool] = None,
    ):
        """
        Initialize agent state storage.

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Database user
            password: Database password
            connection_pool: Optional existing connection pool (if provided, ignores other params)
        """
        if connection_pool is not None:
            self.pool = connection_pool
            self._own_pool = False
        else:
            self.pool = None
            self._own_pool = True
            self._host = host
            self._port = port
            self._database = database
            self._user = user
            self._password = password

    async def connect(self) -> None:
        """Create connection pool if not using external pool."""
        if self.pool is None and self._own_pool:
            try:
                self.pool = await asyncpg.create_pool(
                    host=self._host,
                    port=self._port,
                    database=self._database,
                    user=self._user,
                    password=self._password,
                    min_size=1,
                    max_size=10,
                )
                logger.info(
                    f"Created connection pool for agent state storage: {self._database}"
                )
            except Exception as e:
                logger.error(f"Failed to create connection pool: {e}", exc_info=True)
                raise

    async def disconnect(self) -> None:
        """Close connection pool if we own it."""
        if self.pool is not None and self._own_pool:
            await self.pool.close()
            self.pool = None
            logger.info("Closed connection pool for agent state storage")

    async def save_state(self, state: AgentState) -> None:
        """
        Save agent state to database.

        Args:
            state: AgentState instance to save

        Raises:
            ValueError: If state validation fails
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Serialize capabilities
                    capabilities_json = json.dumps(
                        [cap.model_dump() for cap in state.capabilities]
                    )

                    # Serialize metrics
                    metrics_json = json.dumps(state.metrics.model_dump())

                    # Serialize config
                    config_json = json.dumps(state.config)

                    # Use INSERT ... ON CONFLICT UPDATE for upsert
                    await conn.execute(
                        """
                        INSERT INTO agent_state (
                            agent_id, current_task_id, status, capabilities,
                            performance_metrics, configuration, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
                        ON CONFLICT (agent_id) DO UPDATE SET
                            current_task_id = EXCLUDED.current_task_id,
                            status = EXCLUDED.status,
                            capabilities = EXCLUDED.capabilities,
                            performance_metrics = EXCLUDED.performance_metrics,
                            configuration = EXCLUDED.configuration,
                            updated_at = NOW()
                        """,
                        state.agent_id,
                        state.current_task_id,
                        state.status.value,
                        capabilities_json,
                        metrics_json,
                        config_json,
                    )

                    logger.debug(f"Saved agent state for agent_id={state.agent_id}")

        except Exception as e:
            logger.error(
                f"Failed to save agent state for agent_id={state.agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def load_state(self, agent_id: str) -> Optional[AgentState]:
        """
        Load agent state from database.

        Args:
            agent_id: Agent ID to load state for

        Returns:
            AgentState instance if found, None otherwise

        Raises:
            ValidationError: If loaded data fails validation
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT agent_id, current_task_id, status, capabilities,
                           performance_metrics, configuration, created_at, updated_at
                    FROM agent_state
                    WHERE agent_id = $1
                    """,
                    agent_id,
                )

                if row is None:
                    logger.debug(f"No state found for agent_id={agent_id}")
                    return None

                # Deserialize capabilities
                capabilities_data = json.loads(row["capabilities"] or "[]")
                capabilities = [
                    AgentCapabilities(**cap_data) for cap_data in capabilities_data
                ]

                # Deserialize metrics
                metrics_data = json.loads(row["performance_metrics"] or "{}")
                metrics = AgentMetrics(**metrics_data)

                # Deserialize config
                config = json.loads(row["configuration"] or "{}")

                # Build AgentState
                state = AgentState(
                    agent_id=row["agent_id"],
                    current_task_id=row["current_task_id"],
                    status=AgentStatus(row["status"]),
                    capabilities=capabilities,
                    metrics=metrics,
                    config=config,
                )

                logger.debug(f"Loaded agent state for agent_id={agent_id}")
                return state

        except ValidationError as e:
            logger.error(
                f"Validation error loading agent state for agent_id={agent_id}: {e}",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                f"Failed to load agent state for agent_id={agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def update_state(
        self, agent_id: str, updates: Dict[str, Any]
    ) -> Optional[AgentState]:
        """
        Update agent state with partial updates.

        Args:
            agent_id: Agent ID to update
            updates: Dictionary of fields to update (e.g., {'status': 'active', 'current_task_id': 'task-123'})

        Returns:
            Updated AgentState instance if found, None otherwise

        Raises:
            ValueError: If update fields are invalid
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        # Build update query dynamically
        set_clauses = []
        values = []
        param_idx = 1

        allowed_fields = {
            "current_task_id",
            "status",
            "capabilities",
            "performance_metrics",
            "configuration",
        }

        for field, value in updates.items():
            if field not in allowed_fields:
                raise ValueError(f"Invalid update field: {field}")

            if field == "status":
                # Convert to enum value if needed
                if isinstance(value, AgentStatus):
                    value = value.value
                set_clauses.append(f"status = ${param_idx}")
                values.append(value)
                param_idx += 1
            elif field == "capabilities":
                # Serialize if it's a list of AgentCapabilities
                if isinstance(value, list) and value and isinstance(
                    value[0], AgentCapabilities
                ):
                    value = json.dumps([cap.model_dump() for cap in value])
                elif isinstance(value, str):
                    # Already JSON string
                    pass
                else:
                    value = json.dumps(value)
                set_clauses.append(f"capabilities = ${param_idx}")
                values.append(value)
                param_idx += 1
            elif field == "performance_metrics":
                # Serialize if it's an AgentMetrics instance
                if isinstance(value, AgentMetrics):
                    value = json.dumps(value.model_dump())
                elif isinstance(value, str):
                    # Already JSON string
                    pass
                else:
                    value = json.dumps(value)
                set_clauses.append(f"performance_metrics = ${param_idx}")
                values.append(value)
                param_idx += 1
            elif field == "configuration":
                # Serialize if it's a dict
                if isinstance(value, str):
                    # Already JSON string
                    pass
                else:
                    value = json.dumps(value)
                set_clauses.append(f"configuration = ${param_idx}")
                values.append(value)
                param_idx += 1
            else:
                # Simple field
                set_clauses.append(f"{field} = ${param_idx}")
                values.append(value)
                param_idx += 1

        if not set_clauses:
            # No updates, just return current state
            return await self.load_state(agent_id)

        # Add updated_at and agent_id
        values.append(agent_id)
        query = f"""
            UPDATE agent_state
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE agent_id = ${param_idx}
        """

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(query, *values)

                    logger.debug(f"Updated agent state for agent_id={agent_id}")
                    return await self.load_state(agent_id)

        except Exception as e:
            logger.error(
                f"Failed to update agent state for agent_id={agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def list_all_states(
        self, status: Optional[AgentStatus] = None, limit: int = 1000
    ) -> List[AgentState]:
        """
        List all agent states with optional status filter.

        Args:
            status: Filter by agent status (optional)
            limit: Maximum number of states to return

        Returns:
            List of AgentState instances

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                conditions = []
                params = []
                param_idx = 1

                if status:
                    conditions.append(f"status = ${param_idx}")
                    params.append(status.value)
                    param_idx += 1

                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

                params.append(limit)

                query = f"""
                    SELECT agent_id, current_task_id, status, capabilities,
                           performance_metrics, configuration, created_at, updated_at
                    FROM agent_state
                    {where_clause}
                    ORDER BY updated_at DESC
                    LIMIT ${param_idx}
                """

                rows = await conn.fetch(query, *params)

                states = []
                for row in rows:
                    try:
                        # Deserialize capabilities
                        capabilities_data = json.loads(row["capabilities"] or "[]")
                        capabilities = [
                            AgentCapabilities(**cap_data)
                            for cap_data in capabilities_data
                        ]

                        # Deserialize metrics
                        metrics_data = json.loads(row["performance_metrics"] or "{}")
                        metrics = AgentMetrics(**metrics_data)

                        # Deserialize config
                        config = json.loads(row["configuration"] or "{}")

                        # Build AgentState
                        state = AgentState(
                            agent_id=row["agent_id"],
                            current_task_id=row["current_task_id"],
                            status=AgentStatus(row["status"]),
                            capabilities=capabilities,
                            metrics=metrics,
                            config=config,
                        )
                        states.append(state)
                    except ValidationError as e:
                        logger.warning(
                            f"Validation error loading state for agent_id={row['agent_id']}: {e}"
                        )
                        continue

                logger.debug(f"Listed {len(states)} agent states")
                return states

        except Exception as e:
            logger.error(f"Failed to list agent states: {e}", exc_info=True)
            raise

    async def save_execution_record(self, record: AgentExecutionRecord) -> str:
        """
        Save execution history record.

        Args:
            record: AgentExecutionRecord instance to save

        Returns:
            Record ID (UUID as string)

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.fetchrow(
                        """
                        INSERT INTO agent_execution_history (
                            agent_id, task_id, action_type, outcome,
                            duration_ms, metadata, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        RETURNING id
                        """,
                        record.agent_id,
                        record.task_id,
                        record.action_type,
                        record.outcome.value if record.outcome else None,
                        record.duration_ms,
                        json.dumps(record.metadata),
                        record.created_at,
                    )

                    record_id = str(result["id"])
                    logger.debug(
                        f"Saved execution record id={record_id} for agent_id={record.agent_id}"
                    )
                    return record_id

        except Exception as e:
            logger.error(
                f"Failed to save execution record for agent_id={record.agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def query_execution_history(
        self,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AgentExecutionRecord]:
        """
        Query execution history records.

        Args:
            agent_id: Filter by agent ID (optional)
            task_id: Filter by task ID (optional)
            start_time: Filter records created after this time (optional)
            end_time: Filter records created before this time (optional)
            limit: Maximum number of records to return

        Returns:
            List of AgentExecutionRecord instances

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                conditions = []
                params = []
                param_idx = 1

                if agent_id:
                    conditions.append(f"agent_id = ${param_idx}")
                    params.append(agent_id)
                    param_idx += 1

                if task_id:
                    conditions.append(f"task_id = ${param_idx}")
                    params.append(task_id)
                    param_idx += 1

                if start_time:
                    conditions.append(f"created_at >= ${param_idx}")
                    params.append(start_time)
                    param_idx += 1

                if end_time:
                    conditions.append(f"created_at <= ${param_idx}")
                    params.append(end_time)
                    param_idx += 1

                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

                params.append(limit)

                query = f"""
                    SELECT id, agent_id, task_id, action_type, outcome,
                           duration_ms, metadata, created_at
                    FROM agent_execution_history
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ${param_idx}
                """

                rows = await conn.fetch(query, *params)

                records = []
                for row in rows:
                    outcome = None
                    if row["outcome"]:
                        outcome = AgentExecutionOutcome(row["outcome"])

                    record = AgentExecutionRecord(
                        agent_id=row["agent_id"],
                        task_id=row["task_id"],
                        action_type=row["action_type"],
                        outcome=outcome,
                        duration_ms=row["duration_ms"],
                        metadata=json.loads(row["metadata"] or "{}"),
                        created_at=row["created_at"],
                    )
                    records.append(record)

                logger.debug(f"Queried {len(records)} execution records")
                return records

        except Exception as e:
            logger.error(f"Failed to query execution history: {e}", exc_info=True)
            raise

    async def save_plan(self, plan: AgentPlan) -> str:
        """
        Save agent plan to database.

        Args:
            plan: AgentPlan instance to save

        Returns:
            Plan ID (UUID as string)

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.fetchrow(
                        """
                        INSERT INTO agent_plans (
                            agent_id, task_id, plan_type, plan_data,
                            success_rate, execution_count, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        RETURNING id
                        """,
                        plan.agent_id,
                        plan.task_id,
                        plan.plan_type,
                        json.dumps(plan.plan_data),
                        plan.success_rate,
                        plan.execution_count,
                        plan.created_at,
                        plan.updated_at,
                    )

                    plan_id = str(result["id"])
                    logger.debug(
                        f"Saved plan id={plan_id} for agent_id={plan.agent_id}"
                    )
                    return plan_id

        except Exception as e:
            logger.error(
                f"Failed to save plan for agent_id={plan.agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def load_plan(self, plan_id: str) -> Optional[AgentPlan]:
        """
        Load agent plan by ID.

        Args:
            plan_id: Plan ID (UUID string)

        Returns:
            AgentPlan instance if found, None otherwise

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, agent_id, task_id, plan_type, plan_data,
                           success_rate, execution_count, created_at, updated_at
                    FROM agent_plans
                    WHERE id = $1
                    """,
                    plan_id,
                )

                if row is None:
                    logger.debug(f"No plan found for plan_id={plan_id}")
                    return None

                plan = AgentPlan(
                    agent_id=row["agent_id"],
                    task_id=row["task_id"],
                    plan_type=row["plan_type"],
                    plan_data=json.loads(row["plan_data"] or "{}"),
                    success_rate=row["success_rate"],
                    execution_count=row["execution_count"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

                logger.debug(f"Loaded plan id={plan_id}")
                return plan

        except ValidationError as e:
            logger.error(
                f"Validation error loading plan plan_id={plan_id}: {e}",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(f"Failed to load plan plan_id={plan_id}: {e}", exc_info=True)
            raise

    async def update_plan(
        self, plan_id: str, updates: Dict[str, Any]
    ) -> Optional[AgentPlan]:
        """
        Update agent plan.

        Args:
            plan_id: Plan ID to update
            updates: Dictionary of fields to update

        Returns:
            Updated AgentPlan instance if found, None otherwise

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        set_clauses = []
        values = []
        param_idx = 1

        allowed_fields = {
            "plan_data",
            "success_rate",
            "execution_count",
        }

        for field, value in updates.items():
            if field not in allowed_fields:
                raise ValueError(f"Invalid update field: {field}")

            if field == "plan_data":
                if isinstance(value, str):
                    pass  # Already JSON string
                else:
                    value = json.dumps(value)
                set_clauses.append(f"plan_data = ${param_idx}")
            else:
                set_clauses.append(f"{field} = ${param_idx}")

            values.append(value)
            param_idx += 1

        if not set_clauses:
            return await self.load_plan(plan_id)

        values.append(plan_id)
        query = f"""
            UPDATE agent_plans
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = ${param_idx}
        """

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(query, *values)
                    logger.debug(f"Updated plan id={plan_id}")
                    return await self.load_plan(plan_id)

        except Exception as e:
            logger.error(f"Failed to update plan plan_id={plan_id}: {e}", exc_info=True)
            raise

    async def query_plans(
        self,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        plan_type: Optional[str] = None,
        min_success_rate: Optional[float] = None,
        limit: int = 100,
    ) -> List[AgentPlan]:
        """
        Query agent plans.

        Args:
            agent_id: Filter by agent ID (optional)
            task_id: Filter by task ID (optional)
            plan_type: Filter by plan type (optional)
            min_success_rate: Filter by minimum success rate (optional)
            limit: Maximum number of plans to return

        Returns:
            List of AgentPlan instances

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                conditions = []
                params = []
                param_idx = 1

                if agent_id:
                    conditions.append(f"agent_id = ${param_idx}")
                    params.append(agent_id)
                    param_idx += 1

                if task_id:
                    conditions.append(f"task_id = ${param_idx}")
                    params.append(task_id)
                    param_idx += 1

                if plan_type:
                    conditions.append(f"plan_type = ${param_idx}")
                    params.append(plan_type)
                    param_idx += 1

                if min_success_rate is not None:
                    conditions.append(f"success_rate >= ${param_idx}")
                    params.append(min_success_rate)
                    param_idx += 1

                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

                params.append(limit)

                query = f"""
                    SELECT id, agent_id, task_id, plan_type, plan_data,
                           success_rate, execution_count, created_at, updated_at
                    FROM agent_plans
                    {where_clause}
                    ORDER BY success_rate DESC, execution_count DESC
                    LIMIT ${param_idx}
                """

                rows = await conn.fetch(query, *params)

                plans = []
                for row in rows:
                    plan = AgentPlan(
                        agent_id=row["agent_id"],
                        task_id=row["task_id"],
                        plan_type=row["plan_type"],
                        plan_data=json.loads(row["plan_data"] or "{}"),
                        success_rate=row["success_rate"],
                        execution_count=row["execution_count"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    plans.append(plan)

                logger.debug(f"Queried {len(plans)} plans")
                return plans

        except Exception as e:
            logger.error(f"Failed to query plans: {e}", exc_info=True)
            raise

    async def save_knowledge(
        self, agent_id: str, knowledge_key: str, knowledge_value: Dict[str, Any]
    ) -> str:
        """
        Save knowledge to cache.

        Args:
            agent_id: Agent ID
            knowledge_key: Knowledge key identifier
            knowledge_value: Knowledge value (will be serialized to JSON)

        Returns:
            Knowledge cache ID (UUID as string)

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.fetchrow(
                        """
                        INSERT INTO agent_knowledge_cache (
                            agent_id, knowledge_key, knowledge_value,
                            access_count, last_accessed_at
                        ) VALUES ($1, $2, $3, 0, NOW())
                        ON CONFLICT (agent_id, knowledge_key) DO UPDATE SET
                            knowledge_value = EXCLUDED.knowledge_value,
                            updated_at = NOW(),
                            last_accessed_at = NOW()
                        RETURNING id
                        """,
                        agent_id,
                        knowledge_key,
                        json.dumps(knowledge_value),
                    )

                    cache_id = str(result["id"])
                    logger.debug(
                        f"Saved knowledge key={knowledge_key} for agent_id={agent_id}"
                    )
                    return cache_id

        except Exception as e:
            logger.error(
                f"Failed to save knowledge key={knowledge_key} for agent_id={agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def get_knowledge(
        self, agent_id: str, knowledge_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get knowledge from cache.

        Args:
            agent_id: Agent ID
            knowledge_key: Knowledge key identifier

        Returns:
            Knowledge value dict if found, None otherwise

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                # Update access count and last_accessed_at
                await conn.execute(
                    """
                    UPDATE agent_knowledge_cache
                    SET access_count = access_count + 1,
                        last_accessed_at = NOW()
                    WHERE agent_id = $1 AND knowledge_key = $2
                    """,
                    agent_id,
                    knowledge_key,
                )

                row = await conn.fetchrow(
                    """
                    SELECT knowledge_value
                    FROM agent_knowledge_cache
                    WHERE agent_id = $1 AND knowledge_key = $2
                    """,
                    agent_id,
                    knowledge_key,
                )

                if row is None:
                    logger.debug(
                        f"No knowledge found for key={knowledge_key}, agent_id={agent_id}"
                    )
                    return None

                value = json.loads(row["knowledge_value"] or "{}")
                logger.debug(
                    f"Retrieved knowledge key={knowledge_key} for agent_id={agent_id}"
                )
                return value

        except Exception as e:
            logger.error(
                f"Failed to get knowledge key={knowledge_key} for agent_id={agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def expire_knowledge(
        self,
        agent_id: Optional[str] = None,
        older_than_days: int = 30,
        limit: int = 1000,
    ) -> int:
        """
        Expire old knowledge cache entries.

        Args:
            agent_id: Filter by agent ID (optional, expires all agents if None)
            older_than_days: Delete entries older than this many days
            limit: Maximum number of entries to delete

        Returns:
            Number of entries deleted

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = [
                        f"last_accessed_at < NOW() - INTERVAL '{older_than_days} days'"
                    ]
                    params = []
                    param_idx = 1

                    if agent_id:
                        conditions.append(f"agent_id = ${param_idx}")
                        params.append(agent_id)
                        param_idx += 1

                    where_clause = "WHERE " + " AND ".join(conditions)

                    # Delete in batches to avoid long transactions
                    result = await conn.execute(
                        f"""
                        DELETE FROM agent_knowledge_cache
                        {where_clause}
                        AND id IN (
                            SELECT id FROM agent_knowledge_cache
                            {where_clause}
                            LIMIT ${param_idx}
                        )
                        """,
                        *params,
                        limit,
                    )

                    deleted_count = int(result.split()[-1])
                    logger.info(
                        f"Expired {deleted_count} knowledge cache entries (older than {older_than_days} days)"
                    )
                    return deleted_count

        except Exception as e:
            logger.error(f"Failed to expire knowledge cache: {e}", exc_info=True)
            raise

    async def save_resource_lock(
        self,
        resource_id: str,
        agent_id: str,
        lock_type: str,
        expires_at: datetime,
    ) -> str:
        """
        Save a resource lock to database.

        Args:
            resource_id: Resource identifier
            agent_id: Agent holding the lock
            lock_type: Lock type ('exclusive' or 'shared')
            expires_at: Expiration timestamp

        Returns:
            Lock ID (UUID as string)

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.fetchrow(
                        """
                        INSERT INTO resource_locks (
                            resource_id, agent_id, lock_type, expires_at, released
                        ) VALUES ($1, $2, $3, $4, FALSE)
                        RETURNING id
                        """,
                        resource_id,
                        agent_id,
                        lock_type,
                        expires_at,
                    )

                    lock_id = str(result["id"])
                    logger.debug(
                        f"Saved resource lock: resource_id={resource_id}, "
                        f"agent_id={agent_id}, lock_type={lock_type}"
                    )
                    return lock_id

        except Exception as e:
            logger.error(
                f"Failed to save resource lock for resource_id={resource_id}, "
                f"agent_id={agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def release_resource_lock(self, resource_id: str, agent_id: str) -> bool:
        """
        Release a resource lock in database.

        Args:
            resource_id: Resource identifier
            agent_id: Agent releasing the lock

        Returns:
            True if lock was released, False if not found

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(
                        """
                        UPDATE resource_locks
                        SET released = TRUE
                        WHERE resource_id = $1 AND agent_id = $2 
                          AND released = FALSE
                          AND expires_at > NOW()
                        """,
                        resource_id,
                        agent_id,
                    )

                    released = result.split()[-1] != "0"
                    if released:
                        logger.debug(
                            f"Released resource lock: resource_id={resource_id}, "
                            f"agent_id={agent_id}"
                        )
                    return released

        except Exception as e:
            logger.error(
                f"Failed to release resource lock for resource_id={resource_id}, "
                f"agent_id={agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def release_all_agent_locks(self, agent_id: str) -> int:
        """
        Release all locks held by an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Number of locks released

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(
                        """
                        UPDATE resource_locks
                        SET released = TRUE
                        WHERE agent_id = $1 AND released = FALSE
                          AND expires_at > NOW()
                        """,
                        agent_id,
                    )

                    count = int(result.split()[-1])
                    if count > 0:
                        logger.debug(f"Released {count} locks for agent_id={agent_id}")
                    return count

        except Exception as e:
            logger.error(
                f"Failed to release all locks for agent_id={agent_id}: {e}",
                exc_info=True,
            )
            raise

    async def get_active_resource_locks(
        self, resource_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all active resource locks from database.

        Args:
            resource_id: Optional resource ID to filter by (None for all)

        Returns:
            List of lock dictionaries with keys: resource_id, agent_id, lock_type,
            created_at, expires_at

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                if resource_id:
                    rows = await conn.fetch(
                        """
                        SELECT resource_id, agent_id, lock_type, created_at, expires_at
                        FROM resource_locks
                        WHERE resource_id = $1
                          AND released = FALSE
                          AND expires_at > NOW()
                        ORDER BY created_at
                        """,
                        resource_id,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT resource_id, agent_id, lock_type, created_at, expires_at
                        FROM resource_locks
                        WHERE released = FALSE
                          AND expires_at > NOW()
                        ORDER BY resource_id, created_at
                        """
                    )

                locks = []
                for row in rows:
                    locks.append(
                        {
                            "resource_id": row["resource_id"],
                            "agent_id": row["agent_id"],
                            "lock_type": row["lock_type"],
                            "created_at": row["created_at"],
                            "expires_at": row["expires_at"],
                        }
                    )

                return locks

        except Exception as e:
            logger.error(f"Failed to get active resource locks: {e}", exc_info=True)
            raise

    async def cleanup_expired_locks(self) -> int:
        """
        Clean up expired locks from database.

        Returns:
            Number of locks cleaned up

        Raises:
            Exception: If database operation fails
        """
        if self.pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(
                        """
                        UPDATE resource_locks
                        SET released = TRUE
                        WHERE released = FALSE AND expires_at <= NOW()
                        """
                    )

                    count = int(result.split()[-1])
                    if count > 0:
                        logger.debug(f"Cleaned up {count} expired resource locks")
                    return count

        except Exception as e:
            logger.error(f"Failed to cleanup expired locks: {e}", exc_info=True)
            raise
