# API Documentation

This directory contains comprehensive API documentation for all June services.

## Available Documentation

- **[Gateway API](gateway.md)** - REST endpoints, WebSocket API, authentication, rate limiting
- **[Inference API](inference.md)** - gRPC methods, request/response formats, streaming, embeddings
- **[STT Service](stt.md)** - gRPC methods, audio format requirements, streaming, language detection
- **[TTS Service](tts.md)** - gRPC methods, voice options, prosody control, streaming
- **[Telegram Bot API](telegram.md)** - Commands, message handling, webhook setup, admin commands
- **[TODO MCP Service](todo-mcp.md)** - Task management endpoints, MCP compatibility, relationships

## Quick Reference

### Gateway Service
- Base URL: `http://localhost:8000`
- Authentication: JWT Bearer tokens
- Main endpoints: `/api/v1/audio/transcribe`, `/api/v1/llm/generate`, `/api/v1/tts/speak`, `/chat`
- WebSocket: `/ws/{user_id}`

### gRPC Services
- Inference API: `tensorrt-llm:8000` (TensorRT-LLM, default) or `inference-api:50051` (legacy)
- STT Service: `localhost:50052`
- TTS Service: `localhost:50053`

### TODO Service
- Base URL: `http://localhost:8004`
- MCP-compatible endpoints available

## Getting Started

1. **Authentication**: Start with `/auth/login` to get access tokens
2. **Check Health**: Use `/health` endpoints to verify services are running
3. **Read Service Docs**: Each service has detailed documentation with examples
4. **Use Examples**: All documentation includes curl and Python examples

## Common Patterns

### Authentication Flow
```python
# 1. Login
response = requests.post("http://localhost:8000/auth/login", json={"username": "user", "password": "pass"})
tokens = response.json()

# 2. Use token
headers = {"Authorization": f"Bearer {tokens['access_token']}"}
response = requests.get("http://localhost:8000/health", headers=headers)
```

### gRPC Client Usage
```python
import grpc
from june_grpc_api import llm as llm_shim

# Default: TensorRT-LLM (tensorrt-llm:8000)
# Legacy: inference-api (inference-api:50051)
async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
    client = llm_shim.LLMClient(channel)
    response = await client.generate(request)
```

### Task Management
```python
# List available tasks
tasks = requests.get("http://localhost:8004/agents/implementation/available-tasks").json()

# Reserve and complete
requests.post(f"http://localhost:8004/tasks/{task_id}/lock", json={"agent_id": "agent-1"})
# ... work on task ...
requests.post(f"http://localhost:8004/tasks/{task_id}/complete", json={"agent_id": "agent-1"})
```

## See Also

- [Main README](../../README.md) - Project overview
- [Architecture Documentation](../architecture/) - System architecture
- [Deployment Guides](../DEPLOYMENT.md) - Deployment instructions
