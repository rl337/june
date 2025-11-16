# Switchboard Service

The Switchboard service provides a formalized API for orchestrating and managing agent execution. It replaces the shell-script-based agent management in the agenticness repo with a programmatic interface.

## Features

- **Structured API**: RESTful API for sending requests to configured agents
- **Session Locking**: Prevents concurrent execution of the same agent session
- **Agent Lifecycle Management**: Handles agent creation, execution, and cleanup
- **Extensible Agent Types**: Support for different agent implementations (currently popen-based cursor agents)
- **Streaming Responses**: Real-time updates as agents execute
- **Synchronous and Asynchronous Execution**: Both streaming and blocking execution modes

## Architecture

### Agent Interface

All agents implement the `Agent` abstract base class:

```python
class Agent(ABC):
    async def execute(request: AgentRequest) -> AsyncIterator[AgentResponse]
    async def cancel(request_id: str) -> bool
    async def get_status(request_id: str) -> Optional[AgentResponse]
```

### Current Agent Types

- **PopenCursorAgent**: Executes cursor-agent via subprocess (current implementation)

### Future Agent Types

- **PTYCursorAgent**: Long-running interactive cursor agent via PTY
- **MultiTurnAgent**: Agent that maintains state across multiple turns
- **Custom Agents**: Any agent implementing the `Agent` interface

## API Endpoints

### Health Check

```bash
GET /health
```

Returns service health status.

### List Agents

```bash
GET /agents
```

Returns list of all registered agents.

### Execute Agent (Streaming)

```bash
POST /agents/{agent_id}/execute
Content-Type: application/json

{
  "agent_id": "telegram-response",
  "session_id": "user-123-chat-456",
  "message": "Hello, how can you help?",
  "context": {
    "user_id": 123,
    "chat_id": 456
  },
  "timeout": 3600
}
```

Returns Server-Sent Events (SSE) stream with execution updates.

### Execute Agent (Synchronous)

```bash
POST /agents/{agent_id}/execute/sync
Content-Type: application/json

{
  "agent_id": "telegram-response",
  "session_id": "user-123-chat-456",
  "message": "Hello, how can you help?",
  "context": {
    "user_id": 123,
    "chat_id": 456
  }
}
```

Returns final response after execution completes.

### Cancel Execution

```bash
POST /agents/{agent_id}/cancel/{request_id}
```

Cancels a running agent execution.

### Get Status

```bash
GET /agents/{agent_id}/status/{request_id}
```

Returns current status of an execution.

### Check Session Lock

```bash
GET /sessions/{session_id}/lock
```

Checks if a session is currently locked.

## Configuration

### Environment Variables

- `SWITCHBOARD_PORT`: Service port (default: 8082)
- `SWITCHBOARD_HOST`: Service host (default: 0.0.0.0)
- `SWITCHBOARD_LOCK_DIR`: Directory for lock files (default: /tmp/switchboard/locks)
- `SWITCHBOARD_CONFIG`: Path to agent configuration file (default: /etc/switchboard/agents.json)

### Agent Configuration File

Create `/etc/switchboard/agents.json`:

```json
{
  "telegram-response": {
    "type": "popen_cursor",
    "config": {
      "script_path": "/path/to/telegram_response_agent.sh",
      "script_simple_path": "/path/to/telegram_response_agent_simple.sh",
      "working_directory": "/path/to/work",
      "timeout": 3600,
      "use_simple": false
    }
  }
}
```

If no config file exists, defaults are used based on environment variables.

## Session Locking

The switchboard ensures that only one execution can run per session at a time. This prevents:

- Concurrent modifications to the same session
- Race conditions in stateful agents
- Resource conflicts

Locks are automatically released when execution completes or fails.

## Integration with Agenticness

The switchboard can integrate with the agenticness Python library for:

- Session management
- Agent coordination
- Resource locking
- Performance monitoring

## Usage Example

```python
import httpx

# Execute agent synchronously
response = httpx.post(
    "http://localhost:8082/agents/telegram-response/execute/sync",
    json={
        "agent_id": "telegram-response",
        "session_id": "user-123-chat-456",
        "message": "What can you do?",
        "context": {
            "user_id": 123,
            "chat_id": 456
        }
    }
)

result = response.json()
print(result["message"])
```

## Security: Non-Root User Requirement

**CRITICAL**: All services MUST run as non-root users. This is a mandatory security requirement.

**Implementation:**
- Docker containers must use `USER` directive to specify a non-root user (UID 1000 recommended)
- Docker Compose services must specify `user: "1000:1000"` in service definitions
- Host directories mounted as volumes must be owned by the non-root user (UID 1000)
- Never use `privileged: true` or run containers as root

**Verification:**
```bash
# Check container user (should return 1000:1000, never empty)
docker inspect <container> --format '{{.Config.User}}'
```

## Development

### Adding a New Agent Type

1. Create a new agent class inheriting from `Agent`:

```python
from switchboard.agents.base import Agent, AgentRequest, AgentResponse

class MyCustomAgent(Agent):
    @property
    def agent_type(self) -> str:
        return "my_custom"
    
    async def execute(self, request: AgentRequest) -> AsyncIterator[AgentResponse]:
        # Implementation
        pass
    
    async def cancel(self, request_id: str) -> bool:
        # Implementation
        pass
    
    async def get_status(self, request_id: str) -> Optional[AgentResponse]:
        # Implementation
        pass
```

2. Register the agent type:

```python
from switchboard.agent_registry import AgentRegistry

registry = AgentRegistry()
registry.register_agent_type("my_custom", MyCustomAgent)
```

3. Add configuration for the agent type in the config file.

## Future Enhancements

- [ ] PTY-based interactive agents
- [ ] Multi-turn conversation agents
- [ ] Agent health monitoring
- [ ] Metrics and observability
- [ ] Agent load balancing
- [ ] Priority queues for agent execution
- [ ] Agent resource limits and quotas



