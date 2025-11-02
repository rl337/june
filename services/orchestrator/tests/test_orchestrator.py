"""
Tests for orchestration service.
"""
import pytest
from fastapi.testclient import TestClient
from main import app, OrchestrationService


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def service():
    """Create service instance."""
    return OrchestrationService()


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "active_agents" in data
    assert "total_agents" in data


def test_register_agent(client):
    """Test agent registration."""
    response = client.post(
        "/agents/register",
        json={
            "agent_id": "test-agent-1",
            "agent_type": "implementation",
            "capabilities": ["code", "git"],
            "metadata": {}
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "test-agent-1"
    assert data["status"] == "registered"


def test_register_duplicate_agent(client):
    """Test registering duplicate agent fails."""
    client.post(
        "/agents/register",
        json={
            "agent_id": "test-agent-2",
            "agent_type": "implementation"
        }
    )
    
    response = client.post(
        "/agents/register",
        json={
            "agent_id": "test-agent-2",
            "agent_type": "implementation"
        }
    )
    assert response.status_code == 409


def test_start_agent(client):
    """Test starting an agent."""
    client.post(
        "/agents/register",
        json={
            "agent_id": "test-agent-3",
            "agent_type": "implementation"
        }
    )
    
    response = client.post("/agents/test-agent-3/start")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"


def test_stop_agent(client):
    """Test stopping an agent."""
    client.post(
        "/agents/register",
        json={
            "agent_id": "test-agent-4",
            "agent_type": "implementation"
        }
    )
    
    client.post("/agents/test-agent-4/start")
    response = client.post("/agents/test-agent-4/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"


def test_list_agents(client):
    """Test listing agents."""
    client.post(
        "/agents/register",
        json={
            "agent_id": "test-agent-5",
            "agent_type": "implementation"
        }
    )
    
    response = client.get("/agents")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert len(data["agents"]) >= 1


def test_assign_task(client):
    """Test task assignment."""
    client.post(
        "/agents/register",
        json={
            "agent_id": "test-agent-6",
            "agent_type": "implementation"
        }
    )
    
    client.post("/agents/test-agent-6/start")
    
    response = client.post(
        "/tasks/assign",
        json={
            "task_id": 123,
            "agent_id": "test-agent-6"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "assigned"
    assert data["agent_id"] == "test-agent-6"


def test_assign_task_auto_select(client):
    """Test automatic agent selection for task."""
    client.post(
        "/agents/register",
        json={
            "agent_id": "test-agent-7",
            "agent_type": "implementation"
        }
    )
    
    client.post("/agents/test-agent-7/start")
    
    response = client.post(
        "/tasks/assign",
        json={
            "task_id": 456
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "assigned"


def test_metrics_endpoint(client):
    """Test metrics endpoint."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_statistics(client):
    """Test statistics endpoint."""
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_agents" in data
    assert "active_agents" in data
    assert "pending_tasks" in data
