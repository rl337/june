#!/bin/bash
# Common cursor-agent wrapper script with session management, error tracking, and retry logic
# Usage: cursor_agent_wrapper.sh [options]
# 
# Options:
#   --role ROLE              Session role (required, e.g., "normal", "architect")
#   --prompt-file FILE       Path to prompt file (required)
#   --prompt-text TEXT       Prompt text (alternative to --prompt-file)
#   --working-dir DIR        Working directory (default: /app)
#   --timeout SECONDS        Timeout in seconds (default: 3600)
#   --max-errors COUNT       Max consecutive errors before session reset (default: 3)
#   --output-format FORMAT   Output format: stream-json or text (default: stream-json)
#   --message TEXT           Optional message to substitute in prompt (for ${MESSAGE} variable)
#
# This script handles:
# - Session management with persistence
# - Error tracking and counting
# - Session replacement after max-errors consecutive failures
# - Timeout handling
# - Proper cursor-agent invocation with --resume

set -euo pipefail

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JUNE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENTICNESS_DIR="/home/rlee/dev/agenticness"

# Set standardized directories
export AGENTICNESS_DATA_DIR="${AGENTICNESS_DATA_DIR:-${JUNE_DATA_DIR:-/home/rlee/june_data}/switchboard}"
export STATE_DIR="${STATE_DIR:-${AGENTICNESS_DATA_DIR}}"
export SESSION_STATE_DIR="${SESSION_STATE_DIR:-${AGENTICNESS_DATA_DIR}/sessions}"

# Source required includes from agenticness
INCLUDE_DIR="${AGENTICNESS_DIR}/include"
if [ ! -d "$INCLUDE_DIR" ]; then
    echo "Error: agenticness include directory not found: $INCLUDE_DIR" >&2
    exit 1
fi

source "${INCLUDE_DIR}/logging.sh"
source "${INCLUDE_DIR}/session_manager.sh"

# Parse arguments
ROLE=""
PROMPT_FILE=""
PROMPT_TEXT=""
WORKING_DIR="${WORKING_DIRECTORY:-/app}"
TIMEOUT="${AGENT_TIMEOUT:-3600}"
MAX_ERRORS="${MAX_CONSECUTIVE_ERRORS:-3}"
OUTPUT_FORMAT="stream-json"
MESSAGE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --role)
            ROLE="$2"
            shift 2
            ;;
        --prompt-file)
            PROMPT_FILE="$2"
            shift 2
            ;;
        --prompt-text)
            PROMPT_TEXT="$2"
            shift 2
            ;;
        --working-dir)
            WORKING_DIR="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --max-errors)
            MAX_ERRORS="$2"
            shift 2
            ;;
        --output-format)
            OUTPUT_FORMAT="$2"
            shift 2
            ;;
        --message)
            MESSAGE="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$ROLE" ]; then
    log_error "--role is required"
    exit 1
fi

if [ -z "$PROMPT_FILE" ] && [ -z "$PROMPT_TEXT" ]; then
    log_error "Either --prompt-file or --prompt-text is required"
    exit 1
fi

# Set required environment variables
export CURSOR_AGENT_EXE="${CURSOR_AGENT_EXE:-cursor-agent}"
export AGENT_ID="${AGENT_ID:-${ROLE}-agent}"
export AGENT_TIMEOUT="$TIMEOUT"

# Error tracking files
ERROR_COUNT_FILE="${SESSION_STATE_DIR}/${ROLE}.error_count"
SESSION_FILE="${SESSION_STATE_DIR}/${ROLE}.session"

# Function to get current error count
get_error_count() {
    if [ -f "$ERROR_COUNT_FILE" ]; then
        cat "$ERROR_COUNT_FILE" 2>/dev/null | tr -d '[:space:]' || echo "0"
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

# Function to clear session (for error recovery)
clear_session_for_role() {
    log_warning "Clearing session for role '$ROLE' due to consecutive errors"
    rm -f "$SESSION_FILE"
    reset_error_count
    log "Session cleared - new session will be created on next execution"
}

# Get or create session for this role
SESSION_ID=$(get_or_create_session "$ROLE")
if [ -z "$SESSION_ID" ]; then
    log_error "Failed to get or create session for role: $ROLE"
    exit 1
fi

log "Using session ID: $SESSION_ID for role: $ROLE"

# Check error count and clear session if needed
ERROR_COUNT=$(get_error_count)
if [ "$ERROR_COUNT" -ge "$MAX_ERRORS" ]; then
    log_warning "Error count ($ERROR_COUNT) >= max errors ($MAX_ERRORS) - clearing session"
    clear_session_for_role
    # Get a new session after clearing
    SESSION_ID=$(get_or_create_session "$ROLE")
    if [ -z "$SESSION_ID" ]; then
        log_error "Failed to get new session after clearing"
        exit 1
    fi
    log "Using new session ID: $SESSION_ID"
fi

# Load prompt
if [ -n "$PROMPT_FILE" ]; then
    if [ ! -f "$PROMPT_FILE" ]; then
        log_error "Prompt file not found: $PROMPT_FILE"
        exit 1
    fi
    PROMPT=$(cat "$PROMPT_FILE")
elif [ -n "$PROMPT_TEXT" ]; then
    PROMPT="$PROMPT_TEXT"
fi

# Substitute variables in prompt
if [ -n "$MESSAGE" ]; then
    PROMPT=$(echo "$PROMPT" | sed "s|\${MESSAGE}|${MESSAGE}|g")
    PROMPT=$(echo "$PROMPT" | sed "s|\${USER_MESSAGE}|${MESSAGE}|g")
    PROMPT=$(echo "$PROMPT" | sed "s|\${TASK_INSTRUCTION}|${MESSAGE}|g")
    PROMPT=$(echo "$PROMPT" | sed "s|\${INSTRUCTION}|${MESSAGE}|g")
fi

# Change to working directory
cd "$WORKING_DIR" || {
    log_error "Failed to change to working directory: $WORKING_DIR"
    exit 1
}

# Build cursor-agent command
CURSOR_AGENT_CMD=(
    "$CURSOR_AGENT_EXE"
    "agent"
    "--print"
    "--output-format" "$OUTPUT_FORMAT"
)

# Add --stream-partial-output for stream-json format
if [ "$OUTPUT_FORMAT" = "stream-json" ]; then
    CURSOR_AGENT_CMD+=("--stream-partial-output")
fi

# Always use --resume with session ID (cursor-agent will create session if it doesn't exist)
CURSOR_AGENT_CMD+=("--resume" "$SESSION_ID")
CURSOR_AGENT_CMD+=("--model" "auto")

# Execute cursor-agent with timeout
log "Executing cursor-agent for role '$ROLE' with timeout ${TIMEOUT}s..."
log "Command: ${CURSOR_AGENT_CMD[*]}"

# Record start time
START_TIME=$(date +%s)

# Run cursor-agent with timeout
# timeout exit code 124 means the command was terminated due to timeout
if echo "$PROMPT" | timeout "$TIMEOUT" "${CURSOR_AGENT_CMD[@]}" 2>&1; then
    # Success - reset error count
    reset_error_count
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log_success "Agent execution completed successfully in ${DURATION}s"
    exit 0
else
    EXIT_CODE=$?
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    # Check if timeout occurred (exit code 124 from timeout command)
    if [ $EXIT_CODE -eq 124 ]; then
        log_error "Agent execution timed out after ${TIMEOUT}s"
        ERROR_COUNT=$(increment_error_count)
    else
        log_error "Agent execution failed with exit code $EXIT_CODE after ${DURATION}s"
        ERROR_COUNT=$(increment_error_count)
    fi
    
    log_warning "Consecutive error count: $ERROR_COUNT (max: $MAX_ERRORS)"
    
    # If we have max-errors or more consecutive errors, clear the session
    if [ "$ERROR_COUNT" -ge "$MAX_ERRORS" ]; then
        log_warning "$ERROR_COUNT consecutive errors detected - session will be cleared for next execution"
        clear_session_for_role
    fi
    
    exit $EXIT_CODE
fi


