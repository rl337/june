# June MCP Client

Python client library for interacting with the TODO MCP Service using the Model Context Protocol (MCP) over JSON-RPC 2.0.

## Installation

```bash
pip install -e .
```

Or install with development dependencies:

```bash
pip install -e ".[dev]"
```

## Usage

```python
from june_mcp_client import MCPClient

# Initialize client
client = MCPClient(
    base_url="http://localhost:8004",
    api_key="your-api-key"  # Optional
)

# List available tasks
tasks = client.list_available_tasks(
    agent_type="implementation",
    project_id=1,
    limit=10
)

# Reserve a task
context = client.reserve_task(
    task_id=123,
    agent_id="my-agent"
)

# Add an update
client.add_task_update(
    task_id=123,
    agent_id="my-agent",
    content="Making progress...",
    update_type="progress"
)

# Complete a task
client.complete_task(
    task_id=123,
    agent_id="my-agent",
    notes="Completed successfully!"
)
```

## Configuration

The client can be configured via environment variables:

- `TODO_SERVICE_URL`: Base URL of TODO service (default: `http://localhost:8004`)
- `TODO_API_KEY`: API key for authentication (optional)

## Error Handling

The client provides several exception types:

- `MCPClientError`: Base exception for all client errors
- `MCPConnectionError`: Connection errors (network, timeout, etc.)
- `MCPProtocolError`: JSON-RPC protocol errors
- `MCPServiceError`: Service errors from the MCP server

Example:

```python
from june_mcp_client import MCPClient, MCPServiceError

try:
    client = MCPClient()
    context = client.reserve_task(task_id=123, agent_id="my-agent")
except MCPServiceError as e:
    print(f"Service error: {e.error.message}")
except MCPConnectionError as e:
    print(f"Connection error: {e}")
```

## Features

- ? Full JSON-RPC 2.0 protocol support
- ? Automatic retry logic for transient failures
- ? Type hints throughout
- ? Comprehensive error handling
- ? Support for all MCP functions
- ? Easy-to-use Python API

## Development

Run tests:

```bash
pytest
```

With coverage:

```bash
pytest --cov=june_mcp_client --cov-report=html
```
