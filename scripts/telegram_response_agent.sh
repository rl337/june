#!/bin/bash
# Telegram Response Agent for June project
# Usage: telegram_response_agent.sh [user_id] [chat_id] "<user_message>"
# Output: JSON response on stdout, errors on stderr

set -euo pipefail

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTICNESS_DIR="/home/rlee/dev/agenticness"

# Set standardized directories
export AGENTICNESS_DATA_DIR="${AGENTICNESS_DATA_DIR:-${JUNE_DATA_DIR:-/home/rlee/june_data}/switchboard}"
export PROMPTS_DIR="${PROMPTS_DIR:-${AGENTICNESS_DIR}/prompts/telegram-response}"
export WORKING_DIRECTORY="${WORKING_DIRECTORY:-/app}"

# Source logging for error messages (before exec to wrapper)
INCLUDE_DIR="${AGENTICNESS_DIR}/include"
if [ -d "$INCLUDE_DIR" ] && [ -f "${INCLUDE_DIR}/logging.sh" ]; then
    source "${INCLUDE_DIR}/logging.sh"
else
    # Fallback log_error function if logging.sh not available
    log_error() {
        echo "ERROR: $*" >&2
    }
fi

# Parse arguments
if [ $# -eq 1 ]; then
    USER_ID=""
    CHAT_ID=""
    USER_MESSAGE="${1:-}"
elif [ $# -eq 3 ]; then
    USER_ID="${1:-}"
    CHAT_ID="${2:-}"
    USER_MESSAGE="${3:-}"
else
    log_error "Usage: $0 [user_id] [chat_id] \"<user_message>\""
    log_error "       OR: $0 \"<user_message>\" (legacy, no session support)"
    exit 1
fi

# Check environment variables
if [ -z "$USER_ID" ] && [ -n "${TELEGRAM_USER_ID:-}" ]; then
    USER_ID="${TELEGRAM_USER_ID}"
fi
if [ -z "$CHAT_ID" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    CHAT_ID="${TELEGRAM_CHAT_ID}"
fi

if [ -z "$USER_MESSAGE" ]; then
    log_error "User message cannot be empty"
    exit 1
fi

# Determine session role for role-based lookup
if [ -n "$USER_ID" ] && [ -n "$CHAT_ID" ]; then
    SESSION_ROLE="telegram-${USER_ID}-${CHAT_ID}"
else
    SESSION_ROLE="telegram-response"
fi

# Set standardized directories
export AGENTICNESS_DATA_DIR="${AGENTICNESS_DATA_DIR:-${JUNE_DATA_DIR:-/home/rlee/june_data}/switchboard}"
export PROMPTS_DIR="${PROMPTS_DIR:-${AGENTICNESS_DIR}/prompts/telegram-response}"
export WORKING_DIRECTORY="${WORKING_DIRECTORY:-/app}"

# Agent configuration
ROLE="$SESSION_ROLE"
PROMPT_FILE="${PROMPTS_DIR}/prompt.txt"
TIMEOUT="${AGENT_TIMEOUT:-300}"
MAX_ERRORS="${MAX_CONSECUTIVE_ERRORS:-3}"

# Call Python executor
exec python3 -m agenticness.commands.execute_cursor_agent \
    --role "$ROLE" \
    --prompt-file "$PROMPT_FILE" \
    --working-dir "$WORKING_DIRECTORY" \
    --timeout "$TIMEOUT" \
    --max-errors "$MAX_ERRORS" \
    --output-format "stream-json" \
    ${USER_MESSAGE:+--message "$USER_MESSAGE"}

