# API Documentation

This directory contains comprehensive API documentation for all June services.

## Available Documentation

- **[Inference API](inference.md)** - LLM gRPC service (TensorRT-LLM, default) with request/response formats, streaming, embeddings
- **[STT Service](stt.md)** - Speech-to-text gRPC service with audio format requirements, streaming, language detection
- **[TTS Service](tts.md)** - Text-to-speech gRPC service with voice options, prosody control, streaming
- **[Telegram Bot API](telegram.md)** - Telegram bot integration with commands, message handling, webhook setup, admin commands
- **[TODO MCP Service](todo-mcp.md)** - Task management endpoints, MCP compatibility, relationships

**Note:** Gateway API was removed for MVP. Services now communicate directly via gRPC. See [gateway.md.obsolete](gateway.md.obsolete) for historical reference.

## Quick Reference

### gRPC Services
- Inference API: `tensorrt-llm:8000` (TensorRT-LLM, default) or `inference-api:50051` (legacy)
- STT Service: `localhost:50052`
- TTS Service: `localhost:50053`

### TODO Service
- Base URL: `http://localhost:8004`
- MCP-compatible endpoints available

## Getting Started

1. **Check Service Health**: Use gRPC health checks or HTTP health endpoints (if available) to verify services are running
2. **Read Service Docs**: Each service has detailed documentation with examples
3. **Use Examples**: All documentation includes Python gRPC examples
4. **Direct gRPC Access**: Services communicate directly via gRPC - no gateway required

## Common Patterns

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
