#!/bin/bash
#
# Refactor Agent Loop Script
# 
# This script runs cursor-agent in a continuous loop, instructing it to:
# 1. Read REFACTOR_PLAN.md
# 2. Pick an unfinished task to work on
# 3. Perform the task
# 4. Update REFACTOR_PLAN.md with progress and discoveries
#
# Usage:
#   ./scripts/refactor_agent_loop.sh
#   AGENT_TIMEOUT_SECONDS=3600 ./scripts/refactor_agent_loop.sh  # 1 hour timeout
#
# The script will run forever, sleeping 60 seconds between each agent invocation.
# Each agent iteration has a timeout (default: 30 minutes) to prevent stuck processes.
# Long operations (model downloads, builds, etc.) must be run in background.
# The timeout can be configured via AGENT_TIMEOUT_SECONDS environment variable.

set -euo pipefail

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REFACTOR_PLAN="$PROJECT_ROOT/REFACTOR_PLAN.md"

# Change to project root
cd "$PROJECT_ROOT"

# Log file for the loop
LOG_FILE="${PROJECT_ROOT}/refactor_agent_loop.log"

# Session ID file to persist session across iterations
SESSION_ID_FILE="${PROJECT_ROOT}/.refactor_agent_session_id"

# Timeout for each agent iteration (in seconds)
# Default: 30 minutes (1800 seconds) - prevents stuck processes
# Long operations (model downloads, builds, etc.) must be run in background
# Can be overridden via AGENT_TIMEOUT_SECONDS environment variable
AGENT_TIMEOUT_SECONDS="${AGENT_TIMEOUT_SECONDS:-1800}"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Function to log to file only (no stdout)
# Use this when you don't want output in command substitution
log_file_only() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Function to check if cursor-agent is available
check_cursor_agent() {
    if command -v cursor-agent &> /dev/null; then
        return 0
    elif command -v cursor_agent &> /dev/null; then
        return 0
    else
        log "ERROR: cursor-agent command not found in PATH"
        log "Please ensure cursor-agent is installed and in your PATH"
        exit 1
    fi
}

# Function to get cursor-agent command
get_cursor_agent_cmd() {
    if command -v cursor-agent &> /dev/null; then
        echo "cursor-agent"
    elif command -v cursor_agent &> /dev/null; then
        echo "cursor_agent"
    fi
}

# Function to get or create session ID
# Returns only the session ID (no log messages) to stdout
# Log messages go to log file only (not stdout)
get_session_id() {
    if [[ -f "$SESSION_ID_FILE" ]]; then
        # Session ID exists, read it (strip any whitespace)
        cat "$SESSION_ID_FILE" | tr -d '[:space:]'
    else
        # No session ID, create a new one (UUID v4 format)
        # Generate a UUID-like identifier for the session
        SESSION_ID=$(uuidgen 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())" 2>/dev/null || echo "$(date +%s)-$(shuf -i 1000-9999 -n 1)")
        echo "$SESSION_ID" > "$SESSION_ID_FILE"
        # Log to file only so it doesn't interfere with the return value
        log_file_only "Created new session ID: $SESSION_ID"
        # Return only the session ID to stdout
        echo "$SESSION_ID"
    fi
}

# File to track consecutive error count (non-zero exit codes)
ERROR_COUNT_FILE="$PROJECT_ROOT/.refactor_agent_error_count"

# Function to get current error count
get_error_count() {
    if [[ -f "$ERROR_COUNT_FILE" ]]; then
        cat "$ERROR_COUNT_FILE" | tr -d '[:space:]'
    else
        echo "0"
    fi
}

# Function to increment error count
increment_error_count() {
    local current_count=$(get_error_count)
    local new_count=$((current_count + 1))
    echo "$new_count" > "$ERROR_COUNT_FILE"
    echo "$new_count"
}

# Function to reset error count
reset_error_count() {
    echo "0" > "$ERROR_COUNT_FILE"
}


# Function to create the prompt for the agent
create_prompt() {
    cat << 'PROMPT_EOF'
You are working on refactoring the june project. Your task is to:

1. **Read REFACTOR_PLAN.md** - Read the entire refactoring plan to understand the current state and what needs to be done.

2. **Pick an unfinished task** - Look for tasks marked with ⏳ TODO in the REFACTOR_PLAN.md. Choose one that:
   - Is clearly defined and actionable
   - You have enough context to complete
   - Will make meaningful progress toward the refactoring goals
   - Is appropriate for a single iteration (not too large)

3. **Perform the task** - Complete the selected task. This may involve:
   - Removing code dependencies on removed services
   - Implementing tracing or metrics
   - Cleaning up code
   - Writing tests
   - Building services
   - **Setting up Qwen3 model on GPU (Phase 10.1-10.2) - NEW PRIORITY**
   - **Developing coding agent (Phase 10.4) - NEW PRIORITY**
   - **Setting up benchmark evaluation with sandboxes (Phase 10.5) - NEW PRIORITY**
   - Any other task from the plan

4. **Update REFACTOR_PLAN.md** - After completing the task:
   - Mark the completed task(s) as ✅ COMPLETED
   - Add a brief summary of what was done
   - If you discovered new tasks or issues, add them to the appropriate section with ⏳ TODO
   - If you found that a task needs to be broken down further, update the plan accordingly
   - Document any important discoveries or decisions made

5. **Document discoveries** - If during your work you discover:
   - New tasks that need to be done
   - Issues or blockers
   - Better approaches or alternatives
   - Dependencies between tasks
   Add these to REFACTOR_PLAN.md in the appropriate section so the next iteration can understand and act on them.

**Important Guidelines:**
- **CRITICAL - 30 MINUTE TIMEOUT:** Each iteration has a 30-minute timeout. If an operation takes longer than 30 minutes, it will be terminated. 
  - **Use timeouts for individual commands:** Always use the `timeout` command for operations that might hang (tests, network operations, etc.):
    - Tests: `timeout 600 pytest tests/...` (10 minutes for test suites)
    - Docker operations: `timeout 1800 docker compose build` (30 minutes for builds)
    - Network requests: `timeout 60 curl ...` (1 minute for HTTP requests)
    - Any command that might hang: `timeout <seconds> <command>`
    - If a command times out, investigate why it hung and fix the issue
  - **For operations that legitimately take longer than 30 minutes**, you MUST run them in the background:
    - **Primary method:** Use `nohup` and `&` to run commands in background: `nohup command > output.log 2>&1 &`
    - For Docker operations: `nohup docker compose build > build.log 2>&1 &` or `docker compose build &` (if you don't need output)
    - For long-running scripts: `nohup python script.py > script.log 2>&1 &`
    - Check background job status: `ps aux | grep <command>` or check log files (e.g., `tail -f output.log`)
    - Check if a process is still running: `pgrep -f "<command_pattern>"` or `ps aux | grep <pattern>`
    - **Important:** Document in REFACTOR_PLAN.md that a long operation is running in background, including:
      - The command that was started
      - The log file where output is being written
      - How to check if it completed (e.g., "check build.log for completion" or "check if docker compose build process is still running")
    - In the next iteration, check if the background operation completed before proceeding with dependent tasks
- Work on ONE task per iteration (don't try to do everything at once)
- Be thorough but focused
- Update the plan immediately after completing work
- If you encounter blockers, document them in the plan
- If a task is too large, break it down and update the plan
- Always verify your changes work before marking tasks complete
- All operations must run as the rlee user on the host. There is no sudo access or running as root.
- **Container-first:** For Phase 10 tasks (Qwen3 setup), all model operations must happen in Docker containers - use `docker compose run` or `docker compose exec` for all model-related work
- **Sandbox isolation:** For benchmark tasks (Phase 10.5), ensure each task runs in an isolated sandbox (container/chroot) with full activity logging and reviewability
- **Efficiency evaluation:** When working on benchmarks, capture not just correctness but also efficiency metrics (commands executed, time to solution, resource usage)
- **CRITICAL - Model Loading:** Before loading any model (LLM, embedding, STT, TTS), ALWAYS check if the model is already loaded in memory:
  - Check if the model object exists and is not None (e.g., `self._model is not None` or `self.llm_strategy._model is not None`)
  - Check if the tokenizer exists (e.g., `self._tokenizer is not None`)
  - If both model and tokenizer are already loaded, skip the loading step and log that the model is already loaded
  - This prevents duplicate model loads which consume massive amounts of memory
  - This is especially critical for large models like Qwen3-30B which can use 15-20GB+ of memory
  - When modifying model loading code, always add checks to prevent reloading if already loaded

**MCP Services for Self-Directed Tasks and Data:**
- **Use MCP services for task management and data storage** - The project has MCP (Model Context Protocol) services available that you should use for:
  - **Task Management (todorama service):** Use MCP tools to manage your own tasks and track progress:
    - `list_available_tasks(agent_type, project_id, limit)` - Find tasks you can work on
    - `reserve_task(task_id, agent_id)` - Lock a task before working on it (MANDATORY)
    - `complete_task(task_id, agent_id, notes, ...)` - Mark tasks complete when done (MANDATORY)
    - `unlock_task(task_id, agent_id)` - Unlock tasks on errors (MANDATORY - always use try/except/finally)
    - `add_task_update(task_id, agent_id, content, update_type)` - Add progress updates during work
    - `get_task_context(task_id)` - Get full context for a task
    - `create_task(...)` - Create new tasks for future work
    - `query_tasks(...)` - Query tasks by various criteria
    - The "june" project (project_id=1) is available in the todorama database
    - **CRITICAL:** Always reserve tasks before working, and always complete or unlock them - never leave tasks in_progress
  - **Knowledge Storage (bucketofacts service):** Use MCP tools to store and retrieve facts and knowledge:
    - `create_fact(subject, predicate, object, ...)` - Store facts about the codebase, decisions, or learnings
    - `query_facts(...)` - Query stored facts
    - `semantic_search(query, limit, threshold)` - Search facts semantically
    - `get_fact(fact_id, ...)` - Retrieve specific facts
    - Use this to remember important decisions, code patterns, architecture choices, etc.
  - **Documentation (docomatic service):** Use MCP tools to manage documentation:
    - `create_document(title, ...)` - Create documentation documents
    - `create_section(document_id, heading, body, ...)` - Add sections to documents
    - `update_document(document_id, ...)` - Update documentation
    - `search_sections(query, ...)` - Search documentation
    - Use this to maintain project documentation, architecture docs, API docs, etc.
- **How to use MCP services:**
  - MCP services are accessible via `cursor-agent mcp` commands
  - You can call MCP tools directly in your agent interactions
  - Services are available at: http://localhost:8000/mcp/{service-name}/sse
  - The todorama service has 49 tools, bucketofacts has 17 tools, docomatic has 23 tools
  - **Best practice:** Use todorama to track your own work, bucketofacts to store learnings, and docomatic for documentation
- **Self-directed task management:**
  - Instead of only working from REFACTOR_PLAN.md, you can:
    - Query available tasks from the todorama service
    - Create tasks for work you identify needs to be done
    - Track your progress using task updates
    - Store learnings in bucketofacts for future reference
    - Document your work in docomatic
  - This enables more autonomous operation and better tracking of work across iterations

**Current Context:**
- Project root: /home/rlee/dev/june
- Refactor plan: REFACTOR_PLAN.md
- **Primary Goal:** Pare down june to bare essentials for Telegram/Discord voice round trip
- **Extended Goal:** Get Qwen3-30B-A3B-Thinking-2507 running on GPU in containers and develop coding agent for benchmark evaluation
- Services to keep: telegram, discord, stt, tts, inference-api
- Services removed: gateway, postgres, minio, redis, nats, orchestrator, webapp
- **NEW PRIORITY:** Phase 10 (Qwen3 setup and coding agent) - see REFACTOR_PLAN.md Phase 10
- **Container-first requirement:** All model operations, downloads, and inference must happen in Docker containers - no host system pollution
- **Sandbox requirement:** All benchmark executions must run in isolated sandboxes (containers/chroot) with full reviewability

**CRITICAL:** Run tests at the start and end of every turn and fix any breakages.

**CRITICAL - GIT COMMITS REQUIRED:**

**STEP 1: Check for outstanding changes FIRST**
- Before starting any new work, check if there are uncommitted changes: `git status`
- If there are uncommitted changes:
  - Examine the changes: `git diff` and `git status`
  - Group related changes into logical commits (e.g., all changes for one service, all changes for one feature)
  - Commit each logical group separately with meaningful commit messages
  - Commit format: "Refactor: <brief description>" or "Fix: <brief description>" or "Add: <brief description>"
  - Examples:
    - "Refactor: Remove PostgreSQL dependencies from telegram service"
    - "Add: OpenTelemetry tracing spans to voice processing operations"
    - "Fix: Update docker-compose.yml to remove gateway service"
  - DO NOT commit unrelated changes together - create separate commits for each logical group
  - After committing all outstanding changes, check if there are unpushed commits and push them upstream

**STEP 2: After completing each task**
- Commit your changes using git with a descriptive commit message
- Use the same commit format as above
- Group related changes into logical commits (one commit per task or logical unit)
- After committing, check if there are unpushed commits and push them upstream
- DO NOT leave uncommitted changes - always commit your work before moving to the next task

**Priority Order:**
1. Phase 10.1-10.2: Qwen3 model setup on GPU (if not yet done)
2. Phase 10.4: Coding agent development (if model is ready)
3. Phase 10.5: Benchmark evaluation setup (if coding agent is ready)
4. Other phases from the plan

**Reference Documents:**
- REFACTOR_PLAN.md - Main refactoring plan with all phases
- QWEN3_SETUP_PLAN.md - Detailed Qwen3 setup instructions (referenced in Phase 10)

Now, read REFACTOR_PLAN.md and begin working on an unfinished task, prioritizing Phase 10 if applicable.
PROMPT_EOF
}

# Main loop
main() {
    log "Starting refactor agent loop"
    log "Project root: $PROJECT_ROOT"
    log "Refactor plan: $REFACTOR_PLAN"
    log "Log file: $LOG_FILE"
    
    # Check if cursor-agent is available
    check_cursor_agent
    CURSOR_AGENT_CMD=$(get_cursor_agent_cmd)
    log "Using cursor-agent command: $CURSOR_AGENT_CMD"
    
    # Check if REFACTOR_PLAN.md exists
    if [[ ! -f "$REFACTOR_PLAN" ]]; then
        log "ERROR: REFACTOR_PLAN.md not found at $REFACTOR_PLAN"
        exit 1
    fi
    
    # Create the prompt
    PROMPT=$(create_prompt)
    
    # Check if session file already exists
    if [[ -f "$SESSION_ID_FILE" ]]; then
        log "Session file exists - will resume existing session"
        SESSION_EXISTS=1
    else
        log "No session file found - will create new session on first iteration"
        SESSION_EXISTS=0
    fi
    
    # Get or create session ID
    SESSION_ID=$(get_session_id)
    log "Using session ID: $SESSION_ID"
    
    # Counter for iterations
    ITERATION=0
    
    # Main loop
    while true; do
        ITERATION=$((ITERATION + 1))
        log "=========================================="
        log "Starting iteration $ITERATION"
        log "=========================================="
        
        # Check if session file exists (may have been deleted due to ConnectError)
        if [[ ! -f "$SESSION_ID_FILE" ]]; then
            SESSION_EXISTS=0
            SESSION_ID=$(get_session_id)
        else
            SESSION_EXISTS=1
            SESSION_ID=$(get_session_id)
        fi
        
        # Determine if we should create new session or resume
        if [[ $SESSION_EXISTS -eq 0 ]] && [[ $ITERATION -eq 1 ]]; then
            # First iteration and no existing session: create new session (don't use --resume)
            log "Creating new chat session..."
            # For new sessions, use text format (stream-partial-output requires stream-json)
            CURSOR_AGENT_ARGS=("agent" "--print" "--force" "--output-format" "text")
            # After first iteration, we'll resume
            SESSION_EXISTS=1
        elif [[ $SESSION_EXISTS -eq 0 ]]; then
            # Session file was removed (likely due to ConnectError) - create new session
            log "Creating new chat session (previous session was removed)..."
            # For new sessions, use text format (stream-partial-output requires stream-json)
            CURSOR_AGENT_ARGS=("agent" "--print" "--force" "--output-format" "text")
            # After this iteration, we'll resume
            SESSION_EXISTS=1
        else
            # Session exists: resume existing session
            log "Resuming chat session: $SESSION_ID"
            # For resumed sessions, use stream-json format with stream-partial-output for real-time visibility
            CURSOR_AGENT_ARGS=("agent" "--print" "--force" "--output-format" "stream-json" "--stream-partial-output" "--resume" "$SESSION_ID")
        fi
        
        # Create temporary file to capture output for ConnectError detection
        TEMP_OUTPUT=$(mktemp)
        trap "rm -f $TEMP_OUTPUT" EXIT
        
        # Run cursor-agent with the prompt
        log "Invoking cursor-agent with args: ${CURSOR_AGENT_ARGS[*]}"
        log "Timeout set to ${AGENT_TIMEOUT_SECONDS} seconds ($(($AGENT_TIMEOUT_SECONDS / 60)) minutes)"
        
        # Record start time for timeout tracking
        ITERATION_START_TIME=$(date +%s)
        
        # Run cursor-agent with timeout, capturing output to both temp file and log, while also showing on stdout
        # Use unbuffered output so we can see progress in real-time
        # timeout exit code 124 means the command was terminated due to timeout
        if echo "$PROMPT" | timeout "$AGENT_TIMEOUT_SECONDS" "$CURSOR_AGENT_CMD" "${CURSOR_AGENT_ARGS[@]}" 2>&1 | tee "$TEMP_OUTPUT" | tee -a "$LOG_FILE"; then
            # Success - reset error count
            reset_error_count
            log "Iteration $ITERATION completed successfully"
        else
            EXIT_CODE=$?
            ITERATION_END_TIME=$(date +%s)
            ITERATION_DURATION=$((ITERATION_END_TIME - ITERATION_START_TIME))
            
            # Check if timeout occurred (exit code 124 from timeout command)
            if [[ $EXIT_CODE -eq 124 ]]; then
                log "ERROR: Iteration $ITERATION timed out after ${AGENT_TIMEOUT_SECONDS} seconds ($(($AGENT_TIMEOUT_SECONDS / 60)) minutes)"
                log "Long operations (model downloads, builds, etc.) must be run in background. See agent prompt for instructions."
                # Timeout is treated as an error for error counting
                ERROR_COUNT=$(increment_error_count)
            else
                ERROR_COUNT=$(increment_error_count)
                log "WARNING: Iteration $ITERATION encountered an error (exit code: $EXIT_CODE) after ${ITERATION_DURATION} seconds - consecutive error count: $ERROR_COUNT"
            fi
            
            # If we have 3 or more consecutive non-zero exit codes, create a new session
            if [[ $ERROR_COUNT -ge 3 ]]; then
                log "WARNING: $ERROR_COUNT consecutive errors detected - will create new session on next iteration"
                # Remove old session file - next iteration will detect it's missing and create new session
                rm -f "$SESSION_ID_FILE"
                reset_error_count
                log "Removed stuck session file and reset error count - new session will be created on next iteration"
            else
                log "Continuing to next iteration..."
            fi
        fi
        
        # Clean up temp file
        rm -f "$TEMP_OUTPUT"
        
        log "Sleeping 60 seconds before next iteration..."
        sleep 60
    done
}

# Handle script interruption
trap 'log "Script interrupted. Exiting..."; exit 0' INT TERM

# Run main function
main

