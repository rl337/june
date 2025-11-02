# Orchestration Service

Orchestration and coordination service for June agents. Provides the control plane for the agentic system.

## Features

- **Agent Lifecycle Management**: Register, start, stop agents
- **Task Distribution**: Automatically assign tasks to available agents
- **Health Monitoring**: Track agent health via heartbeats
- **Coordination**: Prevent conflicts between agents
- **Metrics**: Prometheus metrics for monitoring
- **Configuration**: Manage agent configurations

## API Endpoints

### Health & Monitoring
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `GET /stats` - System statistics

### Agent Management
- `POST /agents/register` - Register a new agent
- `GET /agents` - List all agents
- `GET /agents/{agent_id}` - Get agent information
- `POST /agents/{agent_id}/start` - Start an agent
- `POST /agents/{agent_id}/stop` - Stop an agent
- `POST /agents/{agent_id}/heartbeat` - Agent heartbeat

### Task Management
- `POST /tasks/assign` - Assign a task to an agent
- `POST /tasks/{task_id}/complete` - Mark task as complete
- `GET /tasks/pending` - List pending tasks

## Environment Variables

- `ORCHESTRATOR_PORT` - Service port (default: 8005)
- `TODO_SERVICE_URL` - TODO MCP Service URL (default: http://localhost:8004)
- `GATEWAY_URL` - June Gateway URL (default: http://localhost:8000)
- `LOG_LEVEL` - Logging level (default: INFO)

## Usage

### Run with Docker

```bash
docker build -t june-orchestrator:latest .
docker run -p 8005:8005 june-orchestrator:latest
```

### Run directly

```bash
pip install -r requirements.txt
python main.py
```

### Register an Agent

```bash
curl -X POST http://localhost:8005/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "agent_type": "implementation",
    "capabilities": ["code", "git", "testing"]
  }'
```

### Start Agent

```bash
curl -X POST http://localhost:8005/agents/my-agent/start
```

### Assign Task

```bash
curl -X POST http://localhost:8005/tasks/assign \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 123,
    "agent_id": "my-agent"
  }'
```

## Architecture

The orchestration service manages:
- **Agent Registry**: Track all registered agents and their status
- **Task Queue**: Queue pending tasks when no agents are available
- **Resource Locks**: Prevent conflicts when multiple agents access shared resources
- **Health Monitoring**: Periodic health checks and heartbeat tracking

## Integration

The orchestrator integrates with:
- **TODO MCP Service**: Query and assign tasks
- **June Gateway**: Coordinate agent execution
- **Prometheus**: Expose metrics for monitoring
