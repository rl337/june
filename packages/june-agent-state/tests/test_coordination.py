"""Tests for agent coordination and conflict prevention."""
import asyncio
import pytest
from datetime import datetime, timedelta

from june_agent_state.models import AgentStatus
from june_agent_state.coordination import AgentCoordination, ResourceLock
from june_agent_state.registry import AgentRegistry
from june_agent_state.storage import AgentStateStorage


@pytest.fixture
async def storage():
    """Create storage instance for testing."""
    storage = AgentStateStorage(
        host="localhost",
        port=5432,
        database="june",
        user="postgres",
        password=None,
    )
    await storage.connect()
    yield storage
    await storage.disconnect()


@pytest.fixture
async def registry(storage):
    """Create registry instance for testing."""
    return AgentRegistry(storage)


@pytest.fixture
async def coordination(registry, storage):
    """Create coordination instance for testing."""
    # Register test agents first
    await registry.register_agent("test-agent-1")
    await registry.update_agent_status("test-agent-1", AgentStatus.ACTIVE)
    await registry.register_agent("test-agent-2")
    await registry.update_agent_status("test-agent-2", AgentStatus.ACTIVE)
    
    return AgentCoordination(registry, storage, default_lock_timeout_seconds=60)


@pytest.mark.asyncio
async def test_acquire_exclusive_resource_lock(coordination):
    """Test acquiring an exclusive lock on a resource."""
    result = await coordination.acquire_resource_lock(
        "resource-1", "test-agent-1", lock_type="exclusive"
    )
    assert result is True
    
    # Verify lock exists
    locks = await coordination.get_resource_locks("resource-1")
    assert len(locks) == 1
    assert locks[0].agent_id == "test-agent-1"
    assert locks[0].lock_type == "exclusive"
    assert locks[0].is_valid() is True


@pytest.mark.asyncio
async def test_acquire_resource_lock_fails_if_resource_locked(coordination):
    """Test that acquiring a lock fails if resource is already locked."""
    # Acquire lock with agent 1
    await coordination.acquire_resource_lock("resource-1", "test-agent-1")
    
    # Try to acquire same lock with agent 2 (should fail)
    result = await coordination.acquire_resource_lock(
        "resource-1", "test-agent-2", wait=False
    )
    assert result is False


@pytest.mark.asyncio
async def test_acquire_shared_resource_lock(coordination):
    """Test acquiring shared locks (multiple agents can share)."""
    # Agent 1 acquires shared lock
    result1 = await coordination.acquire_resource_lock(
        "resource-1", "test-agent-1", lock_type="shared"
    )
    assert result1 is True
    
    # Agent 2 can also acquire shared lock
    result2 = await coordination.acquire_resource_lock(
        "resource-1", "test-agent-2", lock_type="shared", wait=False
    )
    assert result2 is True
    
    # Both locks should exist
    locks = await coordination.get_resource_locks("resource-1")
    assert len(locks) == 2


@pytest.mark.asyncio
async def test_shared_lock_blocked_by_exclusive(coordination):
    """Test that shared locks are blocked by exclusive locks."""
    # Acquire exclusive lock
    await coordination.acquire_resource_lock(
        "resource-1", "test-agent-1", lock_type="exclusive"
    )
    
    # Try to acquire shared lock (should fail)
    result = await coordination.acquire_resource_lock(
        "resource-1", "test-agent-2", lock_type="shared", wait=False
    )
    assert result is False


@pytest.mark.asyncio
async def test_exclusive_lock_blocked_by_shared(coordination):
    """Test that exclusive locks are blocked by shared locks."""
    # Acquire shared lock
    await coordination.acquire_resource_lock(
        "resource-1", "test-agent-1", lock_type="shared"
    )
    
    # Try to acquire exclusive lock (should fail)
    result = await coordination.acquire_resource_lock(
        "resource-1", "test-agent-2", lock_type="exclusive", wait=False
    )
    assert result is False


@pytest.mark.asyncio
async def test_release_resource_lock(coordination):
    """Test releasing a resource lock."""
    # Acquire lock
    await coordination.acquire_resource_lock("resource-1", "test-agent-1")
    
    # Release lock
    result = await coordination.release_resource_lock("resource-1", "test-agent-1")
    assert result is True
    
    # Verify lock is released
    locks = await coordination.get_resource_locks("resource-1")
    assert len(locks) == 0


@pytest.mark.asyncio
async def test_release_nonexistent_lock(coordination):
    """Test releasing a non-existent lock."""
    result = await coordination.release_resource_lock("resource-1", "test-agent-1")
    assert result is False


@pytest.mark.asyncio
async def test_release_all_agent_locks(coordination):
    """Test releasing all locks held by an agent."""
    # Acquire multiple locks
    await coordination.acquire_resource_lock("resource-1", "test-agent-1")
    await coordination.acquire_resource_lock("resource-2", "test-agent-1")
    await coordination.acquire_resource_lock("resource-3", "test-agent-1")
    
    # Release all locks
    count = await coordination.release_all_agent_locks("test-agent-1")
    assert count == 3
    
    # Verify all locks are released
    locks1 = await coordination.get_resource_locks("resource-1")
    locks2 = await coordination.get_resource_locks("resource-2")
    locks3 = await coordination.get_resource_locks("resource-3")
    assert len(locks1) == 0
    assert len(locks2) == 0
    assert len(locks3) == 0


@pytest.mark.asyncio
async def test_check_resource_available(coordination):
    """Test checking if a resource is available."""
    # Resource should be available initially
    available = await coordination.check_resource_available("resource-1")
    assert available is True
    
    # Acquire lock
    await coordination.acquire_resource_lock("resource-1", "test-agent-1")
    
    # Resource should not be available
    available = await coordination.check_resource_available("resource-1")
    assert available is False


@pytest.mark.asyncio
async def test_lock_expiration(coordination):
    """Test that locks expire after timeout."""
    # Acquire lock with short timeout
    result = await coordination.acquire_resource_lock(
        "resource-1", "test-agent-1", timeout_seconds=1
    )
    assert result is True
    
    # Verify lock exists
    locks = await coordination.get_resource_locks("resource-1")
    assert len(locks) == 1
    
    # Wait for expiration
    await asyncio.sleep(2)
    
    # Lock should be expired and cleaned up
    locks = await coordination.get_resource_locks("resource-1")
    assert len(locks) == 0
    
    # Resource should be available again
    available = await coordination.check_resource_available("resource-1")
    assert available is True


@pytest.mark.asyncio
async def test_coordinate_task_assignment(coordination):
    """Test coordinating task assignment by acquiring all required resources."""
    # Acquire all resources for a task
    required_resources = ["resource-1", "resource-2", "resource-3"]
    result = await coordination.coordinate_task_assignment(
        "task-1", "test-agent-1", required_resources
    )
    assert result is True
    
    # Verify all resources are locked
    for resource_id in required_resources:
        locks = await coordination.get_resource_locks(resource_id)
        assert len(locks) == 1
        assert locks[0].agent_id == "test-agent-1"


@pytest.mark.asyncio
async def test_coordinate_task_assignment_partial_failure(coordination):
    """Test that task assignment fails if not all resources can be acquired."""
    # Lock one resource with agent 2
    await coordination.acquire_resource_lock("resource-2", "test-agent-2")
    
    # Try to acquire all resources (should fail)
    required_resources = ["resource-1", "resource-2", "resource-3"]
    result = await coordination.coordinate_task_assignment(
        "task-1", "test-agent-1", required_resources
    )
    assert result is False
    
    # Verify no resources are locked by agent 1 (all should be released)
    locks1 = await coordination.get_resource_locks("resource-1")
    locks3 = await coordination.get_resource_locks("resource-3")
    assert len(locks1) == 0
    assert len(locks3) == 0
    
    # Resource 2 should still be locked by agent 2
    locks2 = await coordination.get_resource_locks("resource-2")
    assert len(locks2) == 1
    assert locks2[0].agent_id == "test-agent-2"


@pytest.mark.asyncio
async def test_handle_agent_failure(coordination):
    """Test handling agent failure by releasing locks."""
    # Agent acquires locks
    await coordination.acquire_resource_lock("resource-1", "test-agent-1")
    await coordination.acquire_resource_lock("resource-2", "test-agent-1")
    
    # Handle agent failure
    result = await coordination.handle_agent_failure(
        "test-agent-1", error_info={"error": "test error"}
    )
    assert result is True
    
    # Verify all locks are released
    locks1 = await coordination.get_resource_locks("resource-1")
    locks2 = await coordination.get_resource_locks("resource-2")
    assert len(locks1) == 0
    assert len(locks2) == 0
    
    # Verify agent status is ERROR
    agent_state = await coordination.registry.get_agent("test-agent-1")
    assert agent_state is not None
    assert agent_state.status == AgentStatus.ERROR


@pytest.mark.asyncio
async def test_check_task_assignment(coordination, registry):
    """Test checking task assignment."""
    # Assign task to agent
    await coordination.assign_task_to_agent("task-1", "test-agent-1")
    
    # Check assignment
    assigned_agent = await coordination.check_task_assignment("task-1")
    assert assigned_agent == "test-agent-1"
    
    # Check non-existent task
    result = await coordination.check_task_assignment("task-nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_assign_task_to_agent(coordination):
    """Test assigning a task to an agent."""
    result = await coordination.assign_task_to_agent("task-1", "test-agent-1")
    assert result is True
    
    # Verify task is assigned
    agent_state = await coordination.registry.get_agent("test-agent-1")
    assert agent_state is not None
    assert agent_state.current_task_id == "task-1"


@pytest.mark.asyncio
async def test_assign_task_conflict_prevention(coordination):
    """Test that task assignment conflicts are prevented."""
    # Assign task to agent 1
    result1 = await coordination.assign_task_to_agent("task-1", "test-agent-1")
    assert result1 is True
    
    # Try to assign same task to agent 2 (should fail)
    result2 = await coordination.assign_task_to_agent("task-1", "test-agent-2")
    assert result2 is False
    
    # Verify task is still assigned to agent 1
    assigned_agent = await coordination.check_task_assignment("task-1")
    assert assigned_agent == "test-agent-1"
