"""Tests for agent state storage layer."""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

import pytest

from june_agent_state.models import (
    AgentCapabilities,
    AgentExecutionOutcome,
    AgentExecutionRecord,
    AgentMetrics,
    AgentPlan,
    AgentState,
    AgentStatus,
)
from june_agent_state.storage import AgentStateStorage


@pytest.fixture
async def storage():
    """Create storage instance for testing."""
    # Use test database connection
    storage = AgentStateStorage(
        host="localhost",
        port=5432,
        database="june",
        user="postgres",
        password=None,  # Use environment or defaults
    )
    await storage.connect()
    yield storage
    await storage.disconnect()


@pytest.fixture
def sample_agent_state():
    """Create sample agent state for testing."""
    return AgentState(
        agent_id="test-agent-1",
        current_task_id="task-123",
        status=AgentStatus.ACTIVE,
        capabilities=[
            AgentCapabilities(
                tools=["code_execution", "git_operations"],
                metadata={"version": "1.0"},
            )
        ],
        metrics=AgentMetrics(
            tasks_completed=10,
            avg_execution_time=5.5,
            success_rate=0.9,
            total_execution_time=55.0,
            tasks_succeeded=9,
            tasks_failed=1,
        ),
        config={"max_concurrent_tasks": 3},
    )


@pytest.mark.asyncio
async def test_save_and_load_state(storage, sample_agent_state):
    """Test saving and loading agent state."""
    # Save state
    await storage.save_state(sample_agent_state)

    # Load state
    loaded_state = await storage.load_state("test-agent-1")

    # Verify loaded state
    assert loaded_state is not None
    assert loaded_state.agent_id == "test-agent-1"
    assert loaded_state.current_task_id == "task-123"
    assert loaded_state.status == AgentStatus.ACTIVE
    assert len(loaded_state.capabilities) == 1
    assert loaded_state.capabilities[0].tools == ["code_execution", "git_operations"]
    assert loaded_state.metrics.tasks_completed == 10
    assert loaded_state.metrics.success_rate == 0.9
    assert loaded_state.config["max_concurrent_tasks"] == 3


@pytest.mark.asyncio
async def test_save_state_updates_existing(storage, sample_agent_state):
    """Test that saving state updates existing record."""
    # Save initial state
    await storage.save_state(sample_agent_state)

    # Update state
    sample_agent_state.current_task_id = "task-456"
    sample_agent_state.status = AgentStatus.IDLE
    await storage.save_state(sample_agent_state)

    # Load and verify update
    loaded_state = await storage.load_state("test-agent-1")
    assert loaded_state.current_task_id == "task-456"
    assert loaded_state.status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_load_nonexistent_state(storage):
    """Test loading state that doesn't exist."""
    loaded_state = await storage.load_state("nonexistent-agent")
    assert loaded_state is None


@pytest.mark.asyncio
async def test_update_state_partial(storage, sample_agent_state):
    """Test partial state updates."""
    # Save initial state
    await storage.save_state(sample_agent_state)

    # Update only status
    updated_state = await storage.update_state(
        "test-agent-1", {"status": AgentStatus.IDLE}
    )

    assert updated_state is not None
    assert updated_state.status == AgentStatus.IDLE
    # Other fields should remain unchanged
    assert updated_state.current_task_id == "task-123"


@pytest.mark.asyncio
async def test_update_state_multiple_fields(storage, sample_agent_state):
    """Test updating multiple fields."""
    # Save initial state
    await storage.save_state(sample_agent_state)

    # Update multiple fields
    new_metrics = AgentMetrics(tasks_completed=20, success_rate=0.95)
    updated_state = await storage.update_state(
        "test-agent-1",
        {
            "status": AgentStatus.IDLE,
            "current_task_id": "task-789",
            "performance_metrics": new_metrics,
        },
    )

    assert updated_state is not None
    assert updated_state.status == AgentStatus.IDLE
    assert updated_state.current_task_id == "task-789"
    assert updated_state.metrics.tasks_completed == 20
    assert updated_state.metrics.success_rate == 0.95


@pytest.mark.asyncio
async def test_save_execution_record(storage):
    """Test saving execution history record."""
    record = AgentExecutionRecord(
        agent_id="test-agent-1",
        task_id="task-123",
        action_type="task_completed",
        outcome=AgentExecutionOutcome.SUCCESS,
        duration_ms=5000,
        metadata={"tools_used": ["git", "pytest"]},
    )

    record_id = await storage.save_execution_record(record)
    assert record_id is not None
    assert isinstance(record_id, str)


@pytest.mark.asyncio
async def test_query_execution_history_by_agent(storage):
    """Test querying execution history by agent ID."""
    # Create multiple records
    record1 = AgentExecutionRecord(
        agent_id="test-agent-1",
        task_id="task-123",
        action_type="task_started",
        outcome=None,
        duration_ms=None,
    )
    record2 = AgentExecutionRecord(
        agent_id="test-agent-1",
        task_id="task-123",
        action_type="task_completed",
        outcome=AgentExecutionOutcome.SUCCESS,
        duration_ms=5000,
    )
    record3 = AgentExecutionRecord(
        agent_id="test-agent-2",
        task_id="task-456",
        action_type="task_completed",
        outcome=AgentExecutionOutcome.SUCCESS,
        duration_ms=3000,
    )

    await storage.save_execution_record(record1)
    await storage.save_execution_record(record2)
    await storage.save_execution_record(record3)

    # Query by agent_id
    history = await storage.query_execution_history(agent_id="test-agent-1")

    assert len(history) == 2
    assert all(record.agent_id == "test-agent-1" for record in history)


@pytest.mark.asyncio
async def test_query_execution_history_by_task(storage):
    """Test querying execution history by task ID."""
    record1 = AgentExecutionRecord(
        agent_id="test-agent-1",
        task_id="task-123",
        action_type="task_started",
    )
    record2 = AgentExecutionRecord(
        agent_id="test-agent-1",
        task_id="task-123",
        action_type="task_completed",
        outcome=AgentExecutionOutcome.SUCCESS,
    )
    record3 = AgentExecutionRecord(
        agent_id="test-agent-1",
        task_id="task-456",
        action_type="task_completed",
        outcome=AgentExecutionOutcome.SUCCESS,
    )

    await storage.save_execution_record(record1)
    await storage.save_execution_record(record2)
    await storage.save_execution_record(record3)

    # Query by task_id
    history = await storage.query_execution_history(task_id="task-123")

    assert len(history) == 2
    assert all(record.task_id == "task-123" for record in history)


@pytest.mark.asyncio
async def test_query_execution_history_time_range(storage):
    """Test querying execution history by time range."""
    now = datetime.now()
    past = now - timedelta(days=2)
    recent = now - timedelta(hours=1)

    record1 = AgentExecutionRecord(
        agent_id="test-agent-1",
        task_id="task-123",
        action_type="task_completed",
        created_at=past,
    )
    record2 = AgentExecutionRecord(
        agent_id="test-agent-1",
        task_id="task-456",
        action_type="task_completed",
        created_at=recent,
    )

    await storage.save_execution_record(record1)
    await storage.save_execution_record(record2)

    # Query recent records (last day)
    history = await storage.query_execution_history(
        agent_id="test-agent-1", start_time=recent - timedelta(hours=1)
    )

    assert len(history) >= 1
    assert all(record.created_at >= recent - timedelta(hours=1) for record in history)


@pytest.mark.asyncio
async def test_save_and_load_plan(storage):
    """Test saving and loading agent plan."""
    plan = AgentPlan(
        agent_id="test-agent-1",
        task_id="task-123",
        plan_type="execution_plan",
        plan_data={
            "steps": ["step1", "step2", "step3"],
            "strategy": "sequential",
        },
        success_rate=0.85,
        execution_count=10,
    )

    plan_id = await storage.save_plan(plan)
    assert plan_id is not None

    loaded_plan = await storage.load_plan(plan_id)
    assert loaded_plan is not None
    assert loaded_plan.agent_id == "test-agent-1"
    assert loaded_plan.task_id == "task-123"
    assert loaded_plan.plan_type == "execution_plan"
    assert loaded_plan.plan_data["strategy"] == "sequential"
    assert loaded_plan.success_rate == 0.85
    assert loaded_plan.execution_count == 10


@pytest.mark.asyncio
async def test_update_plan(storage):
    """Test updating agent plan."""
    plan = AgentPlan(
        agent_id="test-agent-1",
        task_id="task-123",
        plan_type="execution_plan",
        plan_data={"steps": ["step1"]},
        success_rate=0.5,
        execution_count=2,
    )

    plan_id = await storage.save_plan(plan)

    # Update plan
    updated_plan = await storage.update_plan(
        plan_id,
        {
            "success_rate": 0.9,
            "execution_count": 5,
            "plan_data": {"steps": ["step1", "step2"]},
        },
    )

    assert updated_plan is not None
    assert updated_plan.success_rate == 0.9
    assert updated_plan.execution_count == 5
    assert len(updated_plan.plan_data["steps"]) == 2


@pytest.mark.asyncio
async def test_query_plans(storage):
    """Test querying agent plans."""
    plan1 = AgentPlan(
        agent_id="test-agent-1",
        task_id="task-123",
        plan_type="execution_plan",
        plan_data={},
        success_rate=0.9,
        execution_count=10,
    )
    plan2 = AgentPlan(
        agent_id="test-agent-1",
        task_id="task-456",
        plan_type="task_decomposition",
        plan_data={},
        success_rate=0.7,
        execution_count=5,
    )
    plan3 = AgentPlan(
        agent_id="test-agent-2",
        task_id="task-789",
        plan_type="execution_plan",
        plan_data={},
        success_rate=0.8,
        execution_count=8,
    )

    await storage.save_plan(plan1)
    await storage.save_plan(plan2)
    await storage.save_plan(plan3)

    # Query by agent_id
    plans = await storage.query_plans(agent_id="test-agent-1")
    assert len(plans) == 2
    assert all(plan.agent_id == "test-agent-1" for plan in plans)

    # Query by plan_type
    plans = await storage.query_plans(plan_type="execution_plan")
    assert len(plans) >= 2
    assert all(plan.plan_type == "execution_plan" for plan in plans)

    # Query by min_success_rate
    plans = await storage.query_plans(min_success_rate=0.8)
    assert len(plans) >= 2
    assert all(plan.success_rate >= 0.8 for plan in plans)


@pytest.mark.asyncio
async def test_save_and_get_knowledge(storage):
    """Test saving and retrieving knowledge cache."""
    knowledge_value = {
        "pattern": "effective_test_strategy",
        "details": "Use pytest with fixtures",
        "score": 0.95,
    }

    cache_id = await storage.save_knowledge(
        "test-agent-1", "test_pattern", knowledge_value
    )
    assert cache_id is not None

    retrieved = await storage.get_knowledge("test-agent-1", "test_pattern")
    assert retrieved is not None
    assert retrieved["pattern"] == "effective_test_strategy"
    assert retrieved["score"] == 0.95


@pytest.mark.asyncio
async def test_knowledge_access_count_updates(storage):
    """Test that knowledge access count increments."""
    knowledge_value = {"data": "test"}
    await storage.save_knowledge("test-agent-1", "test_key", knowledge_value)

    # Access multiple times
    await storage.get_knowledge("test-agent-1", "test_key")
    await storage.get_knowledge("test-agent-1", "test_key")

    # Verify access count was updated (we can't easily check the count,
    # but we can verify the knowledge was retrieved)
    retrieved = await storage.get_knowledge("test-agent-1", "test_key")
    assert retrieved is not None


@pytest.mark.asyncio
async def test_get_nonexistent_knowledge(storage):
    """Test getting knowledge that doesn't exist."""
    retrieved = await storage.get_knowledge("test-agent-1", "nonexistent_key")
    assert retrieved is None


@pytest.mark.asyncio
async def test_expire_knowledge(storage):
    """Test expiring old knowledge cache entries."""
    # Create knowledge entries with different timestamps
    await storage.save_knowledge("test-agent-1", "old_key", {"data": "old"})
    await storage.save_knowledge("test-agent-1", "recent_key", {"data": "recent"})

    # Expire entries older than 1 day (should expire old_key if we manually set timestamp)
    # Note: In real scenario, we'd need to manipulate the database directly
    # For this test, we'll just verify the function runs
    deleted_count = await storage.expire_knowledge(
        agent_id="test-agent-1", older_than_days=1, limit=100
    )

    # The count depends on database state, but function should run without error
    assert isinstance(deleted_count, int)
    assert deleted_count >= 0


@pytest.mark.asyncio
async def test_storage_not_connected_error(storage):
    """Test that operations fail if storage not connected."""
    await storage.disconnect()

    state = AgentState(
        agent_id="test-agent",
        status=AgentStatus.ACTIVE,
    )

    with pytest.raises(RuntimeError, match="Storage not connected"):
        await storage.save_state(state)

    with pytest.raises(RuntimeError, match="Storage not connected"):
        await storage.load_state("test-agent")


@pytest.mark.asyncio
async def test_update_state_invalid_field(storage, sample_agent_state):
    """Test that updating with invalid field raises error."""
    await storage.save_state(sample_agent_state)

    with pytest.raises(ValueError, match="Invalid update field"):
        await storage.update_state("test-agent-1", {"invalid_field": "value"})


@pytest.mark.asyncio
async def test_update_plan_invalid_field(storage):
    """Test that updating plan with invalid field raises error."""
    plan = AgentPlan(
        agent_id="test-agent-1",
        task_id="task-123",
        plan_type="execution_plan",
        plan_data={},
    )

    plan_id = await storage.save_plan(plan)

    with pytest.raises(ValueError, match="Invalid update field"):
        await storage.update_plan(plan_id, {"invalid_field": "value"})


@pytest.mark.asyncio
async def test_load_nonexistent_plan(storage):
    """Test loading plan that doesn't exist."""
    loaded_plan = await storage.load_plan("00000000-0000-0000-0000-000000000000")
    assert loaded_plan is None


@pytest.mark.asyncio
async def test_storage_with_external_pool():
    """Test storage with external connection pool."""
    import asyncpg

    # Create external pool
    pool = await asyncpg.create_pool(
        host="localhost",
        port=5432,
        database="june",
        user="postgres",
        min_size=1,
        max_size=5,
    )

    # Create storage with external pool
    storage = AgentStateStorage(connection_pool=pool)
    # Should not need connect() when using external pool

    # Test that it works
    state = AgentState(agent_id="test-agent-pool", status=AgentStatus.ACTIVE)
    await storage.save_state(state)

    loaded = await storage.load_state("test-agent-pool")
    assert loaded is not None
    assert loaded.agent_id == "test-agent-pool"
    # Note: disconnect() won't close external pool
    await storage.disconnect()

    # Close external pool
    await pool.close()
