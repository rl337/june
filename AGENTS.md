# Agent Development Guidelines for June Refactoring

This document provides essential context and guidelines for AI agents working on the June project refactoring.

## Versioning

**IMPORTANT**: This project uses **automatic semantic versioning** via GitHub Actions.

### How It Works

- **Regular commits to main**: Automatically bumps patch version (0.2.0 → 0.2.1)
- **Merge commits to main**: Automatically bumps minor version (0.2.0 → 0.3.0)
- **Major versions**: Must be bumped manually using `poetry version major`

### What This Means for Agents

1. **Do NOT manually update versions** in `pyproject.toml` or `essence/__init__.py` unless:
   - You're bumping a major version (breaking changes)
   - You're fixing a version that got out of sync

2. **Version bumps are automatic**: When you commit to main (or merge a PR), the version will be automatically bumped by the GitHub Actions workflow.

3. **Version sync**: The workflow updates both:
   - `pyproject.toml` (the `version = "X.Y.Z"` field)
   - `essence/__init__.py` (the `__version__ = "X.Y.Z"` field)

4. **Skip CI**: Version bump commits include `[skip ci]` to prevent infinite loops.

### Manual Version Bumping

If you need to manually bump a major version:

```bash
poetry version major
# Then manually update essence/__init__.py to match
```

## Current Refactoring Context

**Goal:** Pare down the june project to bare essentials for the **voice message → STT → LLM → TTS → voice response** round trip, supporting both **Telegram** and **Discord** platforms.

**Status:** See `REFACTOR_PLAN.md` for detailed progress and TODO items.

**CRITICAL:** Run tests at the start and end of every turn and fix any breakages. 
**CRITICAL:** Use feature branches for all work - never commit directly to main. See "Git Branching Strategy" section below.
**CRITICAL:** Check in outstanding logically grouped changes with good descriptive commit messages. If there are commits unpushed, push upstream

## Project Structure

### Code Organization

**CRITICAL:** All Python code lives in the `essence/` package. Services are thin wrappers.

- **`essence/`** = All actual service code and shared utilities
  - `essence/services/telegram/` = Telegram bot service code
  - `essence/services/discord/` = Discord bot service code
  - `essence/chat/` = Shared chat/conversation utilities (used by both platforms)
  - `essence/commands/` = Command pattern implementations
  - `essence/chat/utils/tracing.py` = OpenTelemetry tracing utilities

- **`services/<service_name>/`** = Dockerfiles and configuration ONLY
  - Contains: Dockerfile, config files
  - Does NOT contain: Python code (code is in `essence/`)
  - Services import from `essence` package, not from `services/` directories

### Essential Services (Keep)

1. **telegram** - Receives voice messages from Telegram, orchestrates pipeline
2. **discord** - Receives voice messages from Discord, orchestrates pipeline
3. **stt** - Speech-to-text conversion (Whisper)
4. **tts** - Text-to-speech conversion (FastSpeech2/espeak)

**LLM Inference:** 
- **Current implementation:** TensorRT-LLM container (from home_infra shared-network) - optimized GPU inference
- **Legacy:** inference-api service (disabled by default, available via legacy profile for backward compatibility)

### Removed Services (Do Not Use)

- ❌ **gateway** - Using common nginx from home_infra instead
- ❌ **postgres** - Not needed for MVP (available in home_infra for other services)
- ❌ **minio** - Not needed for MVP
- ❌ **redis** - Not needed for MVP
- ❌ **nats** - Not needed for MVP (available in home_infra for other services)
- ❌ **orchestrator** - Removed
- ❌ **webapp** - Removed
- ❌ **june-agent** - Removed
- ❌ **mock-sink** - Removed
- ❌ **telegram-voice-worker** - Removed

## Architecture Patterns

### Command Pattern

All services use the `essence.command.Command` pattern:

```python
from essence.command import Command

class TelegramServiceCommand(Command):
    @classmethod
    def get_name(cls) -> str:
        return "telegram-service"
    
    def init(self) -> None:
        # Initialize service
        pass
    
    def run(self) -> None:
        # Run service (blocking)
        pass
    
    def cleanup(self) -> None:
        # Clean up resources
        pass
```

Services are invoked via: `python -m essence <service-name>-service`

### Service Entry Points

- Services run via `essence` command system
- Dockerfiles copy `essence/` package and run: `poetry run python -m essence <service-name>-service`
- Services get their code from `essence` package, NOT from `services/` directories

### Shared Code

- **Telegram and Discord share code** via `essence/chat/` module:
  - `essence/chat/agent/handler.py` - Shared agent message processing
  - `essence/chat/message_builder.py` - Shared message building utilities
  - `essence/chat/storage/conversation.py` - Shared conversation storage
  - Platform-specific handlers in `essence/services/telegram/` and `essence/services/discord/`

## Dependencies to Remove

When refactoring, remove dependencies on:

1. **PostgreSQL** - Remove `POSTGRES_URL`, database connections, queries
2. **MinIO** - Remove `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, storage operations
3. **Redis** - Remove `REDIS_URL`, caching, rate limiting (use in-memory alternatives)
4. **NATS** - Remove `NATS_URL`, pub/sub messaging (services call each other directly via gRPC)
5. **Gateway** - Remove `GATEWAY_URL`, `CONVERSATION_API_URL` (use in-memory conversation storage)

## Replacement Patterns

### Conversation Storage
- **Before:** Gateway HTTP API or PostgreSQL
- **After:** In-memory storage in telegram/discord services
- **Implementation:** Use dictionaries or simple in-memory data structures

### Rate Limiting
- **Before:** Redis-based rate limiting
- **After:** In-memory rate limiting in telegram/discord services
- **Implementation:** Use in-memory counters with time windows

### Caching
- **Before:** Redis caching
- **After:** In-memory caching or no caching for MVP
- **Implementation:** Simple Python dictionaries with TTL

### Messaging
- **Before:** NATS pub/sub
- **After:** Direct gRPC calls between services
- **Implementation:** Services call each other directly via gRPC (already implemented)

## Observability Requirements

### OpenTelemetry Tracing

**All services MUST use proper tracing:**

1. **Initialize tracing on startup:**
   ```python
   from essence.chat.utils.tracing import setup_tracing
   setup_tracing(service_name="june-telegram")  # or "june-discord", "june-stt", etc.
   ```

2. **Add spans to all operations:**
   - gRPC calls (STT, TTS, LLM)
   - HTTP requests (Telegram/Discord webhooks)
   - Voice processing (download, conversion, transcription)
   - Message handling (processing, generation, synthesis)
   - Error handling (with proper error tags)

3. **Trace propagation:**
   - Ensure trace context propagates across gRPC calls
   - Use OpenTelemetry gRPC instrumentation for automatic propagation
   - Traces should show full request flow: Telegram → STT → LLM → TTS → Telegram

4. **Configuration:**
   - Environment variables: `ENABLE_TRACING=true`, `JAEGER_ENDPOINT=http://common-jaeger:14268/api/traces`
   - Traces go to Jaeger in shared-network: `common-jaeger:14268`

### Prometheus Metrics

**All services MUST expose Prometheus metrics:**

1. **Expose `/metrics` endpoint:**
   - Use `prometheus_client` library
   - Metrics available on service's HTTP port (telegram:8080, discord:8081)

2. **Key metrics to implement:**
   - `http_requests_total` - Total HTTP requests (labels: method, endpoint, status_code)
   - `http_request_duration_seconds` - Request duration histogram
   - `grpc_requests_total` - Total gRPC requests (labels: service, method, status_code)
   - `grpc_request_duration_seconds` - gRPC request duration histogram
   - `voice_messages_processed_total` - Total voice messages (labels: platform, status)
   - `voice_processing_duration_seconds` - Voice processing duration histogram
   - `errors_total` - Total errors (labels: service, error_type)
   - `service_health` - Service health status (1 = healthy, 0 = unhealthy)

3. **Verification:**
   - Metrics should be scraped by Prometheus in home_infra
   - Metrics should appear in Grafana dashboards

## Network Configuration

### Docker Networks

- **`june_network`** - Internal network for june services
- **`shared-network`** - External network connecting to home_infra services
  - Access to: Jaeger, Prometheus, Grafana, nginx
  - Name: `shared_network` (external network)

### Service Communication

- **gRPC:** Services communicate via gRPC directly
  - STT: `grpc://stt:50052`
  - TTS: `grpc://tts:50053`
  - LLM: TensorRT-LLM container (grpc://tensorrt-llm:8000) - default implementation; NVIDIA NIM (grpc://nim-qwen3:8001) - pre-built alternative; inference-api service available via legacy profile
- **HTTP:** Health checks and metrics endpoints
  - Telegram: `http://telegram:8080`
  - Discord: `http://discord:8081`

## Python Dependency Management

**All Python code uses Poetry for dependency management.**

- Commands: `poetry run python -m essence <command>`
- Tests: `poetry run pytest`
- Dependencies: `pyproject.toml` and `poetry.lock`

## Working with the Refactoring Plan

### Reading the Plan

- **File:** `REFACTOR_PLAN.md`
- **Status markers:**
  - ✅ = Completed
  - ⏳ = TODO (unfinished)
  - ~~strikethrough~~ = Removed/obsolete

### Updating the Plan

When completing tasks:

1. **Mark completed tasks:**
   - Change ⏳ TODO to ✅ COMPLETED
   - Add brief summary of what was done

2. **Document discoveries:**
   - Add new tasks with ⏳ TODO
   - Document issues or blockers
   - Document decisions made
   - Add to appropriate section

3. **Keep it organized:**
   - Update progress status section
   - Keep phases in order
   - Maintain clear task descriptions

## Common Tasks

### Removing Service Dependencies

1. **Find references:**
   ```bash
   grep -r "POSTGRES_URL\|MINIO_ENDPOINT\|REDIS_URL\|NATS_URL" essence/
   ```

2. **Remove environment variables:**
   - Remove from docker-compose.yml (already done)
   - Remove from code that reads them

3. **Replace functionality:**
   - Database → In-memory storage
   - Redis → In-memory rate limiting/caching
   - NATS → Direct gRPC calls
   - Gateway API → In-memory conversation storage

### Adding Tracing

1. **Import tracing utilities:**
   ```python
   from essence.chat.utils.tracing import get_tracer
   ```

2. **Create spans:**
   ```python
   tracer = get_tracer(__name__)
   with tracer.start_as_current_span("operation_name") as span:
       span.set_attribute("key", "value")
       # ... do work ...
   ```

3. **Add to gRPC calls:**
   - Use OpenTelemetry gRPC instrumentation
   - Ensure trace context propagates

### Adding Metrics

1. **Import prometheus_client:**
   ```python
   from prometheus_client import Counter, Histogram, generate_latest
   ```

2. **Define metrics:**
   ```python
   requests_total = Counter('http_requests_total', 'Total requests', ['method', 'endpoint'])
   request_duration = Histogram('http_request_duration_seconds', 'Request duration')
   ```

3. **Expose endpoint:**
   ```python
   @app.get("/metrics")
   def metrics():
       return Response(generate_latest(), media_type="text/plain")
   ```

## Testing Guidelines

### Unit Tests

- Test individual functions and classes
- Mock external dependencies (gRPC, HTTP)
- Use `poetry run pytest tests/`

### Integration Tests

- Test service interactions
- Use test fixtures for starting services
- Verify tracing and metrics

### End-to-End Tests

- Test complete request flow
- Verify traces in Jaeger
- Verify metrics in Prometheus
- Fully automated (no human interaction)

## Important Files

- **`REFACTOR_PLAN.md`** - Main refactoring plan (READ THIS FIRST)
- **`docker-compose.yml`** - Service definitions (already cleaned up)
- **`pyproject.toml`** - Python dependencies
- **`essence/`** - All service code
- **`services/`** - Dockerfiles and config only

## Common Pitfalls

1. **Don't add code to `services/` directories** - Code goes in `essence/`
2. **Don't use removed services** - No postgres, minio, redis, nats, gateway
3. **Don't skip tracing** - All operations must be traced
4. **Don't skip metrics** - All services must expose metrics
5. **Don't forget to update REFACTOR_PLAN.md** - Document what you did

## Getting Help

- Read `REFACTOR_PLAN.md` for current state and tasks
- Check `essence/chat/utils/tracing.py` for tracing examples
- Check existing service code in `essence/services/` for patterns
- Review docker-compose.yml to understand service configuration

## Git Branching Strategy

**CRITICAL:** All development work must happen on feature branches, not directly on `main`.

### Why Feature Branches?

- **Clean history:** Main branch stays clean with meaningful, squashed commits
- **Better organization:** Related changes grouped together in feature branches
- **Easier review:** Each feature can be reviewed as a unit before merging
- **Reduced noise:** Avoids proliferation of trivial commits (e.g., "Update timestamp", "Fix typo") on main

### Branching Workflow

1. **Create feature branch from main:**
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/phase-19-whitelist-config
   ```
   - Branch naming: `feature/<descriptive-name>` or `feature/phase-<N>-<task>`
   - Examples: `feature/phase-19-whitelist-config`, `feature/nim-deployment`, `feature/telegram-user-ids`

2. **Work on the feature branch:**
   - Make all commits to the feature branch
   - Commit frequently with descriptive messages
   - Group related changes logically
   - Push feature branch regularly: `git push origin feature/branch-name`

3. **Track in REFACTOR_PLAN.md:**
   - Add feature branch to "Active Feature Branches" section
   - Update status as work progresses
   - Link to specific tasks/phases

4. **When feature is complete:**
   - Ensure all tests pass: `poetry run pytest tests/`
   - Squash commits into logical groups (if needed): `git rebase -i main`
   - Update REFACTOR_PLAN.md to mark tasks complete
   - Create pull request or merge with squash:
     ```bash
     git checkout main
     git pull origin main
     git merge --squash feature/branch-name
     git commit -m "Feature: <descriptive name>
     
     <detailed description of what was implemented>
     
     Closes: <task reference from REFACTOR_PLAN.md>"
     git push origin main
     git branch -d feature/branch-name  # Delete local branch
     git push origin --delete feature/branch-name  # Delete remote branch
     ```

### What Goes in a Feature Branch?

- **One feature or task** from REFACTOR_PLAN.md
- **All related changes:**
  - Code changes
  - Tests
  - Documentation updates
  - Configuration changes
  - Related fixes and improvements

### What Stays on Main?

- **Only merged features** (via squash merge)
- **Hotfixes** (critical production issues) - use `hotfix/` branches
- **No trivial commits** like:
  - "Update timestamp"
  - "Fix typo" (unless part of a feature)
  - "Cleanup whitespace" (unless part of a feature)
  - Multiple small documentation updates (group into feature)

### Branch Naming Conventions

- `feature/phase-<N>-<task-name>` - For refactoring plan tasks
- `feature/<descriptive-name>` - For other features
- `hotfix/<issue-description>` - For critical fixes
- Examples:
  - `feature/phase-19-whitelist-config`
  - `feature/telegram-user-id-extraction`
  - `feature/nim-deployment-setup`
  - `hotfix/telegram-service-crash`

### Tracking Feature Branches

- **In REFACTOR_PLAN.md:** Add to "Active Feature Branches" section
- **Format:**
  ```markdown
  ### Active Feature Branches
  
  - `feature/phase-19-whitelist-config` - ⏳ IN PROGRESS
    - Task: Configure Telegram/Discord whitelist user IDs
    - Started: 2025-11-20
    - Status: Extracted Telegram ID, need Discord ID
    - Related: Phase 19 Task 2
  ```

## Workflow for Refactoring Agent

1. **Check for active feature branches** - See REFACTOR_PLAN.md "Active Feature Branches" section
2. **If no active branch, create one:**
   - Pick a task from REFACTOR_PLAN.md
   - Create feature branch: `git checkout -b feature/phase-<N>-<task>`
   - Add branch to REFACTOR_PLAN.md "Active Feature Branches" section
3. **Work on the feature branch:**
   - Make focused, incremental changes
   - Commit frequently with descriptive messages
   - Push feature branch regularly
4. **Update REFACTOR_PLAN.md:**
   - Document progress in feature branch section
   - Update task status
5. **When feature complete:**
   - Squash commits if needed
   - Merge to main with squash
   - Update REFACTOR_PLAN.md to mark complete
   - Delete feature branch

## Key Principles

1. **Incremental progress** - One task at a time
2. **Update the plan** - Always document progress and discoveries
3. **Keep it simple** - MVP means minimal viable product
4. **Test as you go** - Verify changes work
5. **Follow patterns** - Use existing code patterns and structure
