#!/bin/bash
# Log wrapper script that captures stdout/stderr and writes to both:
# 1. Original stdout/stderr (for Docker logs)
# 2. Log files in /logs/ directory (for Promtail to ship to Loki)
#
# Usage: log-wrapper.sh <service-name> <original-command> [args...]

SERVICE_NAME="${1:-unknown}"
shift

LOG_DIR="/var/log/june/${SERVICE_NAME}"
LOG_FILE="${LOG_DIR}/${SERVICE_NAME}.log"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Function to add timestamp and write to both stdout and log file
# Uses file descriptor redirection to keep file handle open for efficiency
# When logrotate rotates the file, the next write will create a new file automatically
add_timestamp_and_log() {
    local log_file="$1"
    # Open log file as file descriptor 3, keep it open
    exec 3>> "$log_file"
    while IFS= read -r line; do
        local timestamped="[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $line"
        echo "$timestamped"  # Write to stdout (Docker captures this)
        echo "$timestamped" >&3  # Write to log file via file descriptor (more efficient)
    done
    exec 3>&-  # Close file descriptor when done
}

# Start the original command, capturing both stdout and stderr
# Both go to stdout (for Docker) and to the log file (for Promtail)
exec "$@" 2>&1 | add_timestamp_and_log "$LOG_FILE"

