# June Development Plan

## Status: ✅ **PRODUCTION READY**

**Last Updated:** 2025-11-21

**Current State:**
- ✅ **All code implementation complete** (419 tests passing locally, 1 skipped, 32 deselected)
- ✅ **All infrastructure ready** (commands, tools, documentation)
- ✅ **GitHub Actions:** Latest runs successful
- ✅ **System production-ready** - All services operational

## Task Management

**All tasks are managed in todorama (project_id=1).**

- Use MCP todorama service to query, reserve, and complete tasks
- User interactions from Telegram/Discord create todorama tasks automatically
- Agent loop processes tasks from todorama exclusively
- No task management in this file - all tasks are in todorama

## Architecture Overview

### Essential Services

1. **telegram** - Receives voice messages from Telegram, orchestrates pipeline
2. **discord** - Receives voice messages from Discord, orchestrates pipeline
3. **stt** - Speech-to-text conversion (Whisper via TensorRT-LLM)
4. **tts** - Text-to-speech conversion (FastSpeech2/espeak via TensorRT-LLM)

**LLM Inference:** 
- **Current implementation:** TensorRT-LLM container (from home_infra shared-network) - optimized GPU inference
- **Alternative:** NVIDIA NIM (nim-qwen3:8001) - pre-built containers
- **Legacy:** inference-api service (disabled by default, available via legacy profile for backward compatibility)

### Infrastructure

**No Infrastructure Required for MVP:**
- All services communicate via gRPC directly
- Conversation storage: In-memory (in telegram/discord services)
- Rate limiting: In-memory (in telegram/discord services)

**Optional Infrastructure (from home_infra):**
- **TensorRT-LLM** - LLM inference service (Triton Inference Server) - available in shared-network as `tensorrt-llm:8000` (default)
- **NVIDIA NIM** - Pre-built LLM inference containers - available in shared-network as `nim-qwen3:8001` (alternative)
- **Jaeger** - Distributed tracing (OpenTelemetry) - available in shared-network
- **Prometheus + Grafana** - Metrics collection and visualization - available in shared-network
- **nginx** - Reverse proxy (replaces removed gateway service) - available in shared-network

## Architecture Principles

### Minimal Architecture
- **Essential services only:** telegram, discord, stt, tts, TensorRT-LLM (via home_infra)
- **LLM inference:** TensorRT-LLM container (from home_infra shared-network) - optimized GPU inference
- **No external dependencies:** All services communicate via gRPC directly
- **In-memory alternatives:** Conversation storage and rate limiting use in-memory implementations
- **Container-first:** All operations run in Docker containers - no host system pollution
- **Command pattern:** All services follow `python -m essence <service-name>` pattern

### Code Organization
- **Service code:** `essence/services/<service-name>/` - Actual service implementation
- **Service config:** `services/<service-name>/` - Dockerfiles and service-specific configuration
- **Shared code:** `essence/chat/` - Shared utilities for telegram and discord
- **Commands:** `essence/commands/` - Reusable tools runnable via `poetry run python -m essence <command-name>`
- **Scripts:** `scripts/` - Shell scripts for complex container operations and automation only
- **Tests:** `tests/` - All test code, runnable via pytest

### Testing Philosophy
- **Unit tests:** Classic unit tests with all external services/libraries mocked
- **Integration tests:** Run in background, checked periodically via test service (not waited on)
- **Test service:** REST interface and logs for checking integration test runs
- **All tests runnable via pytest:** No custom test runners - use pytest for everything

### Observability
- **OpenTelemetry tracing:** Implemented across all services
- **Prometheus metrics:** Implemented and exposed
- **Health checks:** All services have health check endpoints

## User Interaction Flow

**Telegram/Discord → Todorama Tasks:**
1. Owner user sends message via Telegram/Discord
2. Service creates todorama task (via `create-user-interaction-task` command)
3. Agent loop processes task from todorama
4. Agent generates response and sends via Message API
5. Agent marks task as complete in todorama

**No USER_MESSAGES.md files** - All user interactions are managed as todorama tasks.

## Reference Documents

- **QWEN3_SETUP_PLAN.md** - Detailed Qwen3 setup instructions
- **AGENTS.md** - Agent development guidelines
- **docs/guides/** - Additional documentation

## Migration Notes

**Recent Changes (2025-11-21):**
- ✅ Migrated from USER_MESSAGES.md file-based approach to todorama task management
- ✅ Updated Telegram/Discord services to create todorama tasks
- ✅ Updated agent loop to only use todorama for task management
- ✅ Removed REFACTOR_PLAN.md task management (all tasks now in todorama)

**Future Work:**
- Migrate TTS/STT from NIMs to TensorRT-LLM with HuggingFace models (see todorama task #19)
