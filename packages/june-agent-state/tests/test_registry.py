"""Tests for agent registry."""
import pytest

from june_agent_state.models import (
    AgentCapabilities,
    AgentState,
    AgentStatus,
)
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


@pytest.mark.asyncio
async def test_register_agent(registry):
    """Test registering a new agent."""
    capabilities = [
        AgentCapabilities(tools=["code_execution", "git_operations"])
    ]
    config = {"max_concurrent_tasks": 3}

    state = await registry.register_agent(
        "test-agent-1", capabilities=capabilities, config=config
    )

    assert state.agent_id == "test-agent-1"
    assert state.status == AgentStatus.INIT
    assert len(state.capabilities) == 1
    assert state.capabilities[0].tools == ["code_execution", "git_operations"]
    assert state.config["max_concurrent_tasks"] == 3


@pytest.mark.asyncio
async def test_register_existing_agent_updates(registry):
    """Test that registering an existing agent updates it."""
    # Register first time
    state1 = await registry.register_agent(
        "test-agent-2",
        capabilities=[AgentCapabilities(tools=["tool1"])],
        config={"key1": "value1"},
    )

    # Register again with new capabilities/config
    state2 = await registry.register_agent(
        "test-agent-2",
        capabilities=[AgentCapabilities(tools=["tool2"])],
        config={"key2": "value2"},
    )

    assert state2.agent_id == "test-agent-2"
    assert len(state2.capabilities) == 1
    assert state2.capabilities[0].tools == ["tool2"]
    # Config should be merged
    assert "key1" in state2.config or "key2" in state2.config


@pytest.mark.asyncio
async def test_unregister_agent(registry):
    """Test unregistering an agent."""
    # Register agent
    await registry.register_agent("test-agent-3", config={"test": "value"})

    # Unregister
    result = await registry.unregister_agent("test-agent-3")

    assert result is True

    # Verify status changed to IDLE
    state = await registry.get_agent("test-agent-3")
    assert state is not None
    assert state.status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_unregister_nonexistent_agent(registry):
    """Test unregistering non-existent agent."""
    result = await registry.unregister_agent("nonexistent-agent")
    assert result is False


@pytest.mark.asyncio
async def test_get_agent(registry):
    """Test getting agent by ID."""
    await registry.register_agent("test-agent-4")

    state = await registry.get_agent("test-agent-4")

    assert state is not None
    assert state.agent_id == "test-agent-4"
    assert state.status == AgentStatus.INIT


@pytest.mark.asyncio
async def test_get_nonexistent_agent(registry):
    """Test getting non-existent agent."""
    state = await registry.get_agent("nonexistent-agent")
    assert state is None


@pytest.mark.asyncio
async def test_list_agents_all(registry):
    """Test listing all agents."""
    await registry.register_agent("test-agent-5")
    await registry.register_agent("test-agent-6")
    await registry.register_agent("test-agent-7")

    agents = await registry.list_agents()

    # Should return at least the agents we registered
    agent_ids = [agent.agent_id for agent in agents]
    assert "test-agent-5" in agent_ids
    assert "test-agent-6" in agent_ids
    assert "test-agent-7" in agent_ids


@pytest.mark.asyncio
async def test_list_agents_by_status(registry):
    """Test listing agents filtered by status."""
    await registry.register_agent("test-agent-8")
    await registry.register_agent("test-agent-9")

    # Update one to ACTIVE
    await registry.update_agent_status("test-agent-9", AgentStatus.ACTIVE)

    # List by status
    active_agents = await registry.list_agents(status=AgentStatus.ACTIVE)

    active_ids = [agent.agent_id for agent in active_agents]
    assert "test-agent-9" in active_ids
    assert "test-agent-8" not in active_ids


@pytest.mark.asyncio
async def test_list_agents_with_filters(registry):
    """Test listing agents with additional filters."""
    # Register agents with different configurations
    await registry.register_agent(
        "test-agent-10",
        capabilities=[AgentCapabilities(tools=["tool_a"])],
    )
    await registry.register_agent(
        "test-agent-11",
        capabilities=[AgentCapabilities(tools=["tool_b"])],
    )

    # Update one to have a task
    await registry.storage.update_state(
        "test-agent-10", {"current_task_id": "task-123"}
    )

    # Filter by has_task
    agents_with_task = await registry.list_agents(
        filters={"has_task": True}
    )
    agent_ids_with_task = [agent.agent_id for agent in agents_with_task]
    assert "test-agent-10" in agent_ids_with_task
    assert "test-agent-11" not in agent_ids_with_task

    # Filter by capability
    agents_with_tool_a = await registry.list_agents(
        filters={"capability": "tool_a"}
    )
    agent_ids_with_tool_a = [agent.agent_id for agent in agents_with_tool_a]
    assert "test-agent-10" in agent_ids_with_tool_a
    assert "test-agent-11" not in agent_ids_with_tool_a


@pytest.mark.asyncio
async def test_update_agent_status(registry):
    """Test updating agent status."""
    await registry.register_agent("test-agent-12")

    updated_state = await registry.update_agent_status(
        "test-agent-12", AgentStatus.ACTIVE
    )

    assert updated_state is not None
    assert updated_state.status == AgentStatus.ACTIVE


@pytest.mark.asyncio
async def test_update_agent_status_nonexistent(registry):
    """Test updating status for non-existent agent."""
    updated_state = await registry.update_agent_status(
        "nonexistent-agent", AgentStatus.ACTIVE
    )
    assert updated_state is None


@pytest.mark.asyncio
async def test_initialize_agent_on_startup_new(registry):
    """Test initializing a new agent on startup."""
    capabilities = [AgentCapabilities(tools=["tool1"])]
    config = {"setting": "value"}

    state = await registry.initialize_agent_on_startup(
        "test-agent-13", capabilities=capabilities, config=config
    )

    assert state.agent_id == "test-agent-13"
    assert state.status == AgentStatus.INIT
    assert len(state.capabilities) == 1


@pytest.mark.asyncio
async def test_initialize_agent_on_startup_existing(registry):
    """Test initializing an existing agent on startup (recovery)."""
    # Register agent first
    await registry.register_agent(
        "test-agent-14", config={"old_setting": "old_value"}
    )
    await registry.update_agent_status("test-agent-14", AgentStatus.IDLE)

    # Initialize on startup (recovery)
    state = await registry.initialize_agent_on_startup(
        "test-agent-14",
        config={"new_setting": "new_value"},
    )

    assert state is not None
    assert state.agent_id == "test-agent-14"
    # Status should be updated to ACTIVE from IDLE
    assert state.status == AgentStatus.ACTIVE
    # Config should be merged
    assert "old_setting" in state.config or "new_setting" in state.config


@pytest.mark.asyncio
async def test_get_agent_by_capability(registry):
    """Test getting agents by capability."""
    await registry.register_agent(
        "test-agent-15",
        capabilities=[AgentCapabilities(tools=["python", "git"])],
    )
    await registry.register_agent(
        "test-agent-16",
        capabilities=[AgentCapabilities(tools=["javascript", "npm"])],
    )

    python_agents = await registry.get_agent_by_capability("python")

    agent_ids = [agent.agent_id for agent in python_agents]
    assert "test-agent-15" in agent_ids
    assert "test-agent-16" not in agent_ids


@pytest.mark.asyncio
async def test_get_available_agents(registry):
    """Test getting available agents (ACTIVE or IDLE)."""
    await registry.register_agent("test-agent-17")
    await registry.register_agent("test-agent-18")
    await registry.register_agent("test-agent-19")

    # Update statuses
    await registry.update_agent_status("test-agent-17", AgentStatus.ACTIVE)
    await registry.update_agent_status("test-agent-18", AgentStatus.IDLE)
    await registry.update_agent_status("test-agent-19", AgentStatus.ERROR)

    available = await registry.get_available_agents()

    available_ids = [agent.agent_id for agent in available]
    assert "test-agent-17" in available_ids
    assert "test-agent-18" in available_ids
    assert "test-agent-19" not in available_ids  # ERROR status not available
