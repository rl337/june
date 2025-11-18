# June Refactoring Plan

## Goal
Pare down the june project to bare essentials for the **voice message → STT → LLM → TTS → voice response** round trip, supporting both **Telegram** and **Discord** platforms.

**Extended Goal:** Get Qwen3-30B-A3B-Thinking-2507 running on GPU in containers and develop a capable locally-run coding agent for evaluation on public benchmark datasets. **All operations must be containerized** - no host system pollution.

## Core Principles (Established from Completed Work)

### Minimal Architecture
- **Essential services only:** telegram, discord, stt, tts, inference-api
- **No external dependencies:** All services communicate via gRPC directly
- **In-memory alternatives:** Conversation storage and rate limiting use in-memory implementations
- **Container-first:** All operations run in Docker containers - no host system pollution
- **Command pattern:** All services follow `python -m essence <service-name>` pattern

### Code Organization
- **Service code:** `essence/services/<service-name>/` - Actual service implementation
- **Service config:** `services/<service-name>/` - Dockerfiles and service-specific configuration
- **Shared code:** `essence/chat/` - Shared utilities for telegram and discord
- **Commands:** `essence/commands/` - Reusable tools runnable via `poetry run -m essence <command-name>`
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

## Completed Work Summary

### Phase 1-3: Service Removal and Cleanup ✅
- Removed non-essential services: gateway, postgres, minio, redis, nats, orchestrator, webapp
- Removed all code dependencies on removed services
- Cleaned up service directories
- **Best Practice:** Keep architecture minimal - only essential services for core functionality

### Phase 4-5: Observability ✅
- Implemented OpenTelemetry tracing across all services
- Implemented Prometheus metrics and exposed endpoints
- **Best Practice:** Always add tracing and metrics to new services

### Phase 6: Package Simplification ✅
- Removed unused packages (june-agent-state, june-agent-tools, june-cache, june-mcp-client, june-metrics)
- Migrated from wheel builds to Poetry in-place installation
- **Best Practice:** Only keep packages that are actively used; use editable installs for development

### Phase 7: Documentation Cleanup ✅
- Simplified README.md to reflect minimal architecture
- Removed references to removed services
- **Best Practice:** Keep documentation minimal and aligned with actual architecture

### Phase 9.1: Service Refactoring ✅
- All services refactored to use Command pattern
- All services work without external dependencies
- **Best Practice:** All services must follow Command pattern and work independently

### Phase 10: Qwen3 Setup and Coding Agent ✅
- Qwen3-30B model setup on GPU in containers
- Coding agent interface with tool calling
- Benchmark evaluation framework with sandbox isolation
- **Best Practice:** All model operations must be containerized; use sandboxes for benchmark isolation

### Phase 11: Scripts Directory Cleanup and Command Migration ✅
- All reusable Python tools converted to commands
- All test utilities moved to tests/scripts/
- All obsolete scripts removed
- Documentation updated
- **Best Practice:** Keep scripts/ minimal - only infrastructure/automation scripts; use commands for reusable tools

## Current Priorities

### Phase 12: Test Infrastructure and Integration Test Service ⏳ TODO

**Goal:** Establish proper test infrastructure with unit tests (mocked) and integration tests (background service).

**Unit Test Requirements:**
- ⏳ All unit tests must mock external services and libraries
- ⏳ All tests runnable via pytest
- ⏳ No dependencies on running services for unit tests
- ⏳ Fast execution (< 1 minute for full suite)

**Integration Test Service:**
- ⏳ Create integration test service that runs tests in background
- ⏳ REST API for:
  - Starting test runs
  - Checking test run status
  - Retrieving test results
  - Viewing test logs
- ⏳ Log aggregation for test runs
- ⏳ Test run history and results storage
- ⏳ Health check endpoint for test service status

**Integration Test Requirements:**
- ⏳ All integration tests run in background (not waited on)
- ⏳ Tests check end-to-end functionality with real services
- ⏳ Tests can be checked periodically via REST API or logs
- ⏳ Test failures are logged and retrievable via API

**Tasks:**
1. **Create integration test service:**
   - ⏳ Design REST API for test management
   - ⏳ Implement test runner that executes tests in background
   - ⏳ Implement result storage and retrieval
   - ⏳ Add health check endpoint

2. **Migrate existing integration tests:**
   - ⏳ Identify current integration tests
   - ⏳ Ensure they can run in background
   - ⏳ Update to use test service API

3. **Documentation:**
   - ⏳ Document how to run unit tests (pytest)
   - ⏳ Document how to start integration test service
   - ⏳ Document how to check integration test results
   - ⏳ Document test service REST API

### Phase 13: Running and Checking Integration Test Runs ⏳ TODO

**Goal:** Establish workflow for running and monitoring integration tests.

**Tasks:**
1. **Test service deployment:**
   - ⏳ Add test service to docker-compose.yml
   - ⏳ Configure test service to run integration tests
   - ⏳ Set up log aggregation for test service

2. **Monitoring and alerting:**
   - ⏳ Set up alerts for test failures
   - ⏳ Dashboard for test run status
   - ⏳ Integration with existing monitoring (Prometheus/Grafana)

3. **Workflow documentation:**
   - ⏳ How to start integration test service
   - ⏳ How to trigger test runs
   - ⏳ How to check test results via REST API
   - ⏳ How to view test logs
   - ⏳ How to set up periodic test runs

## Essential Services

### Services (KEEP)
1. **telegram** - Receives voice messages from Telegram, orchestrates the pipeline
2. **discord** - Receives voice messages from Discord, orchestrates the pipeline (shares code with telegram)
3. **stt** - Speech-to-text conversion (Whisper)
4. **tts** - Text-to-speech conversion (FastSpeech2/espeak)
5. **inference-api** - LLM processing (Qwen3)

### Infrastructure
- **None required** - All services communicate via gRPC directly
- **From home_infra (shared-network):** nginx, jaeger, prometheus, grafana (available but not required)

## Architecture

### Service Directory Structure
- **`services/<service_name>/`** = Dockerfiles, service-specific configuration, build setup
- **`essence/services/<service_name>/`** = Actual service implementation code
- Services import and use the `essence` package for their code
- Clean separation: Docker/configuration vs. code

### Shared Code Architecture
- **Telegram and Discord share code** via `essence/chat/` module:
  - `essence/chat/agent/handler.py` - Shared agent message processing
  - `essence/chat/message_builder.py` - Shared message building utilities
  - `essence/chat/storage/conversation.py` - Shared conversation storage
  - Platform-specific handlers in `essence/services/telegram/` and `essence/services/discord/`

### Command Pattern
- All services implement `essence.commands.Command` interface
- Run via: `python -m essence <service-name>`
- Commands are discovered via reflection in `essence/commands/__init__.py`

## Testing Strategy

### Unit Tests
- **Location:** `tests/`
- **Runner:** pytest
- **Requirements:**
  - All external services/libraries must be mocked
  - Fast execution (< 1 minute for full suite)
  - No dependencies on running services
  - All tests runnable via `pytest tests/`

### Integration Tests
- **Location:** `tests/integration/` (or similar)
- **Runner:** Integration test service (background)
- **Requirements:**
  - Run in background (not waited on)
  - Check end-to-end functionality with real services
  - Results available via REST API or logs
  - Can be checked periodically

### Test Service
- **Purpose:** Run integration tests in background and provide results via API
- **Interface:** REST API for test management
- **Features:**
  - Start test runs
  - Check test status
  - Retrieve results
  - View logs
  - Test run history

## Next Steps

1. **Phase 11:** Clean up scripts directory and migrate to commands
2. **Phase 12:** Create integration test service infrastructure
3. **Phase 13:** Establish workflow for running and checking integration tests
4. **Ongoing:** Maintain minimal architecture and follow established best practices
