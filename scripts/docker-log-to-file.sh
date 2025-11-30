#!/bin/bash
# Script to copy Docker container logs to /logs directory for Promtail
# This runs as a sidecar or init container to capture stdout/stderr logs
#
# Usage: docker-log-to-file.sh <container-name> <service-name>

CONTAINER_NAME="${1}"
SERVICE_NAME="${2:-${CONTAINER_NAME}}"
LOG_DIR="/logs"
LOG_FILE="${LOG_DIR}/${SERVICE_NAME}.log"

mkdir -p "${LOG_DIR}"

# Follow Docker logs and write to file with timestamps
docker logs -f "${CONTAINER_NAME}" 2>&1 | while IFS= read -r line; do
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $line" >> "${LOG_FILE}"
done







