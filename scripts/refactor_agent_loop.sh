#!/bin/bash
#
# Refactor Agent Loop Script
# 
# This script runs cursor-agent in a continuous loop, instructing it to:
# 1. Check todorama for available tasks (prioritizing human_interface tasks from Telegram/Discord)
# 2. Reserve and work on tasks from todorama
# 3. Update task status in todorama and send responses for human_interface tasks
#
# Usage:
#   ./scripts/refactor_agent_loop.sh
#   AGENT_TIMEOUT_SECONDS=3600 ./scripts/refactor_agent_loop.sh  # 1 hour timeout
#
# The script will run forever, sleeping 60 seconds between each agent invocation.
# Each agent iteration has a timeout (default: 30 minutes) to prevent stuck processes.
# Long operations (model downloads, builds, etc.) must be run in background.
# The timeout can be configured via AGENT_TIMEOUT_SECONDS environment variable.
#
# User Response Polling:
# The script also runs periodic polling for user responses in the background:
# - Polls for user responses to agent messages (default: every 2 minutes)
# - Checks for pending user requests from USER_REQUESTS.md
# - Processes NEW messages from USER_MESSAGES.md (Phase 21)
# - Polling interval can be configured via USER_POLLING_INTERVAL_SECONDS environment variable
# - Polling can be disabled by setting ENABLE_USER_POLLING=0

set -euo pipefail

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# REFACTOR_PLAN.md is no longer used - all tasks are in todorama

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

# Polling interval for user responses (in seconds)
# Default: 2 minutes (120 seconds) - checks for user responses periodically
# Can be overridden via USER_POLLING_INTERVAL_SECONDS environment variable
USER_POLLING_INTERVAL_SECONDS="${USER_POLLING_INTERVAL_SECONDS:-120}"

# Flag to enable/disable user polling
# Set to "0" to disable user response polling
# Can be overridden via ENABLE_USER_POLLING environment variable
ENABLE_USER_POLLING="${ENABLE_USER_POLLING:-1}"

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

# PID file for user polling background process
USER_POLLING_PID_FILE="$PROJECT_ROOT/.user_polling_pid"

# Function to poll for user responses
# This runs in the background and periodically checks for user responses to agent messages
poll_user_responses() {
    local polling_interval="$1"
    log "Starting user response polling (interval: ${polling_interval}s)"
    
    while true; do
        sleep "$polling_interval"
        
        # Check if polling should continue (check if PID file still exists)
        if [[ ! -f "$USER_POLLING_PID_FILE" ]]; then
            log "User polling PID file removed - stopping polling"
            break
        fi
        
        # Poll for user responses
        log_file_only "Polling for user responses..."
        if cd "$PROJECT_ROOT" && poetry run python -m essence poll-user-responses >> "$LOG_FILE" 2>&1; then
            log_file_only "User response polling completed successfully"
        else
            log_file_only "User response polling encountered an error (non-fatal, will retry)"
        fi
        
        # Check for pending user requests
        log_file_only "Checking for pending user requests..."
        if cd "$PROJECT_ROOT" && poetry run python -m essence read-user-requests >> "$LOG_FILE" 2>&1; then
            log_file_only "Pending requests check completed"
        else
            log_file_only "Pending requests check encountered an error (non-fatal, will retry)"
        fi
        
        # Process NEW messages from USER_MESSAGES.md (Phase 21)
        log_file_only "Processing NEW messages from USER_MESSAGES.md..."
        if cd "$PROJECT_ROOT" && poetry run python -m essence process-user-messages >> "$LOG_FILE" 2>&1; then
            log_file_only "User messages processing completed"
        else
            log_file_only "User messages processing encountered an error (non-fatal, will retry)"
        fi
    done
    
    log "User response polling stopped"
}

# Function to start user polling in background
start_user_polling() {
    if [[ "$ENABLE_USER_POLLING" != "1" ]]; then
        log "User polling disabled (ENABLE_USER_POLLING=$ENABLE_USER_POLLING)"
        return 0
    fi
    
    # Check if polling is already running
    if [[ -f "$USER_POLLING_PID_FILE" ]]; then
        local existing_pid=$(cat "$USER_POLLING_PID_FILE" 2>/dev/null | tr -d '[:space:]')
        if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
            log "User polling already running (PID: $existing_pid)"
            return 0
        else
            # PID file exists but process is dead - clean up
            log "Removing stale user polling PID file"
            rm -f "$USER_POLLING_PID_FILE"
        fi
    fi
    
    # Start polling in background
    poll_user_responses "$USER_POLLING_INTERVAL_SECONDS" &
    local polling_pid=$!
    echo "$polling_pid" > "$USER_POLLING_PID_FILE"
    log "Started user response polling (PID: $polling_pid, interval: ${USER_POLLING_INTERVAL_SECONDS}s)"
}

# Function to stop user polling
stop_user_polling() {
    if [[ ! -f "$USER_POLLING_PID_FILE" ]]; then
        return 0
    fi
    
    local polling_pid=$(cat "$USER_POLLING_PID_FILE" 2>/dev/null | tr -d '[:space:]')
    if [[ -n "$polling_pid" ]] && kill -0 "$polling_pid" 2>/dev/null; then
        log "Stopping user response polling (PID: $polling_pid)"
        kill "$polling_pid" 2>/dev/null || true
        # Wait a bit for graceful shutdown
        sleep 2
        # Force kill if still running
        if kill -0 "$polling_pid" 2>/dev/null; then
            log "Force killing user polling process"
            kill -9 "$polling_pid" 2>/dev/null || true
        fi
    fi
    
    rm -f "$USER_POLLING_PID_FILE"
    log "User response polling stopped"
}

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

1. **Check MCP todorama for available tasks** - Query for tasks to work on:
   - Use MCP todorama service to query available tasks: `mcp_todorama_list_available_tasks` with agent_type="implementation", project_id=1, limit=10
   - **PRIORITY:** Human interaction tasks (task_type="human_interface") should be handled first - these are user messages from Telegram/Discord
   - If tasks are available, reserve one using `mcp_todorama_reserve_task` and work on it
   - If no tasks available, you're done for this iteration
   - **CRITICAL:** Always reserve tasks before working on them, and always complete or unlock them when done
   - **CRITICAL:** User interactions from Telegram/Discord are automatically created as todorama tasks (type="human_interface") - no file queue processing needed

**Working on Related Projects:**
- You CAN and SHOULD work on the `home_infra` project at `/home/rlee/dev/home_infra` when tasks require it
- The `home_infra` project provides shared infrastructure (TensorRT-LLM, nginx, prometheus, etc.) that june services use
- If a task requires changes to `home_infra/docker-compose.yml` or related files, you should make those changes
- This is NOT external work - it's part of the june project infrastructure

3. **Check for GitHub Actions failures** - Before picking a new task:
   - Check the GitHub Actions page: https://github.com/rl337/june/actions
   - Look for any failed workflow runs (status: failed, red X icon)
   - If failures are found:
     - Click on the failed workflow run to view details
     - Read the error logs to identify the specific failure
     - Fix the issue causing the failure
     - Commit and push the fix
     - Verify the fix by checking if a new workflow run passes
   - **Priority:** Fixing GitHub Actions failures takes precedence over new tasks
   - Only proceed to pick a new task if there are no active failures
   - **If you fix a CI issue, create a task in todorama to track it:** Use MCP to create a task documenting what was fixed

4. **Work on reserved task** - If you have a reserved task from todorama:
   - Read the task details carefully
   - Follow the task instructions
   - Add progress updates using `mcp_todorama_add_task_update` as you work
   - If you encounter blockers, add a blocker update and unlock the task
   - When complete, mark the task as complete using `mcp_todorama_complete_task`
   - **If the task is a human_interface task (user interaction):**
     - The task description contains the user's message and context (user_id, chat_id, platform, message_id)
     - Process the user's request and generate an appropriate response
     - Send the response to the user via Telegram/Discord using the Message API
     - Update the task with your response before completing it
     - **Note:** Task creation and completion automatically trigger notifications to the user, so you don't need to send separate status messages

5. **Perform the task** - Complete the selected task. This may involve:
   - Removing code dependencies on removed services
   - Implementing tracing or metrics
   - Cleaning up code
   - Writing tests
   - Building services
   - **Setting up Qwen3 model on GPU (Phase 10.1-10.2) - NEW PRIORITY**
   - **Developing coding agent (Phase 10.4) - NEW PRIORITY**
   - **Setting up benchmark evaluation with sandboxes (Phase 10.5) - NEW PRIORITY**
   - Any other task from the plan

6. **Update task status in MCP todorama** - After completing the task:
   - If you worked on an MCP task, mark it complete: `cursor-agent mcp call todorama complete_task --task_id <id> --agent_id looping_agent --notes "Completed: <summary>"`
   - Add task updates during work: `cursor-agent mcp call todorama add_task_update --task_id <id> --agent_id looping_agent --content "<progress>" --update_type progress`
   - If you encountered errors, unlock the task: `cursor-agent mcp call todorama unlock_task --task_id <id> --agent_id looping_agent`

7. **Store learnings in MCP bucketofacts** - After completing significant work:
   - Store important decisions: `cursor-agent mcp call bucketofacts create_fact --subject "june" --predicate "uses" --object "TensorRT-LLM for LLM inference"`
   - Store code patterns: `cursor-agent mcp call bucketofacts create_fact --subject "june" --predicate "pattern" --object "All services use gRPC for inter-service communication"`
   - Query before making decisions: `cursor-agent mcp call bucketofacts query_facts --subject "june"` to see what's been learned

8. **Create new tasks in todorama** - If during your work you discover:
   - New tasks that need to be done → Create tasks in todorama using `mcp_todorama_create_task`
   - Issues or blockers → Create blocker tasks or add updates to existing tasks
   - Better approaches or alternatives → Document in task updates or create new tasks
   - Dependencies between tasks → Link tasks using parent_task_id and relationship_type
   - **CRITICAL:** All task management happens in todorama, not in files
   - **PENDING TASKS TO CREATE:** There are pending tasks documented in `/home/rlee/dev/june/scripts/create_pending_tasks.py` that need to be created in Todorama. Run this script to create them (requires API key configuration first):
     - Task 1: Fix Telegram service not responding to user messages (bug_fix, high priority)
     - Task 2: Formalize release versioning with auto-increment for all components (feature)

**Agent-to-User Communication:**
- **CRITICAL:** For human_interface tasks, you MUST send a response message to the user
- Use the Message API client: `from essence.chat.message_api_client import send_message_via_api`
- **When to send messages:**
  - **ALWAYS** when completing a human_interface task - send the response to the user
  - Extract user_id, chat_id, and platform from the task description
  - **DO NOT send status messages** for other task types - task creation/completion notifications are automatic
  - If no human_interface tasks were completed, do NOT send a message
- **How to send:**
  ```python
  from essence.chat.message_api_client import send_message_via_api
  import os
  
  # Get user/chat ID from environment or use defaults
  user_id = os.getenv("TELEGRAM_WHITELISTED_USERS", "").split(",")[0] or os.getenv("TELEGRAM_USER_ID", "your_user_id")
  chat_id = user_id  # For DMs, chat_id is same as user_id
  
  result = send_message_via_api(
      user_id=user_id,
      chat_id=chat_id,
      message="Your message here",
      platform="auto",  # Tries Telegram first, falls back to Discord
      message_type="progress",  # or "help_request", "clarification", "status"
      api_url=os.getenv("MESSAGE_API_URL", "http://localhost:8082")
  )
  ```
- **IMPORTANT:** Message API service must be running: `docker compose up -d message-api` or `poetry run python -m essence message-api-service`
- **Message types:** "text", "error", "status", "clarification", "help_request", "progress"

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
    - **Important:** Add a task update in todorama documenting that a long operation is running in background, including:
      - The command that was started
      - The log file where output is being written
      - How to check if it completed (e.g., "check build.log for completion" or "check if docker compose build process is still running")
    - In the next iteration, check if the background operation completed before proceeding with dependent tasks
- Work on ONE task per iteration (don't try to do everything at once)
- Be thorough but focused
- Update task status in todorama immediately after completing work
- If you encounter blockers, add blocker updates to the task in todorama
- If a task is too large, break it down into subtasks in todorama
- Always verify your changes work before marking tasks complete
- All operations must run as the rlee user on the host. There is no sudo access or running as root.
  - **CRITICAL:** NEVER use `sudo` - not even in defensive patterns like `sudo cmd || cmd`
  - If you encounter permission errors, check file/directory ownership and permissions first
  - Create directories/files only in locations owned by the rlee user (e.g., `/var/data/june/*`, `/home/rlee/*`)
  - For Docker volume mounts, ensure host directories exist with proper permissions (775 or 755) before mounting
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

**MCP Services Workflow (REQUIRED):**

**Step 1: Check for available tasks in todorama FIRST**
- Query available tasks: `cursor-agent mcp call todorama list_available_tasks --agent_type implementation --project_id 1 --limit 10`
- If tasks found, reserve one: `cursor-agent mcp call todorama reserve_task --task_id <id> --agent_id looping_agent`
- Work on the reserved task
- Add progress updates: `cursor-agent mcp call todorama add_task_update --task_id <id> --agent_id looping_agent --content "<update>" --update_type progress`
- When done: `cursor-agent mcp call todorama complete_task --task_id <id> --agent_id looping_agent --notes "<summary>"`
- On error: `cursor-agent mcp call todorama unlock_task --task_id <id> --agent_id looping_agent` (always unlock on errors)

**Step 2: Create tasks for operational work**
- When you encounter operational tasks (e.g., "compile model", "run end-to-end test"), create tasks in todorama:
  - `cursor-agent mcp call todorama create_task --project_id 1 --title "<task>" --description "<details>" --agent_type implementation --agent_id looping_agent`
- This allows tracking operational work that's blocked on external factors

**Step 3: Store learnings in bucketofacts**
- After significant work, store decisions: `cursor-agent mcp call bucketofacts create_fact --subject "june" --predicate "<relation>" --object "<value>"`
- Query before decisions: `cursor-agent mcp call bucketofacts query_facts --subject "june"` to see what's been learned
- Use semantic search: `cursor-agent mcp call bucketofacts semantic_search --query "<question>" --limit 5`

**Step 4: Document in docomatic (optional)**
- For major architectural decisions: `cursor-agent mcp call docomatic create_document --title "<title>" --content "<content>"`
- Search existing docs: `cursor-agent mcp call docomatic search_sections --query "<topic>"`

**MCP Service Details:**
- **todorama:** 49 tools for task management (project_id=1 for june project)
- **bucketofacts:** 17 tools for knowledge storage
- **docomatic:** 23 tools for documentation
- **Access:** `cursor-agent mcp call <service> <tool> --<arg> <value>`
- **CRITICAL:** Always reserve tasks before working, always complete or unlock them - never leave tasks in_progress
- **YOUR AGENT ID:** `looping_agent` - Always use this as your agent_id when reserving, updating, or completing tasks

**Current Context:**
- Project root: /home/rlee/dev/june
- **Your Agent ID:** `looping_agent` - Always use this when reserving, updating, or completing tasks
- **Task Management:** All tasks are in todorama (project_id=1) - no REFACTOR_PLAN.md task management
- **Note:** All existing tasks in todorama should be treated as if they were created/assigned to `looping_agent`. When you work on tasks, use agent_id="looping_agent"
- **Primary Goal:** Pare down june to bare essentials for Telegram/Discord voice round trip
- **Extended Goal:** Get Qwen3-30B-A3B-Thinking-2507 running on GPU in containers and develop coding agent for benchmark evaluation
- Services to keep: telegram, discord, stt, tts
- LLM Inference: TensorRT-LLM (in home_infra/shared-network, default) or NVIDIA NIM (nim-qwen3:8001). Legacy inference-api service available via --profile legacy for backward compatibility only.
- Services removed: gateway, postgres, minio, redis, nats, orchestrator, webapp
- **User Interactions:** Telegram/Discord services create todorama tasks directly (type="human_interface") - no file queue, tasks appear immediately in todorama
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
  - **After each commit, immediately push to upstream:** `git push origin main` (or `git push` if upstream is configured)
  - If push fails (e.g., network issue), log the error but continue - the commit is still saved locally

**STEP 2: After completing each task**
- Commit your changes using git with a descriptive commit message
- Use the same commit format as above
- Group related changes into logical commits (one commit per task or logical unit)
- **After each commit, immediately push to upstream:** `git push origin main` (or `git push` if upstream is configured)
- If push fails (e.g., network issue), log the error but continue - the commit is still saved locally
- DO NOT leave uncommitted changes - always commit and push your work before moving to the next task

**CRITICAL - DO NOT UPDATE COMMIT COUNTS:**
- **DO NOT automatically update commit counts** - The commit count (e.g., "85 commits ahead of origin/main") is informational only and does not need to be kept in sync
- **DO NOT create commits solely to update commit counts** - This creates an infinite loop where each commit increments the count, requiring another update
- Only update commit counts if:
  1. You are explicitly documenting a major milestone or release
  2. The commit count is significantly outdated (e.g., more than 100 commits off)
  3. You are asked to do so in a specific task
- Focus on actual refactoring work, not documentation maintenance of commit counts

**Priority Order:**
1. **CRITICAL - GitHub Actions failures** - Fix any failed workflow runs first (check https://github.com/rl337/june/actions)
2. Phase 10.1-10.2: Qwen3 model setup on GPU (if not yet done)
3. Phase 10.4: Coding agent development (if model is ready)
4. Phase 10.5: Benchmark evaluation setup (if coding agent is ready)
5. Other phases from the plan

**Reference Documents:**
- QWEN3_SETUP_PLAN.md - Detailed Qwen3 setup instructions

Now, check todorama for available tasks to work on. Prioritize human_interface tasks (user messages from Telegram/Discord).
PROMPT_EOF
}

# Main loop
main() {
    log "Starting refactor agent loop"
    log "Project root: $PROJECT_ROOT"
    log "Task management: todorama (project_id=1)"
    log "Agent ID: looping_agent"
    log "Log file: $LOG_FILE"
    
    # Check if cursor-agent is available
    check_cursor_agent
    CURSOR_AGENT_CMD=$(get_cursor_agent_cmd)
    log "Using cursor-agent command: $CURSOR_AGENT_CMD"
    
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
    
    # Start user response polling in background
    start_user_polling
    
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
cleanup_on_exit() {
    log "Script interrupted. Cleaning up..."
    stop_user_polling
    exit 0
}
trap cleanup_on_exit INT TERM

# Run main function
main

