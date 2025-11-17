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
#
# The script will run forever, sleeping 60 seconds between each agent invocation.

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

# Function to check if output contains ConnectError
check_for_connect_error() {
    local output_file="$1"
    # Check for various ConnectError patterns
    if grep -qiE "(ConnectError|ConnectionError|connection error|unavailable.*Error)" "$output_file" 2>/dev/null; then
        return 0  # Found ConnectError
    else
        return 1  # No ConnectError
    fi
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
- Work on ONE task per iteration (don't try to do everything at once)
- Be thorough but focused
- Update the plan immediately after completing work
- If you encounter blockers, document them in the plan
- If a task is too large, break it down and update the plan
- Always verify your changes work before marking tasks complete
- All operations must run as the rlee user on the host. There is no sudo access or running as root.

**Current Context:**
- Project root: /home/rlee/dev/june
- Refactor plan: REFACTOR_PLAN.md
- Goal: Pare down june to bare essentials for Telegram/Discord voice round trip
- Services to keep: telegram, discord, stt, tts, inference-api
- Services removed: gateway, postgres, minio, redis, nats, orchestrator, webapp

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

Now, read REFACTOR_PLAN.md and begin working on an unfinished task.
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
            CURSOR_AGENT_ARGS=("agent" "--print" "--force" "--output-format" "text" "--stream-partial-output")
            # After first iteration, we'll resume
            SESSION_EXISTS=1
        elif [[ $SESSION_EXISTS -eq 0 ]]; then
            # Session file was removed (likely due to ConnectError) - create new session
            log "Creating new chat session (previous session was removed)..."
            CURSOR_AGENT_ARGS=("agent" "--print" "--force" "--output-format" "text" "--stream-partial-output")
            # After this iteration, we'll resume
            SESSION_EXISTS=1
        else
            # Session exists: resume existing session
            log "Resuming chat session: $SESSION_ID"
            CURSOR_AGENT_ARGS=("agent" "--print" "--force" "--output-format" "stream-json" "--stream-partial-output" "--resume" "$SESSION_ID")
        fi
        
        # Create temporary file to capture output for ConnectError detection
        TEMP_OUTPUT=$(mktemp)
        trap "rm -f $TEMP_OUTPUT" EXIT
        
        # Run cursor-agent with the prompt
        log "Invoking cursor-agent with args: ${CURSOR_AGENT_ARGS[*]}"
        
        # Run cursor-agent, capturing output to both temp file and log, while also showing on stdout
        # Use unbuffered output so we can see progress in real-time
        if echo "$PROMPT" | "$CURSOR_AGENT_CMD" "${CURSOR_AGENT_ARGS[@]}" 2>&1 | tee "$TEMP_OUTPUT" | tee -a "$LOG_FILE"; then
            # Check for ConnectError even on success (sometimes it exits 0 but has errors)
            if check_for_connect_error "$TEMP_OUTPUT"; then
                log "WARNING: ConnectError detected in output - will create new session on next iteration"
                # Remove old session file - next iteration will detect it's missing and create new session
                rm -f "$SESSION_ID_FILE"
                log "Removed stuck session file - new session will be created on next iteration"
            else
                log "Iteration $ITERATION completed successfully"
            fi
        else
            EXIT_CODE=$?
            # Check if the error was a ConnectError
            if check_for_connect_error "$TEMP_OUTPUT"; then
                log "WARNING: ConnectError detected (exit code: $EXIT_CODE) - will create new session on next iteration"
                # Remove old session file - next iteration will detect it's missing and create new session
                rm -f "$SESSION_ID_FILE"
                log "Removed stuck session file - new session will be created on next iteration"
            else
                log "WARNING: Iteration $ITERATION encountered an error (exit code: $EXIT_CODE)"
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

