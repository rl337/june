"""
Tests for MCP Client.
"""
import json
import pytest
from unittest.mock import Mock, patch
import httpx

from june_mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPProtocolError,
    MCPServiceError,
    Task,
    TaskContext
)


@pytest.fixture
def client():
    """Create a test client."""
    return MCPClient(base_url="http://localhost:8004", api_key="test-key")


@pytest.fixture
def mock_response():
    """Create a mock response."""
    response = Mock(spec=httpx.Response)
    response.status_code = 200
    response.raise_for_status = Mock()
    return response


def test_client_initialization():
    """Test client initialization."""
    client = MCPClient()
    assert client.base_url == "http://localhost:8004"
    assert client.api_key is None
    assert client.timeout == 30.0
    assert client.max_retries == 3


def test_client_initialization_with_params():
    """Test client initialization with parameters."""
    client = MCPClient(
        base_url="http://example.com:8080",
        api_key="my-key",
        timeout=60.0,
        max_retries=5
    )
    assert client.base_url == "http://example.com:8080"
    assert client.api_key == "my-key"
    assert client.timeout == 60.0
    assert client.max_retries == 5


def test_get_headers(client):
    """Test header generation."""
    headers = client._get_headers()
    assert headers["Content-Type"] == "application/json"
    assert headers["X-API-Key"] == "test-key"


def test_get_headers_no_api_key():
    """Test header generation without API key."""
    client = MCPClient(base_url="http://localhost:8004")
    headers = client._get_headers()
    assert headers["Content-Type"] == "application/json"
    assert "X-API-Key" not in headers


@patch("httpx.Client")
def test_make_jsonrpc_request_success(mock_client_class, client, mock_response):
    """Test successful JSON-RPC request."""
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": "test-id",
        "result": {"success": True}
    }
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.post.return_value = mock_response
    mock_client_class.return_value = mock_client
    
    result = client._make_jsonrpc_request("test_method", {"param": "value"})
    
    assert result == {"success": True}
    mock_client.post.assert_called_once()


@patch("httpx.Client")
def test_make_jsonrpc_request_error(mock_client_class, client, mock_response):
    """Test JSON-RPC request with error response."""
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": "test-id",
        "error": {
            "code": -32603,
            "message": "Internal error"
        }
    }
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.post.return_value = mock_response
    mock_client_class.return_value = mock_client
    
    with pytest.raises(MCPServiceError) as exc_info:
        client._make_jsonrpc_request("test_method", {"param": "value"})
    
    assert exc_info.value.error.code == -32603
    assert exc_info.value.error.message == "Internal error"


@patch("httpx.Client")
def test_make_jsonrpc_request_connection_error(mock_client_class, client):
    """Test connection error handling."""
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.post.side_effect = httpx.RequestError("Connection failed")
    mock_client_class.return_value = mock_client
    
    with pytest.raises(MCPConnectionError):
        client._make_jsonrpc_request("test_method")


@patch("httpx.Client")
def test_make_jsonrpc_request_retry(mock_client_class, client, mock_response):
    """Test retry logic on server errors."""
    # First call fails with 500, second succeeds
    error_response = Mock(spec=httpx.Response)
    error_response.status_code = 500
    error_response.text = "Internal Server Error"
    error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error",
        request=Mock(),
        response=error_response
    )
    
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": "test-id",
        "result": {"success": True}
    }
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.post.side_effect = [error_response, mock_response]
    mock_client_class.return_value = mock_client
    
    result = client._make_jsonrpc_request("test_method")
    
    assert result == {"success": True}
    assert mock_client.post.call_count == 2


@patch.object(MCPClient, "_make_jsonrpc_request")
def test_list_available_tasks(mock_request, client):
    """Test list_available_tasks."""
    mock_request.return_value = {
        "content": [{
            "type": "text",
            "text": json.dumps([
                {
                    "id": 1,
                    "project_id": 1,
                    "title": "Test Task",
                    "task_type": "concrete",
                    "task_status": "available",
                    "task_instruction": "Do something",
                    "verification_instruction": "Verify it",
                    "verification_status": "unverified"
                }
            ])
        }]
    }
    
    tasks = client.list_available_tasks(agent_type="implementation", limit=10)
    
    assert len(tasks) == 1
    assert isinstance(tasks[0], Task)
    assert tasks[0].id == 1
    assert tasks[0].title == "Test Task"


@patch.object(MCPClient, "_make_jsonrpc_request")
def test_reserve_task(mock_request, client):
    """Test reserve_task."""
    mock_request.return_value = {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "task": {
                    "id": 1,
                    "project_id": 1,
                    "title": "Test Task",
                    "task_type": "concrete",
                    "task_status": "in_progress",
                    "task_instruction": "Do something",
                    "verification_instruction": "Verify it",
                    "verification_status": "unverified"
                },
                "project": None,
                "updates": [],
                "ancestry": [],
                "recent_changes": []
            })
        }]
    }
    
    context = client.reserve_task(task_id=1, agent_id="test-agent")
    
    assert isinstance(context, TaskContext)
    assert context.task.id == 1
    assert context.task.title == "Test Task"


@patch.object(MCPClient, "_make_jsonrpc_request")
def test_reserve_task_error(mock_request, client):
    """Test reserve_task with error response."""
    mock_request.return_value = {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "success": False,
                "error": "Task not found"
            })
        }]
    }
    
    with pytest.raises(MCPServiceError):
        client.reserve_task(task_id=999, agent_id="test-agent")


@patch.object(MCPClient, "_make_jsonrpc_request")
def test_complete_task(mock_request, client):
    """Test complete_task."""
    mock_request.return_value = {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "success": True,
                "task_id": 1
            })
        }]
    }
    
    result = client.complete_task(
        task_id=1,
        agent_id="test-agent",
        notes="Done!"
    )
    
    assert result["success"] is True
    assert result["task_id"] == 1


@patch.object(MCPClient, "_make_jsonrpc_request")
def test_add_task_update(mock_request, client):
    """Test add_task_update."""
    mock_request.return_value = {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "success": True,
                "update_id": 123
            })
        }]
    }
    
    result = client.add_task_update(
        task_id=1,
        agent_id="test-agent",
        content="Making progress",
        update_type="progress"
    )
    
    assert result["success"] is True
    assert result["update_id"] == 123


@patch.object(MCPClient, "_make_jsonrpc_request")
def test_query_tasks(mock_request, client):
    """Test query_tasks."""
    mock_request.return_value = {
        "content": [{
            "type": "text",
            "text": json.dumps([
                {
                    "id": 1,
                    "project_id": 1,
                    "title": "Task 1",
                    "task_type": "concrete",
                    "task_status": "in_progress",
                    "task_instruction": "Do something",
                    "verification_instruction": "Verify it",
                    "verification_status": "unverified"
                },
                {
                    "id": 2,
                    "project_id": 1,
                    "title": "Task 2",
                    "task_type": "concrete",
                    "task_status": "complete",
                    "task_instruction": "Do something else",
                    "verification_instruction": "Verify it",
                    "verification_status": "verified"
                }
            ])
        }]
    }
    
    tasks = client.query_tasks(task_status="in_progress", limit=100)
    
    assert len(tasks) == 2
    assert all(isinstance(task, Task) for task in tasks)


@patch.object(MCPClient, "_make_jsonrpc_request")
def test_get_agent_performance(mock_request, client):
    """Test get_agent_performance."""
    mock_request.return_value = {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "agent_id": "test-agent",
                "tasks_completed": 10,
                "tasks_created": 5,
                "average_completion_hours": 2.5,
                "success_rate": 0.9
            })
        }]
    }
    
    perf = client.get_agent_performance(agent_id="test-agent")
    
    assert perf.agent_id == "test-agent"
    assert perf.tasks_completed == 10
    assert perf.tasks_created == 5
