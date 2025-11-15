# AGENTS.md - Development Guide for June Agent

This document provides essential information for AI agents working on the June Agent project, including architecture details, development practices, and environment specifics.

## 📋 Task Management

**IMPORTANT:** Always check and update `TODO.md` before and after working on tasks.

- **Before starting work:** Review `TODO.md` for current tasks and priorities
- **After completing work:** Update `TODO.md` to mark completed tasks and add new tasks as needed
- **Keep TODO.md current:** This is the single source of truth for what needs to be done

The `TODO.md` file contains:
- Detailed task breakdowns for major features
- Implementation phases and dependencies
- Technical specifications and requirements
- Testing and deployment checklists

See `TODO.md` for the current Telegram voice-to-text-to-voice service implementation plan.

### TODO MCP Service Integration (For Agentic Capabilities)

When June agents are working with the TODO MCP Service (for autonomous task management), agents MUST check for previous work and continue existing tasks before starting new ones. See the "🔄 Resuming and Continuing Tasks" section below for detailed guidelines.

## 🔄 Resuming and Continuing Tasks (CRITICAL)

**Agents MUST check for previous work and continue existing tasks before starting new ones.**

### Priority: Continue Your In-Progress Tasks First

**Before picking up a new task, ALWAYS check if you already have tasks in progress:**

```python
# 1. First, check for tasks already assigned to you
my_tasks = query_tasks(
    agent_id=agent_id,
    task_status="in_progress",
    limit=10
)

if my_tasks:
    # You have existing work - continue it first!
    logger.info(f"Found {len(my_tasks)} task(s) already in progress")
    for task in my_tasks:
        logger.info(f"  - Task {task['id']}: {task['title']}")
    
    # Continue the first in-progress task
    task_id = my_tasks[0]['id']
    context = get_task_context(task_id=task_id)
else:
    # No existing tasks, can pick up a new one
    tasks = list_available_tasks(agent_type="implementation", project_id=1)
    if tasks:
        task_id = tasks[0]['id']
        context = reserve_task(task_id=task_id, agent_id=agent_id)
```

### The Problem

Agents currently pick up new tasks without checking if they already have work in progress, leading to:
- ❌ Duplicate work (re-doing what another agent already completed)
- ❌ Ignoring previous progress and updates
- ❌ Missing uncommitted changes in git
- ❌ Not resuming where previous agent left off
- ❌ No documentation of progress

### Mandatory Workflow: Check Previous Work (TODO MCP Service)

**When you pick up a task (new or existing), you MUST:**

1. **Check for Previous Context After Reserving:**
   ```python
   # Immediately after reserving, get full context
   context = get_task_context(task_id=task_id)
   
   # Check for:
   # - Previous updates (context["updates"])
   # - Recent changes (context["recent_changes"])
   # - Stale warnings (context.get("stale_warning"))
   # - Parent tasks and relationships (context["ancestry"])
   # - Project information (context["project"])
   ```

2. **Check Git Status for Uncommitted Work (MANDATORY):**
   ```python
   # ALWAYS check git status before starting
   import subprocess
   
   # Check for uncommitted changes in the project directory
   project_path = context["project"]["local_path"]
   git_status = subprocess.run(
       ["git", "status", "--short"],
       cwd=project_path,
       capture_output=True,
       text=True
   ).stdout
   
   if git_status.strip():
       # There are uncommitted changes - review them first!
       # They might be work from a previous agent session
       logger.info(f"Found uncommitted changes:\n{git_status}")
       
       # Show the diff to understand what was done
       git_diff = subprocess.run(
           ["git", "diff"],
           cwd=project_path,
           capture_output=True,
           text=True
       ).stdout
       
       # Review the changes and determine if work should continue
   ```

3. **Review Previous Updates (MANDATORY):**
   ```python
   # Check what the previous agent(s) documented
   updates = context.get("updates", [])
   
   for update in updates:
       logger.info(f"Previous update [{update['update_type']}]: {update['content']}")
       # Understand what was tried, what worked, what failed
       
   # If there are blockers, address them
   blockers = [u for u in updates if u["update_type"] == "blocker"]
   if blockers:
       logger.warning(f"Found {len(blockers)} blocker(s) from previous work")
       # Address blockers before continuing
   ```

4. **Check for Stale Task Warnings (MANDATORY):**
   ```python
   # If task was previously abandoned, you MUST verify work
   stale_warning = context.get("stale_warning")
   if stale_warning:
       logger.warning(f"⚠️ STALE TASK WARNING: {stale_warning['message']}")
       logger.warning(f"Previous agent: {stale_warning['previous_agent']}")
       logger.warning(f"Previously unlocked at: {stale_warning['unlocked_at']}")
       
       # MANDATORY: Verify all previous work before continuing
       # - Check if any code changes are correct
       # - Verify if tests pass
       # - Confirm no regressions
       # - Document your verification in an update
       
       add_task_update(
           task_id=task_id,
           agent_id=agent_id,
           content=f"Verifying previous work by {stale_warning['previous_agent']}. Checking git status, reviewing changes, running tests.",
           update_type="progress"
       )
   ```

5. **Resume Where Previous Work Left Off:**
   ```python
   # Based on updates and git status, determine:
   # - What was already implemented
   # - What still needs to be done
   # - What tests already pass
   # - What needs to be fixed or completed
   
   # Create a plan that builds on previous work
   # Don't start from scratch - continue the work
   
   add_task_update(
       task_id=task_id,
       agent_id=agent_id,
       content="Resuming work. Reviewed previous updates and git status. Previous agent made progress on X, Y. Will continue with Z.",
       update_type="progress"
   )
   ```

6. **Document Your Progress Continuously:**
   ```python
   # As you work, add updates frequently:
   add_task_update(
       task_id=task_id,
       agent_id=agent_id,
       content="Completed step 1: Implemented X function with tests",
       update_type="progress"
   )
   
   add_task_update(
       task_id=task_id,
       agent_id=agent_id,
       content="Found issue with Y - needs refactoring. Creating followup task.",
       update_type="finding"
   )
   
   # This helps the next agent understand what happened
   ```

### Benefits of Continuing Existing Tasks

- ✅ **No duplicate work** - Agents build on previous progress
- ✅ **Better continuity** - Work continues seamlessly across agent sessions
- ✅ **Documented progress** - Updates show what was done and why
- ✅ **Faster completion** - Don't re-do what's already done
- ✅ **Better debugging** - Clear history of attempts and issues
- ✅ **Resource efficiency** - Don't waste time on completed work

### Common Mistakes to Avoid

- ❌ Starting work without checking `get_task_context()`
- ❌ Ignoring `stale_warning` - you MUST verify previous work
- ❌ Not checking git status - uncommitted changes might be previous work
- ❌ Not reading previous updates - you might repeat failed attempts
- ❌ Starting from scratch when work was already done
- ❌ Not documenting progress - next agent won't know what happened
- ❌ Not checking for blockers - you might hit the same issues

**This is CRITICAL for maintaining work continuity and preventing duplicate effort when using the TODO MCP Service for autonomous task management.**

**Key Principle: Always check for your existing in-progress tasks before picking up new work. Continue what you started before starting something new.**

## 🧪 Test-First Development (CRITICAL)

**MANDATORY:** All agents MUST follow test-first behavior.

### Core Principles
1. **Write tests BEFORE implementing features**
   - Define test cases that describe expected behavior
   - Tests should initially fail (red phase)
   - Implement minimal code to make tests pass (green phase)
   - Refactor while keeping tests green

2. **Run checks before ANY commit or push**
   - **ALWAYS** run `./run_checks.sh` before committing
   - Never commit code that breaks existing tests
   - Ensure all new tests pass before pushing
   - Never skip tests for convenience

3. **Test Coverage Requirements**
   - All service endpoints must have tests
   - All database operations must have tests
   - Integration scenarios must be tested
   - Error cases must be covered

### Pre-Commit Workflow
```bash
# MANDATORY: Run before every commit
./run_checks.sh

# Only commit if all checks pass
git add .

# MANDATORY: Write meaningful commit messages
git commit -m "Clear, descriptive commit message"
git push
```

### Commit Message Requirements (CRITICAL)

**All commits MUST have meaningful, descriptive commit messages.**

#### Why Meaningful Commit Messages Matter
- **History**: Makes project history readable and searchable
- **Debugging**: Helps identify when/why bugs were introduced
- **Collaboration**: Other agents understand what changed
- **Documentation**: Commit history serves as project documentation

#### Commit Message Format
1. **Subject line** (first line, imperative mood, ~50-72 chars)
   - Use imperative mood: "Add feature X" not "Added feature X" or "Adds feature X"
   - Start with a capital letter
   - No period at the end
   - Be specific: What changed?

2. **Body** (optional but recommended for complex changes)
   - Explain WHAT changed and WHY
   - Separate from subject with blank line
   - Wrap lines at 72 characters
   - Use bullet points for multiple changes

#### Good Commit Message Examples

```
Add retry logic for transient STT errors

Implements exponential backoff retry mechanism for STT service client.
Handles network failures and temporary service unavailability with
configurable retry attempts and backoff intervals. Updates error handling
to distinguish transient vs permanent failures.

Fixes issue where single network hiccup would fail entire voice message
processing pipeline.
```

```
Fix docker-compose.yml port mapping for STT service

Updates STT service port from 50052 to 50053 to avoid conflict with
TTS service. Also fixes health check endpoint path.
```

```
Update AGENTS.md with commit message requirements

Adds comprehensive guidelines for writing meaningful commit messages.
Emphasizes imperative mood, descriptive subjects, and explanatory bodies
for complex changes.
```

#### Bad Commit Message Examples (DON'T DO THIS)
```
❌ "fix"
❌ "update"
❌ "changes"
❌ "wip"
❌ "commit"
❌ "asdf"
❌ "test"
❌ "."
❌ "fix bug" (too vague - which bug?)
❌ "update stuff" (too vague - what stuff?)
```

#### Multi-File Change Guidelines
When committing changes across multiple files:
- If changes are related to one feature/fix: Single commit with descriptive message explaining the feature/fix
- If changes are unrelated: Separate commits for each logical change
- Example of related changes in one commit:
  ```
  Implement stale task detection in MCP API
  
  Updates reserve_task() and get_task_context() to detect and surface
  stale task information. Includes:
  - Detection logic for stale "finding" updates
  - stale_warning field in reserve_task response
  - stale_info field in get_task_context response
  - Warning messages for agents picking up abandoned tasks
  
  Related files:
  - src/mcp_api.py: Added stale detection logic
  - tests/test_mcp_api.py: Added tests for stale detection
  ```

#### Before Pushing
1. **Review your commit history**: `git log --oneline -10`
   - Verify all commit messages are meaningful
   - Identify related commits that should be combined

2. **Rebase repeated check-ins into feature-based commits** (MANDATORY)
   - **DO NOT push multiple small commits that are part of one feature**
   - Use interactive rebase to squash related commits together: `git rebase -i HEAD~N`
   - Group commits by feature/bug fix, not by "time of commit"
   
   **Example workflow:**
   ```bash
   # Check recent commits
   git log --oneline -8
   # Output might look like:
   # abc123 "Add retry logic to STT client"
   # def456 "Fix backoff calculation"
   # ghi789 "Add error handling for retry"
   # jkl012 "Add tests for retry logic"
   # mno345 "Fix typo in test name"
   # pqr678 "Add documentation for retry"
   
   # These 6 commits should be ONE feature commit
   git rebase -i HEAD~6
   # In editor: change "pick" to "squash" (or "s") for commits 2-6
   # Save and write comprehensive commit message:
   # "Add retry logic for transient STT errors
   #
   # Implements exponential backoff retry mechanism for STT service.
   # Includes error handling, comprehensive tests, and documentation."
   
   # Final result: ONE clean commit instead of 6 scattered ones
   ```

   **When to rebase/squash:**
   - Multiple commits implementing one feature (e.g., "Add feature" + "Fix bug in feature" + "Add tests for feature")
   - Multiple commits fixing one bug (e.g., "Fix bug" + "Fix typo" + "Add test")
   - WIP commits that are part of the same work
   - Typo/formatting fixes that belong with the original feature
   - Documentation updates that go with the feature
   
   **When NOT to rebase:**
   - Commits that are already pushed to shared branches (unless on your own feature branch)
   - Unrelated changes that should remain separate (different features, different bugs)
   - Commits from other people (never rewrite shared history)

   **Interactive Rebase Commands:**
   - `pick` (or `p`): Keep commit as-is
   - `squash` (or `s`): Combine with previous commit
   - `fixup` (or `f`): Like squash but discard commit message
   - `edit` (or `e`): Pause to modify commit
   - `drop` (or `d`): Remove commit entirely

3. **Fix poor commit messages**:
   - Use `git commit --amend` to fix the last commit
   - Use `git rebase -i HEAD~N` to fix multiple recent commits
   - **Never push commits with meaningless messages**

**Goal**: Each pushed commit should represent a complete, logical unit of work (one feature, one bug fix, one refactor, etc.), not just "what I committed at 2pm" vs "what I committed at 3pm".

### What run_checks.sh Validates
- Docker Compose configuration
- Container health and connectivity
- Service endpoints and gRPC services
- Database connectivity
- Model cache integrity
- TODO MCP Service integration
- System-wide health checks

**If run_checks.sh fails, DO NOT commit or push. Fix issues first.**

## 🏗️ Architecture Overview

June Agent is a microservices-based interactive autonomous agent system optimized for NVIDIA DGX Spark with the following architecture:

### Core Services
- **Gateway Service** (Port 8000) - FastAPI + WebSocket ingress with auth, rate limiting
- **Inference API** (Port 50051) - gRPC coordinator for LLM orchestration with RAG
- **STT Service** (Port 50052) - Speech-to-Text with Whisper, VAD, gRPC streaming
- **TTS Service** (Port 50053) - Text-to-Speech with FastSpeech2/HiFi-GAN streaming
- **Webapp Service** (Port 3000) - React-based Telegram-like chat interface

### Supporting Infrastructure
- **PostgreSQL + pgvector** (Port 5432) - RAG storage and conversation memory
- **MinIO** (Ports 9000/9001) - S3-compatible object storage
- **NATS** (Port 4222) - Pub/sub messaging
- **Prometheus** (Port 9090) - Metrics collection
- **Grafana** (Port 3000) - Dashboards
- **Loki** (Port 3100) - Log aggregation
- **Jaeger** (Port 16686) - Distributed tracing

## 🤖 Current Model Configuration

**Primary LLM:** `Qwen/Qwen3-30B-A3B-Thinking-2507`
- **Context Window:** 128k tokens with Yarn expansion
- **Device:** CUDA GPU 0 with MPS sharing
- **Quantization:** 4-bit for memory efficiency
- **Capabilities:** Advanced reasoning, tool use, RAG integration

**STT Model:** `openai/whisper-large-v3`
- **Features:** Voice Activity Detection (VAD), real-time streaming
- **Languages:** Multi-language support

**TTS Model:** `facebook/fastspeech2-en-ljspeech`
- **Features:** Multiple voices, prosody control, streaming output

## 🚨 CRITICAL: Model Cache Management

**STRICT POLICY:** Models MUST be downloaded using the authorized download script ONLY.

### Model Cache Directory
- **Location:** `/home/rlee/models`
- **Structure:**
  - `/home/rlee/models/huggingface/` - Hugging Face models
  - `/home/rlee/models/transformers/` - Transformers cache
  - `/home/rlee/models/whisper/` - Whisper models
  - `/home/rlee/models/tts/` - TTS models

### Authorized Model Download
**ONLY** use `scripts/download_models.py` for model downloads:

```bash
# Download all required models
python scripts/download_models.py --all

# Download specific model
python scripts/download_models.py --model Qwen/Qwen3-30B-A3B-Thinking-2507

# Check cache status
python scripts/download_models.py --status

# List authorized models
python scripts/download_models.py --list
```

### Runtime Model Loading
- **Services MUST use local cache only**
- **NO internet downloads during runtime**
- **Set environment variables:**
  - `MODEL_CACHE_DIR=/home/rlee/models`
  - `HUGGINGFACE_CACHE_DIR=/home/rlee/models/huggingface`
  - `TRANSFORMERS_CACHE_DIR=/home/rlee/models/transformers`

### Security Rules
1. **NEVER** allow services to download models automatically
2. **ALWAYS** use `local_files_only=True` in model loading
3. **VERIFY** models exist in cache before starting services
4. **AUDIT** model cache directory regularly

## 📁 Data Directory Structure

**Primary Data Directory:** `/home/rlee/june_data`
- **PostgreSQL:** `/home/rlee/june_data/postgres/` - Database files
- **MinIO:** `/home/rlee/june_data/minio/` - Object storage
- **NATS:** `/home/rlee/june_data/nats/data/` - Message broker data
- **NATS JetStream:** `/home/rlee/june_data/nats/jets_stream/` - Stream storage
- **Prometheus:** `/home/rlee/june_data/prometheus/` - Metrics data
- **Grafana:** `/home/rlee/june_data/grafana/` - Dashboard configs
- **Loki:** `/home/rlee/june_data/loki/` - Log aggregation
- **Logs:** `/home/rlee/june_data/logs/` - Application logs
- **Uploads:** `/home/rlee/june_data/uploads/` - User uploads
- **Backups:** `/home/rlee/june_data/backups/` - System backups

**Environment Variable:** `JUNE_DATA_DIR=/home/rlee/june_data`

**Important:** This directory will grow very large over time and is excluded from git.

## 📦 Model Artifacts and Test Data Management

### Model Artifacts

All containers produce model artifacts (outputs, caches, generated content) that are mounted to the host filesystem:

**Model Artifacts Directory:** `/home/rlee/june_data/model_artifacts/`
- **STT:** `/home/rlee/june_data/model_artifacts/stt/`
- **TTS:** `/home/rlee/june_data/model_artifacts/tts/`
- **Inference API:** `/home/rlee/june_data/model_artifacts/inference-api/`
- **Gateway:** `/home/rlee/june_data/model_artifacts/gateway/`

These directories are mounted into containers at `/app/model_artifacts/` and persist across container restarts.

**Docker Compose Configuration:**
Each service has a volume mount:
```yaml
volumes:
  - ${JUNE_DATA_DIR:-/home/rlee/june_data}/model_artifacts/<service>:/app/model_artifacts
```

### Test Artifacts

Test runs create isolated test artifacts in timestamped directories:

**Test Data Directory:** `/home/rlee/june_test_data/`
- Individual test runs: `run_YYYYMMDD_HHMMSS/`
  - `input_audio/` - TTS-generated input audio
  - `output_audio/` - Gateway response audio
  - `transcripts/` - Text transcripts
  - `metadata/` - Test metadata JSON
  - `container_artifacts/` - Artifacts copied from containers after tests

### Test Orchestration

The `scripts/run_tests_with_artifacts.sh` script provides full test orchestration:

1. **Starts Fresh Containers** - Spins up a clean docker-compose environment
2. **Runs Tests** - Executes Gateway round-trip tests
3. **Collects Artifacts** - Copies model and test artifacts from containers
4. **Shuts Down** - Tears down containers after completion

**Usage:**
```bash
# Full test run with artifact collection
./scripts/run_tests_with_artifacts.sh

# With custom test limit
TEST_LIMIT=5 ./scripts/run_tests_with_artifacts.sh
```

**Important Notes:**
- Model artifacts persist in `june_data` and are shared across runs
- Test artifacts are isolated per test run
- All artifacts are excluded from git (see `.gitignore`)
- Artifacts can be very large - monitor disk space

## 🐳 Container Environment

### Docker-First Development Strategy
**CRITICAL:** All development tools and CLI utilities MUST run in Docker containers.

**Why Docker-First?**
- **Consistency:** Same environment across all developers
- **Dependency Isolation:** No conflicts with host system libraries
- **Reproducibility:** Guaranteed working environment
- **Security:** Isolated execution environment
- **Version Control:** Exact dependency versions locked

### CLI Tools Container
**Service:** `cli-tools` (Profile: `tools`)
- **Purpose:** All command-line tools and utilities
- **Base Image:** `python:3.11-slim`
- **Dependencies:** ML libraries, development tools, audio processing
- **Access:** `docker exec -it june-cli-tools bash`

**Available Tools:**
- Model download script (`scripts/download_models.py`)
- Development utilities (black, isort, flake8, mypy)
- Testing tools (pytest, pytest-cov)
- Audio processing (whisper, TTS, librosa)

### Shared gRPC API Package (june-grpc-api)
- Location: `dev/june/packages/june-grpc-api`
- Contents: Only proto IDLs in `proto/` (e.g., `asr.proto`, `tts.proto`, `llm.proto`).
- Build: Stubs are generated at image build time inside each service container; no generated code is checked in.
- Install flow (each service Dockerfile):
  - Generate stubs with `grpcio-tools` into `june_grpc_api/` inside the build context.
  - Build a wheel (`python -m build`) and `pip install` the resulting wheel.
- Imports in services:
  - `from june_grpc_api import asr_pb2, asr_pb2_grpc`
- Benefits: Single source of truth, no sys.path hacks, deterministic imports, faster builds, simpler CI.

### GPU Configuration
- **Single GPU Sharing:** All services share GPU 0 via CUDA MPS
- **Memory Management:** Paged KV cache, model quantization
- **CUDA Environment Variables:**
  - `CUDA_VISIBLE_DEVICES=0`
  - `CUDA_MPS_ENABLE_PER_CTX_SM_PARTITIONING=1`

### Docker Compose Services
All services are orchestrated via `docker-compose.yml` with:
- Health checks for all services
- Volume mounts for model cache and data persistence
- Network isolation with `june_network`
- Resource limits and GPU allocation

## 📁 Project Structure

```
dev/june/
├── proto/                    # gRPC protobuf definitions
│   ├── asr.proto            # Speech-to-Text service
│   ├── tts.proto            # Text-to-Speech service
│   └── llm.proto            # LLM inference service
├── services/                 # Microservices
│   ├── gateway/             # FastAPI + WebSocket gateway
│   ├── inference-api/       # LLM orchestration
│   ├── stt/                 # Speech-to-Text
│   ├── tts/                 # Text-to-Speech
│   └── webapp/              # React chat interface
├── shared/                   # Common utilities
│   ├── config.py            # Configuration management
│   ├── utils.py             # Shared utilities
│   └── __init__.py
├── config/                   # Configuration files
│   ├── postgres-init.sql     # Database schema
│   ├── prometheus.yml        # Metrics config
│   ├── loki-config.yml       # Logging config
│   └── grafana/              # Dashboard configs
├── docs/                     # Comprehensive documentation
│   ├── README.md            # Documentation index
│   ├── API/                 # API documentation
│   ├── guides/              # User and developer guides
│   │   └── AGENTS.md        # This file
│   └── architecture/        # Architecture documentation
├── tests/integration/        # System integration tests
├── docker-compose.yml        # Service orchestration
├── .env.example             # Environment template
├── pyproject.toml           # Python dependencies
├── README.md                # Project overview and quick start
└── TODO.md                  # Task tracking
```

## 🔧 Development Practices

### Code Quality Standards
- **Python:** Black formatting, isort imports, flake8 linting, mypy type checking
- **TypeScript/React:** ESLint, Prettier formatting
- **Testing:** Comprehensive test suites for all services
- **Documentation:** Inline docstrings, README updates
- **Logging:** Use logging module, never print() statements

## 📝 Logging Standards (CRITICAL)

**MANDATORY:** All agents MUST use proper logging instead of print statements.

### Core Rules
1. **NEVER use print() for application output**
   - Use `logging` module for all output
   - Print statements should only appear in tests or one-off scripts
   - Print statements are not captured by log aggregation systems (Loki)

2. **Set up logging in all service entrypoints**
   - Configure logging at application startup
   - Use appropriate log levels
   - Include context in log messages
   - Integrate with centralized logging (Loki)

### Logging Setup in Entrypoints

**For June services, use the shared logging setup:**
```python
import logging
from inference_core import setup_logging, config

# Use centralized logging setup
setup_logging(config.monitoring.log_level, "service-name")
logger = logging.getLogger(__name__)

logger.info("Service starting...")
```

**Example for standalone services:**
```python
import logging
import os
from logging.handlers import RotatingFileHandler

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)
```

**Example for service modules:**
```python
import logging

# Get logger for this module
logger = logging.getLogger(__name__)

# Use appropriate log levels
logger.debug("Detailed debugging information")
logger.info("General informational message")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)
logger.critical("Critical error")
```

### Log Levels
- **DEBUG**: Detailed diagnostic information (development only)
- **INFO**: General informational messages (service startup, operations)
- **WARNING**: Unusual situations that don't stop execution
- **ERROR**: Errors that don't stop the service
- **CRITICAL**: Critical errors that may stop the service

### Best Practices
1. **Use structured logging with context**
   ```python
   logger.info("Request processed", extra={
       "request_id": request_id,
       "user_id": user_id,
       "duration_ms": duration
   })
   ```

2. **Include exception information**
   ```python
   try:
       operation()
   except Exception as e:
       logger.error("Operation failed", exc_info=True)
       # or
       logger.exception("Operation failed")  # Includes traceback
   ```

3. **Log service lifecycle events**
   ```python
   logger.info("Service starting", extra={"version": __version__})
   logger.info("Service ready", extra={"port": port})
   logger.info("Service shutting down gracefully")
   ```

4. **Never log sensitive data**
   - No passwords, tokens, API keys
   - Redact PII when necessary
   - Use log masking for sensitive fields

5. **Use appropriate log levels**
   - DEBUG: Verbose debugging (disable in production)
   - INFO: Normal operations, state changes
   - WARNING: Recoverable issues
   - ERROR: Failures that don't stop the service
   - CRITICAL: System-stopping errors

### Centralized Logging (Loki)
All services should log to stdout/stderr for Loki collection:
- Logs are automatically collected by Loki
- Use structured JSON format for complex logs
- Include correlation IDs for request tracing

### Environment Configuration
Set log level in docker-compose.yml:
```yaml
environment:
  - LOG_LEVEL=${LOG_LEVEL:-INFO}
```

Or use inference_core config:
```python
from inference_core import config
setup_logging(config.monitoring.log_level, "service-name")
```

### Common Mistakes to Avoid
1. ❌ Using print() instead of logger
2. ❌ Not configuring logging in entrypoints
3. ❌ Logging sensitive information
4. ❌ Using wrong log levels
5. ❌ Creating loggers without module names
6. ❌ Logging without context

### Examples

**Good:**
```python
logger.info("User authenticated", extra={"user_id": user_id})
logger.error("Database connection failed", exc_info=True)
logger.warning("Rate limit approaching", extra={"current": rate, "limit": limit})
```

**Bad:**
```python
print("User authenticated")  # ❌ Use logger
print(f"Error: {error}")     # ❌ No exception info
logger.info(f"Error: {error}")  # ❌ Should be logger.error
```

### Testing Strategy
Each service includes:
- **Unit Tests:** Individual component testing
- **Integration Tests:** Service interaction testing
- **Mock Tests:** External dependency isolation
- **Performance Tests:** Concurrent request handling
- **Error Handling Tests:** Failure scenario coverage

### Service Communication
- **Internal:** gRPC for service-to-service communication
- **External:** REST API and WebSocket for client access
- **Messaging:** NATS for pub/sub events
- **Storage:** PostgreSQL for structured data, MinIO for objects

## 🚀 Deployment Commands

### Service Build and Deploy (Docker)

All services (including Telegram and Discord bots) are deployed using Docker containers. Services are built using Docker Compose with Poetry for dependency management.

#### Building a Service

**Process:**
1. Services are built using Docker Compose
2. Dockerfiles use Poetry to install dependencies from `pyproject.toml`
3. Services run via `poetry run python -m essence <service-name>-service`

**Command:**
```bash
# Build services using Docker Compose
docker compose build telegram discord

# Start services
docker compose up -d telegram discord
```

**What Gets Built:**
- Docker images with all dependencies installed via Poetry
- Complete `essence` module copied into container
- Service-specific code from `services/<service-name>/`
- Shared dependencies (chat-service-base, packages, proto)
- Services run via essence command system

#### Testing Services

**Before deploying, test services using HTTP endpoints:**

**Telegram Service (Port 8080):**
```bash
# Health check
curl http://localhost:8080/health | jq

# Test agent message processing
curl -X POST http://localhost:8080/api/agent/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, this is a test"}' | jq

# Metrics
curl http://localhost:8080/metrics
```

**Discord Service (Port 8081):**
```bash
# Health check
curl http://localhost:8081/health | jq

# Metrics
curl http://localhost:8081/metrics
```

**Expected Results:**
- Health endpoint returns `{"status": "healthy", ...}`
- Agent message endpoint returns `{"success": true, "message": "..."}`
- Metrics endpoint returns Prometheus format metrics

#### Deploying a Service

**Process:**
1. Build Docker images using Docker Compose
2. Stop previous containers if running
3. Start new containers with updated images
4. Monitor container health and logs

**Command:**
```bash
# Build and deploy services
docker compose build telegram discord
docker compose up -d telegram discord

# View logs
docker compose logs -f telegram discord

# Check status
docker compose ps telegram discord
```

**Service Management:**
- Containers run via Docker Compose
- Logs: `docker compose logs <service-name>`
- Health checks: Built-in Docker healthchecks
- Restart: `docker compose restart <service-name>`

**Environment Configuration:**
Environment variables are configured in `docker-compose.yml` or via `.env` file:
- Service-specific tokens and configuration
- Port numbers and other settings
- Network configuration for MCP services

#### Service Management

**View Logs:**
```bash
# Docker Compose logs
docker compose logs -f <service-name>

# Last 100 lines
docker compose logs --tail=100 <service-name>

# Follow logs
docker compose logs -f --tail=50 <service-name>
```

**Stop Service:**
```bash
docker compose stop <service-name>
```

**Restart Service:**
```bash
docker compose restart <service-name>
```

**View Service Status:**
```bash
docker compose ps <service-name>
```

#### Command Pattern Architecture

All services use the `essence.command.Command` pattern:

**Base Command Interface:**
- `get_name()` - Command name (e.g., "telegram-service")
- `get_description()` - Command description
- `add_args(parser)` - Add command-specific arguments
- `init()` - Initialize service (setup, configuration)
- `run()` - Run service main loop (blocking)
- `cleanup()` - Clean up resources on shutdown

**Execution Flow:**
```bash
# Services are invoked via:
poetry run -m essence <service-name>-service [args...]

# Or directly:
python -m essence <service-name>-service [args...]
```

**Lifecycle:**
1. `essence.__main__.py` parses arguments and selects command
2. Command class instantiated with parsed args
3. `command.execute()` called:
   - Calls `init()` - Initialize resources
   - Calls `run()` - Main service loop (blocks)
   - Calls `cleanup()` - Clean up on exit/error

**Available Commands:**
- `telegram-service` - Telegram bot service
- `discord-service` - Discord bot service
- `tts` - Text-to-Speech service (future)
- `stt` - Speech-to-Text service (future)

#### Best Practices

1. **Always test before deploying:**
   - Build the service
   - Test HTTP endpoints if available
   - Verify health checks pass

2. **Monitor container health:**
   - Check Docker health status: `docker compose ps`
   - Verify service is responding to health checks
   - Monitor logs for startup errors

3. **Use Docker Compose for management:**
   - All services managed via `docker compose`
   - Consistent deployment process
   - Built-in health checks and restart policies
   - Monitor application logs for runtime issues

4. **Graceful shutdown:**
   - Services handle SIGTERM/SIGINT for graceful shutdown
   - Always use PID file to stop services
   - Wait for shutdown before redeploying

5. **Environment variables:**
   - Keep `.env` files secure (600 permissions)
   - Never commit `.env` files to git
   - Document required variables in service README

## 🚀 Deployment Commands (Docker)

### Start Full System
```bash
cd dev/june
cp .env.example .env
# Edit .env with your configuration
docker-compose up -d
```

### Individual Service Development
```bash
# Build specific service
cd services/gateway
docker build -t june-gateway .

# Run with live reload
docker run -p 8000:8000 -v $(pwd):/app june-gateway
```

### Health Checks
```bash
# Run comprehensive health checks
./run_checks.sh

# Check specific service
curl http://localhost:8000/health  # Gateway
curl http://localhost:50051/health # Inference API (gRPC)
```

## 🔍 Monitoring and Debugging

### Metrics Endpoints
- Gateway: `http://localhost:8000/metrics`
- Inference API: `http://localhost:8001/metrics`
- STT: `http://localhost:8002/metrics`
- TTS: `http://localhost:8003/metrics`

### Dashboards
- Grafana: `http://localhost:3000` (admin/admin)
- Prometheus: `http://localhost:9090`
- Jaeger: `http://localhost:16686`

### Logs
```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f gateway
docker-compose logs -f inference-api
```

## 🎙️ STT Service Updates and Validation

### Current STT Implementation
- Model: Whisper `tiny.en` (CPU by default; can be set via `STT_DEVICE`).
- Service: gRPC with unary `Recognize` and streaming `RecognizeStream` (IDL in `asr.proto`).
- Container: Installs `openai-whisper`, `ffmpeg`, and the shared `june-grpc-api` package during build.

### Validation Dataset
- Source: Small subset of LibriSpeech (OpenSLR test-clean; capped to ~20 pairs for fast checks).
- Download script (runs inside CLI tools): `services/cli-tools/scripts/download_librispeech_small.py`
- Index output: `${JUNE_DATA_DIR}/datasets/librispeech_small/index.json` with `{id, audio, text}` pairs.

### Validation Methods
- Solo STT validation: `services/cli-tools/scripts/test_stt_validate.py`
  - Reads FLAC, converts to WAV 16k PCM, calls STT gRPC, compares hypotheses.
  - Quick metric: prefix-3 word match counts (sanity check). Example result: 10/20 (~50%).
  - Extendable to WER/CER using `jiwer` if needed.

### How to Run
```
# Start CLI tools and STT only
docker compose --profile tools up -d cli-tools
docker compose up -d stt

# Download dataset and run validation (script orchestrates both steps)
./scripts/validate_stt.sh
```

### Notes
- All generated artifacts and datasets are stored under `${JUNE_DATA_DIR}` and excluded from git.
- The STT container no longer bind-mounts service code to avoid masking generated gRPC stubs.

## 🛠️ Common Development Tasks

### Using CLI Tools Container
**Start CLI Tools:**
```bash
# Start CLI tools container
docker-compose --profile tools up -d cli-tools

# Access CLI tools
docker exec -it june-cli-tools bash
```

**Model Management:**
```bash
# Download all models
docker exec -it june-cli-tools python scripts/download_models.py --all

# Download specific model
docker exec -it june-cli-tools python scripts/download_models.py --model Qwen/Qwen3-30B-A3B-Thinking-2507

# Check model status
docker exec -it june-cli-tools python scripts/download_models.py --status

# List authorized models
docker exec -it june-cli-tools python scripts/download_models.py --list
```

**Development Tools:**
```bash
# Code formatting
docker exec -it june-cli-tools black /app/scripts/
docker exec -it june-cli-tools isort /app/scripts/

# Linting
docker exec -it june-cli-tools flake8 /app/scripts/
docker exec -it june-cli-tools mypy /app/scripts/

# Testing
docker exec -it june-cli-tools pytest /app/scripts/
```

### Adding New CLI Tools
1. **Add dependencies** to `services/cli-tools/requirements-cli.txt`
2. **Create tool script** in `services/cli-tools/scripts/`
3. **Update Dockerfile** if system dependencies needed
4. **Test tool** in CLI container
5. **Update documentation** with usage instructions

### Adding New Features
1. **Update protobuf schemas** if needed
2. **Implement service logic** with comprehensive tests
3. **Update docker-compose.yml** for new services
4. **Add health checks** and metrics
5. **Update documentation**

### Adding New Models
1. **Add to AUTHORIZED_MODELS** in `scripts/download_models.py`
2. **Update download script** with new model category
3. **Test model download** using the script
4. **Update service code** to use local cache only
5. **Verify no internet access** during runtime
6. **Update documentation** with new model info

### Debugging Issues
1. **Check service health** with `./run_checks.sh`
2. **Review logs** for error messages
3. **Verify GPU allocation** with `nvidia-smi`
4. **Test individual services** in isolation
5. **Check network connectivity** between services

### Performance Optimization
1. **Monitor GPU memory usage** with `nvidia-smi`
2. **Check Prometheus metrics** for bottlenecks
3. **Profile service performance** with timing logs
4. **Optimize model loading** and inference
5. **Scale services horizontally** if needed

## 🔐 Security Considerations

### Security Overview

June Agent implements comprehensive security measures. All agents working on the project must be aware of and follow security best practices.

**For comprehensive security documentation, see:**
- **[Security Documentation](../SECURITY.md)** - Complete security guide covering architecture, practices, and procedures
- **[Security Runbook](../SECURITY_RUNBOOK.md)** - Operational security procedures and incident response
- **[Security Audit Report](../SECURITY_AUDIT_REPORT.md)** - Security audit findings and recommendations
- **[Security Headers](../SECURITY_HEADERS.md)** - Security headers configuration
- **[Rate Limiting](../RATE_LIMITING.md)** - Rate limiting implementation details
- **[june-security Package](../../packages/june-security/README.md)** - Security package documentation

### Authentication
- JWT tokens for API access with access and refresh tokens
- Service-to-service authentication tokens
- Strong password requirements (minimum 12 characters, complexity)
- Token expiration and rotation

### Network Security
- Internal service communication over gRPC (TLS in production)
- External access through Gateway only
- CORS configuration for webapp (not `*` in production)
- Security headers (CSP, HSTS, X-Frame-Options, etc.)

### Data Protection
- Environment variables for secrets (never commit secrets)
- Secure storage of audio/text data
- User session management
- Encryption at rest (PostgreSQL, MinIO) - see Security Audit Report
- Encryption in transit (TLS/HTTPS)

### Input Validation
- Comprehensive input sanitization using june-security package
- Parameterized queries for SQL injection prevention
- File upload validation (type, size, content)
- Path traversal prevention

### Rate Limiting
- Per-user, per-IP, and per-endpoint rate limits
- Redis-based sliding window algorithm
- In-memory fallback if Redis unavailable
- Rate limit headers in responses

### Security Monitoring
- Threat detection via june-security package
- Audit logging of all security-relevant operations
- Prometheus metrics for security events
- Grafana dashboards for security monitoring

### Security Best Practices for Agents

1. **Never commit secrets** to version control
2. **Use strong, random secrets** (minimum 32 characters for JWT)
3. **Validate all inputs** at service boundaries
4. **Use parameterized queries** for database operations
5. **Follow security configuration** guidelines
6. **Review security documentation** before making security-related changes
7. **Test security features** when implementing or modifying them
8. **Report security vulnerabilities** privately (not in public issues)

## 📊 Performance Characteristics

### Expected Performance
- **Text Generation:** ~50-100 tokens/second
- **Speech Recognition:** ~2-3x real-time
- **Text-to-Speech:** ~1-2x real-time
- **Memory Usage:** ~20-30GB GPU memory
- **Latency:** <500ms for simple requests

### Scaling Considerations
- **Horizontal:** Stateless services can be scaled
- **Vertical:** GPU memory limits model size
- **Database:** PostgreSQL can be sharded
- **Storage:** MinIO can be clustered

## 🎯 Future Development Areas

### Planned Features
- **Multi-language Support:** Language detection and translation
- **Advanced RAG:** Document ingestion and retrieval
- **Custom Voice Training:** User-specific voice models
- **Tool Integration:** External API connections
- **Fine-tuning Interface:** Model customization UI

### Architecture Improvements
- **Kubernetes Deployment:** Production orchestration
- **Service Mesh:** Advanced networking
- **Caching Layer:** Redis for performance
- **Load Balancing:** Multiple gateway instances

## 🚨 Troubleshooting Guide

### Common Issues

**GPU Memory Errors:**
- Check `nvidia-smi` for memory usage
- Reduce model quantization or context length
- Restart services to clear memory

**Service Connection Errors:**
- Verify docker-compose network configuration
- Check service health endpoints
- Review NATS connectivity

**Model Loading Failures:**
- Verify Hugging Face token
- Check internet connectivity
- Clear model cache if corrupted

**WebSocket Connection Issues:**
- Check Gateway service status
- Verify authentication tokens
- Review browser console for errors

### Recovery Procedures
1. **Full System Restart:** `docker-compose down && docker-compose up -d`
2. **Service-Specific Restart:** `docker-compose restart <service>`
3. **Data Reset:** Remove volumes and restart
4. **Model Cache Clear:** Remove `~/.cache/huggingface` volume

## 📝 Development Notes

### Current Limitations
- Single GPU deployment only
- Limited to English language models
- Basic tool integration
- No persistent user sessions

### Technical Debt
- WebSocket authentication needs improvement
- Error handling could be more granular
- Metrics collection needs expansion
- Test coverage could be higher

### Known Issues
- Occasional GPU memory fragmentation
- WebSocket reconnection handling
- Audio format compatibility
- Model loading race conditions

## 🌐 Cross-Container Network Architecture

June services communicate with external MCP services (Bucket-O-Facts, Doc-O-Matic, To-Do-Rama) using Docker's external network feature. This allows services in different `docker-compose.yml` files to communicate seamlessly.

### Network Architecture

**MCP Services** (Bucket-O-Facts, Doc-O-Matic, To-Do-Rama):
- Each MCP service runs in its own Docker Compose project
- Each creates its own network (e.g., `bucket-o-facts_bucket-network`)
- Network names follow the pattern: `{project-name}_{network-name}`

**June Services** (Telegram, Discord):
- Connect to MCP service networks as **external networks**
- Defined in `docker-compose.yml` under the `networks` section
- Services can communicate with MCP services using container names

### Network Configuration

In `june/docker-compose.yml`:

```yaml
networks:
  june_network:
    driver: bridge
  # External networks for MCP services
  bucket-network:
    external: true
    name: bucket-o-facts_bucket-network
  doc-o-matic-network:
    external: true
    name: docomatic-mcp-service_doc-o-matic-network
  todo-network:
    external: true
    name: todo-network
```

Services connect to these networks:

```yaml
services:
  telegram:
    networks:
      - june_network
      - bucket-network
      - doc-o-matic-network
      - todo-network
  
  discord:
    networks:
      - june_network
      - bucket-network
      - doc-o-matic-network
      - todo-network
```

### How It Works

1. **MCP Service Starts**: When an MCP service (e.g., Bucket-O-Facts) starts, it creates its network
2. **June Service Connects**: June services reference the network as external
3. **Communication**: Services can communicate using container names:
   - `http://bucket-o-facts:8006/mcp/sse`
   - `http://doc-o-matic:8005/mcp/sse`
   - `http://todo-mcp-service:8004/mcp/sse`

### Network Lifecycle

- **Network Creation**: MCP service creates network when first started
- **Network Persistence**: Network persists even if MCP service stops (if other services reference it)
- **Network Cleanup**: Network is removed only when no containers reference it
- **Reference Counting**: Docker tracks how many services use each network

### Benefits

- **Decoupled Deployment**: MCP services can be updated independently
- **Service Isolation**: Each service manages its own network
- **Flexible Scaling**: Services can be scaled independently
- **No Central Orchestration**: No need for a single docker-compose file

### Troubleshooting

**Network Not Found Error:**
```
Error: network bucketofacts-mcp-service_bucket-network not found
```

**Solution**: Ensure the MCP service is running and has created its network:
```bash
# Check if network exists
docker network ls | grep bucket

# Start MCP service to create network
cd /path/to/bucketofacts-mcp-service
docker compose up -d
```

**Container Cannot Reach MCP Service:**
- Verify network names match exactly (case-sensitive)
- Check that both services are on the same network
- Verify container names match what's configured in MCP client config

---

**Last Updated:** December 2024  
**Version:** 0.2.0  
**Maintainer:** June Agent Team
