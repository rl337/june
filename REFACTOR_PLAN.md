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

### Phase 12: Test Infrastructure and Integration Test Service ✅
- Created integration test service with REST API
- Migrated existing integration tests to work with test service
- Comprehensive testing documentation
- **Best Practice:** Integration tests run in background via test service; use REST API for management

### Phase 13: Running and Checking Integration Test Runs ✅
- Deployed integration test service to docker-compose.yml
- Set up Prometheus metrics and alerting
- Created Grafana dashboard for test monitoring
- Comprehensive workflow documentation
- **Best Practice:** Monitor test runs via Prometheus/Grafana; set up alerts for failures

## Current Priorities

### Phase 12: Test Infrastructure and Integration Test Service ✅ COMPLETED

**Goal:** Establish proper test infrastructure with unit tests (mocked) and integration tests (background service).

**Status:** All requirements met and tasks completed.

**Tasks:**
1. **Create integration test service:**
   - ✅ Design REST API for test management (COMPLETED - REST API with endpoints for starting tests, checking status, retrieving results, viewing logs, listing runs, cancelling runs)
   - ✅ Implement test runner that executes tests in background (COMPLETED - uses subprocess to run pytest in background, captures output line-by-line)
   - ✅ Implement result storage and retrieval (COMPLETED - in-memory storage with TestRun dataclass, stores status, output, logs, exit codes)
   - ✅ Add health check endpoint (COMPLETED - /health endpoint with Prometheus metrics)

2. **Migrate existing integration tests:**
   - ✅ Identify current integration tests (COMPLETED - identified 4 test files: 3 active, 1 obsolete. Created tests/integration/README.md documenting all tests, their dependencies, and status)
   - ✅ Ensure they can run in background (COMPLETED - all tests are pytest-based and can run in background. Integration test service runs them via subprocess)
   - ✅ Update to use test service API (COMPLETED - tests work as-is via pytest. Integration test service runs them via `poetry run pytest` and provides REST API for management. No code changes needed to tests)

3. **Documentation:**
   - ✅ Document how to run unit tests (pytest) (COMPLETED - created docs/guides/TESTING.md with comprehensive testing guide including unit test requirements, examples, best practices, and troubleshooting)
   - ✅ Document how to start integration test service (COMPLETED - added comprehensive documentation to docs/guides/TESTING.md including command usage, environment variables, and service endpoints)
   - ✅ Document how to check integration test results (COMPLETED - added REST API reference with examples for checking status, retrieving results, viewing logs, listing runs, and cancelling tests)
   - ✅ Document test service REST API (COMPLETED - added complete REST API reference with all 8 endpoints, request/response examples, status values, and usage examples in bash and Python)

### Phase 13: Running and Checking Integration Test Runs ✅ COMPLETED

**Goal:** Establish workflow for running and monitoring integration tests.

**Tasks:**
1. **Test service deployment:**
   - ✅ Add test service to docker-compose.yml (COMPLETED - added integration-test service with Dockerfile, health checks, port 8082, log volume mount, and network configuration)
   - ✅ Configure test service to run integration tests (COMPLETED - service runs via `poetry run python -m essence integration-test-service` which executes pytest in background via subprocess)
   - ✅ Set up log aggregation for test service (COMPLETED - logs mounted to `/var/log/june/integration-test:/logs` volume, service writes logs to stdout/stderr which are captured by Docker)

2. **Monitoring and alerting:**
   - ✅ Set up alerts for test failures (COMPLETED - added 5 Prometheus alert rules in config/prometheus-alerts.yml: service down, test failures, high failure rate, long duration, service unhealthy)
   - ✅ Dashboard for test run status (COMPLETED - created Grafana dashboard JSON in config/grafana/integration-test-dashboard.json with 6 panels: active test runs, success rate, service health, test runs by status, test duration, failure rate)
   - ✅ Integration with existing monitoring (Prometheus/Grafana) (COMPLETED - added Prometheus scrape config for integration-test service, added test-specific metrics (integration_test_runs_total, integration_test_run_duration_seconds, integration_test_runs_active), created comprehensive monitoring guide in docs/guides/MONITORING.md)

3. **Workflow documentation:**
   - ✅ How to start integration test service (COMPLETED - documented in docs/guides/TESTING.md with command usage, environment variables, and service endpoints)
   - ✅ How to trigger test runs (COMPLETED - documented in docs/guides/TESTING.md with REST API examples and usage workflows)
   - ✅ How to check test results via REST API (COMPLETED - documented in docs/guides/TESTING.md with complete REST API reference including status, results, and logs endpoints)
   - ✅ How to view test logs (COMPLETED - documented in docs/guides/TESTING.md with GET /tests/logs endpoint and usage examples)
   - ✅ How to set up periodic test runs (COMPLETED - added comprehensive documentation to docs/guides/TESTING.md with examples for cron, systemd timers, Docker containers, Python scripts, and best practices)

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

1. **Ongoing:** Maintain minimal architecture and follow established best practices
2. **Future enhancements (optional):**
   - Consider persistent storage for test results (currently in-memory)
   - Add test result export functionality
   - Enhance Grafana dashboards with additional visualizations
   - Set up automated test runs on code changes (CI/CD integration)

## Known Issues

### Pre-existing Test Failures

**Status:** ⏳ TODO - Not blocking refactoring work

**Issue:** 5 test failures in `tests/essence/chat/agent/test_response_accumulation.py`:
- `test_json_accumulation_logic[complete_json_single_assistant]` - Expected 2 outputs, got 1 (fallback error message)
- `test_json_accumulation_logic[complete_json_with_result]` - Expected "Hello", got "Hello world" (text accumulation issue)
- `test_json_accumulation_logic[shell_output_skipped]` - Expected 2 outputs, got 1 (fallback error message)
- `test_json_accumulation_logic[very_long_result_message]` - Expected 1 output, got 2 (splitting issue)
- `test_json_accumulation_logic[multiple_assistant_chunks]` - Expected 4 outputs, got 1 (fallback error message)

**Root Cause:** JSON parsing logic in `essence/chat/agent/response.py` not extracting messages correctly in test scenarios. Tests show warnings: "No messages were extracted from stream".

**Impact:** These failures are pre-existing and not related to the refactoring work. They affect the response accumulation logic but don't block the core refactoring goals.

**Action Required:** Investigate and fix JSON parsing/extraction logic in `stream_chat_response_agent` function to properly handle test cases.
