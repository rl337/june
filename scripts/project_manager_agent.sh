#!/bin/bash
# Project Manager Agent (Enid) for June project - Coordinates releases and project management
# Usage: project_manager_agent.sh [instruction]
# Output: JSON response on stdout, errors on stderr

set -euo pipefail

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTICNESS_DIR="/home/rlee/dev/agenticness"

# Set standardized directories
export AGENTICNESS_DATA_DIR="${AGENTICNESS_DATA_DIR:-${JUNE_DATA_DIR:-/home/rlee/june_data}/switchboard}"
export PROMPTS_DIR="${PROMPTS_DIR:-${AGENTICNESS_DIR}/prompts/project-manager}"
export WORKING_DIRECTORY="${WORKING_DIRECTORY:-/app}"

# Parse arguments
INSTRUCTION="${1:-}"

# Agent configuration
ROLE="project-manager"
PROMPT_FILE="${PROMPTS_DIR}/prompt.txt"
TIMEOUT="${AGENT_TIMEOUT:-3600}"
MAX_ERRORS="${MAX_CONSECUTIVE_ERRORS:-3}"

# Call Python executor
exec python3 -m agenticness.commands.execute_cursor_agent \
    --role "$ROLE" \
    --prompt-file "$PROMPT_FILE" \
    --working-dir "$WORKING_DIRECTORY" \
    --timeout "$TIMEOUT" \
    --max-errors "$MAX_ERRORS" \
    --output-format "stream-json" \
    ${INSTRUCTION:+--message "$INSTRUCTION"}

