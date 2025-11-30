# Switchboard Service

Agent-as-a-Service API for the June project. Provides a REST API for executing AI agents via the agenticness framework.

## Overview

The Switchboard service allows other June services (Telegram, Discord, etc.) to invoke AI agents through a standardized API. It manages agent execution, session locking, and provides both streaming and synchronous execution modes.

## Features

- **REST API**: Standardized endpoints for agent execution
- **CRUD Operations**: Create, read, update, and delete agents dynamically
- **Agent Metadata**: Name, description, tags, and system prompts
- **Busy Status Tracking**: Prevents concurrent execution and tracks active requests
- **Tag Filtering**: List agents by tags for easy discovery
- **Session Locking**: Prevents concurrent execution of the same agent session
- **Streaming Support**: Real-time updates via Server-Sent Events (SSE)
- **Synchronous Mode**: Blocking execution for simple use cases
- **Role-Based Sessions**: Uses role-based session management (e.g., `telegram-{user_id}-{chat_id}`)
- **Configuration Persistence**: Automatically saves agent configurations to file

## Configuration

### Agent Configuration File

Create `/app/config/agents.json` in the container (mounted from host):

```json
{
  "telegram-response": {
    "type": "popen_cursor",
    "name": "Telegram Response Agent",
    "description": "Handles Telegram user messages and responds via cursor-agent",
    "tags": ["telegram", "user-interface", "response"],
    "system_prompt": "You are a helpful assistant...",
    "config": {
      "script_path": "/app/scripts/telegram_response_agent.sh",
      "script_simple_path": "/app/scripts/telegram_response_agent_simple.sh",
      "working_directory": "/app",
      "timeout": 300,
      "use_simple": false
    }
  },
  "looping-agent": {
    "type": "popen_cursor",
    "name": "Looping Agent",
    "description": "Continuously processes tasks from Todorama",
    "tags": ["task-management", "looping"],
    "config": {
      "script_path": "/app/scripts/refactor_agent_loop.sh",
      "working_directory": "/app",
      "timeout": 3600,
      "use_simple": false
    }
  }
}
```

**Note:** The configuration file is automatically updated when agents are created, updated, or deleted via the API.

### Environment Variables

- `SWITCHBOARD_PORT`: Service port (default: 8082)
- `SWITCHBOARD_HOST`: Service host (default: 0.0.0.0)
- `SWITCHBOARD_LOCK_DIR`: Directory for lock files (default: `/data/locks`)
- `SWITCHBOARD_CONFIG`: Path to agent configuration file (default: `/app/config/agents.json`)
- `AGENTICNESS_DATA_DIR`: Directory for agenticness state (default: `/data`)
- `CURSOR_AGENT_EXE`: Path to cursor-agent executable (default: `cursor-agent`)
- `AGENT_TIMEOUT`: Default timeout in seconds (default: 3600)

## API Endpoints

All endpoints are accessible via the common nginx instance at `/switchboard/*`:

### Health Check
```
GET /switchboard/health
# Or directly: GET http://june-switchboard:8082/health
```

### List Agents
```
GET /switchboard/agents?tags=tag1,tag2
# Or directly: GET http://june-switchboard:8082/agents?tags=tag1,tag2
```

Returns list of all agents, optionally filtered by tags.

### Get Agent
```
GET /switchboard/agents/{agent_id}
# Or directly: GET http://june-switchboard:8082/agents/{agent_id}
```

Returns detailed information about a specific agent, including metadata and busy status.

### Create Agent
```
POST /switchboard/agents
Content-Type: application/json

{
  "agent_id": "my-agent",
  "agent_type": "popen_cursor",
  "name": "My Custom Agent",
  "description": "Does something useful",
  "tags": ["custom", "utility"],
  "system_prompt": "You are a helpful assistant...",
  "config": {
    "script_path": "/app/scripts/my_agent.sh",
    "working_directory": "/app",
    "timeout": 3600
  }
}
```

Creates a new agent. Returns `409 Conflict` if agent already exists.

### Update Agent
```
PUT /switchboard/agents/{agent_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description",
  "tags": ["updated", "tags"],
  "system_prompt": "Updated prompt...",
  "config": {
    "timeout": 7200
  }
}
```

Updates an existing agent. Only provided fields are updated. Returns `409 Conflict` if agent is busy.

### Delete Agent
```
DELETE /switchboard/agents/{agent_id}
# Or directly: DELETE http://june-switchboard:8082/agents/{agent_id}
```

Deletes an agent. Returns `409 Conflict` if agent is busy.

**See [SWITCHBOARD_CRUD.md](../../docs/SWITCHBOARD_CRUD.md) for detailed CRUD documentation.**

### Execute Agent (Synchronous)
```
POST /switchboard/agents/{agent_id}/execute/sync
Content-Type: application/json

{
  "agent_id": "telegram-response",
  "message": "User message here",
  "context": {
    "user_id": "123456789",
    "chat_id": "123456789",
    "platform": "telegram"
  },
  "timeout": 300
}
```

Returns: Final response JSON

### Execute Agent (Streaming)
```
POST /switchboard/agents/{agent_id}/execute
Content-Type: application/json

{
  "agent_id": "telegram-response",
  "message": "User message here",
  "context": {
    "user_id": "123456789",
    "chat_id": "123456789",
    "platform": "telegram"
  },
  "timeout": 300
}
```

Returns: Server-Sent Events (SSE) stream with real-time updates

**Note:** For streaming, use `/switchboard/sse` endpoint which is optimized for SSE.

### Cancel Execution
```
POST /switchboard/agents/{agent_id}/cancel/{request_id}
```

### Get Status
```
GET /switchboard/agents/{agent_id}/status/{request_id}
```

### Check Session Lock
```
GET /switchboard/sessions/{session_id}/lock
```

## Integration with June Services

### Telegram Service Integration

The Telegram service can call switchboard via the shared network:

```python
import httpx

async def handle_user_message(user_id: str, chat_id: str, message: str):
    async with httpx.AsyncClient() as client:
        # Use service name on shared-network
        response = await client.post(
            "http://june-switchboard:8082/agents/telegram-response/execute/sync",
            json={
                "agent_id": "telegram-response",
                "message": message,
                "context": {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "platform": "telegram"
                },
                "timeout": 300
            },
            timeout=310.0
        )
        result = response.json()
        return result["output"]
```

**Note:** Services on the `shared-network` should use `http://june-switchboard:8082` for direct access, or go through nginx at `http://common-nginx/switchboard/` if accessing from outside the network.

## Session Management

The switchboard service uses role-based session management:
- Session ID format: `telegram-{user_id}-{chat_id}` for Telegram
- Each user/chat combination gets its own isolated session
- Sessions persist across invocations for context preservation

## Busy Status

Agents track their busy status:
- **is_busy**: `true` if the agent has active requests
- **active_requests**: Number of currently active requests

When an agent is busy:
- New execution requests return `409 Conflict` with "Agent is currently busy"
- Update and delete operations return `409 Conflict` if agent is busy

## Security

- Runs as non-root user (UID 1000)
- Session locking prevents concurrent execution
- Timeout enforcement prevents runaway processes

