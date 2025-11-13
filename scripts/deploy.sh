#!/bin/bash
#
# Deploy script for June services
# Stops previous version, deploys new version, and starts the service
#
# Usage: ./scripts/deploy.sh <service-name> <tarball-name>
# Example: ./scripts/deploy.sh telegram june-telegram-20240101-120000.tar.gz
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build"
SERVICE_NAME="${1:-}"
TARBALL_NAME="${2:-}"

if [ -z "${SERVICE_NAME}" ] || [ -z "${TARBALL_NAME}" ]; then
    echo "Error: Service name and tarball name are required"
    echo "Usage: $0 <service-name> <tarball-name>"
    echo "Example: $0 telegram june-telegram-20240101-120000.tar.gz"
    exit 1
fi

TARBALL_PATH="${BUILD_DIR}/${TARBALL_NAME}"
if [ ! -f "${TARBALL_PATH}" ]; then
    echo "Error: Tarball not found: ${TARBALL_PATH}"
    exit 1
fi

# Verify checksum if it exists
CHECKSUM_FILE="${TARBALL_PATH}.sha256"
if [ -f "${CHECKSUM_FILE}" ]; then
    echo "Verifying checksum..."
    cd "${BUILD_DIR}"
    if ! sha256sum -c "${CHECKSUM_FILE}"; then
        echo "Error: Checksum verification failed!"
        exit 1
    fi
    echo "Checksum verified."
fi

# Service paths
SERVICE_RUN_DIR="/usr/local/june/${SERVICE_NAME}"
SERVICE_LOG_DIR="/var/log/june"
CONSOLE_LOG="${SERVICE_LOG_DIR}/${SERVICE_NAME}.console"
APP_LOG="${SERVICE_LOG_DIR}/${SERVICE_NAME}.log"

echo "Deploying ${SERVICE_NAME} service..."
echo "Tarball: ${TARBALL_PATH}"
echo "Target directory: ${SERVICE_RUN_DIR}"

# Create log directory
mkdir -p "${SERVICE_LOG_DIR}"
chmod 755 "${SERVICE_LOG_DIR}" 2>/dev/null || true

# Stop previous version if running
echo "Checking for running service..."
if [ -d "${SERVICE_RUN_DIR}" ]; then
    # Try to find and stop the process
    # Look for process running the service
    PID_FILE="${SERVICE_RUN_DIR}/service.pid"
    if [ -f "${PID_FILE}" ]; then
        OLD_PID=$(cat "${PID_FILE}")
        if ps -p "${OLD_PID}" > /dev/null 2>&1; then
            echo "Stopping previous service (PID: ${OLD_PID})..."
            kill -TERM "${OLD_PID}" || true
            # Wait for graceful shutdown
            for i in {1..10}; do
                if ! ps -p "${OLD_PID}" > /dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            # Force kill if still running
            if ps -p "${OLD_PID}" > /dev/null 2>&1; then
                echo "Force killing service (PID: ${OLD_PID})..."
                kill -KILL "${OLD_PID}" || true
            fi
        fi
        rm -f "${PID_FILE}"
    fi
    
    # Also try to find by process name
    pkill -f "essence ${SERVICE_NAME}-service" || true
    sleep 2
fi

# Delete previous version
if [ -d "${SERVICE_RUN_DIR}" ]; then
    echo "Removing previous version from ${SERVICE_RUN_DIR}..."
    rm -rf "${SERVICE_RUN_DIR}"
fi

# Create service directory
echo "Creating service directory..."
mkdir -p "${SERVICE_RUN_DIR}"

# Extract tarball
echo "Extracting tarball..."
cd "${SERVICE_RUN_DIR}"
tar -xzf "${TARBALL_PATH}"

# Find the extracted directory (should be june-<service-name>)
EXTRACTED_DIR=$(find . -maxdepth 1 -type d -name "june-${SERVICE_NAME}" | head -1)
if [ -z "${EXTRACTED_DIR}" ]; then
    echo "Error: Could not find extracted directory june-${SERVICE_NAME}"
    exit 1
fi

# Move contents to service directory root
echo "Organizing files..."
mv "${EXTRACTED_DIR}"/* .
rmdir "${EXTRACTED_DIR}"

# Verify tarball contents are viable
echo "Verifying deployment structure..."
REQUIRED_FILES=(
    "run.sh"
    "venv/bin/python3"
    "essence/__main__.py"
    "essence/command/__init__.py"
    "essence/commands"
)
MISSING_FILES=()
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -e "${SERVICE_RUN_DIR}/${file}" ]; then
        MISSING_FILES+=("${file}")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo "ERROR: Deployment verification failed. Missing required files:"
    for file in "${MISSING_FILES[@]}"; do
        echo "  - ${file}"
    done
    exit 1
fi

# Verify essence module can be imported
echo "Verifying essence module..."
cd "${SERVICE_RUN_DIR}"
if ! "${SERVICE_RUN_DIR}/venv/bin/python3" -c "import sys; sys.path.insert(0, '.'); import essence; print('✓ Essence module importable')" 2>/dev/null; then
    echo "ERROR: Essence module cannot be imported. Deployment may be corrupted."
    exit 1
fi

# Verify commands can be discovered
echo "Verifying command discovery..."
if ! "${SERVICE_RUN_DIR}/venv/bin/python3" -c "import sys; sys.path.insert(0, '.'); from essence.__main__ import get_commands; cmds = get_commands(); print(f'✓ Discovered {len(cmds)} command(s): {list(cmds.keys())}')" 2>/dev/null; then
    echo "WARNING: Command discovery failed. Service may not start correctly."
fi

# Set permissions
echo "Setting permissions..."
chmod +x run.sh
# Only chown if running as root
if [ "$EUID" -eq 0 ]; then
    chown -R root:root "${SERVICE_RUN_DIR}" || true
fi
chmod -R 755 "${SERVICE_RUN_DIR}"

# Set ENV_SH to point to the repo's .env file (if it exists)
# This allows services to source environment variables from the repo without including them in the build
REPO_ENV_FILE="${PROJECT_ROOT}/.env"

if [ -f "${REPO_ENV_FILE}" ]; then
    echo "Found repo .env file at: ${REPO_ENV_FILE}"
    export ENV_SH="${REPO_ENV_FILE}"
else
    echo "Warning: Repo .env file not found at ${REPO_ENV_FILE}"
    echo "Service will need environment variables set via other means (e.g., systemd, environment, etc.)"
fi

# Start the service
echo "Starting service..."
cd "${SERVICE_RUN_DIR}"

# Start service in background with logging
echo "Starting ${SERVICE_NAME} service..."
(
    cd "${SERVICE_RUN_DIR}"
    export SERVICE_NAME="${SERVICE_NAME}"
    # Export ENV_SH if we found the repo .env file
    # This will be picked up by run.sh to source environment variables
    if [ -n "${ENV_SH:-}" ] && [ -f "${ENV_SH}" ]; then
        export ENV_SH="${ENV_SH}"
        echo "Using environment file: ${ENV_SH}"
    fi
    nohup ./run.sh >> "${CONSOLE_LOG}" 2>&1 &
    echo $! > "${SERVICE_RUN_DIR}/service.pid"
)

# Wait a moment for service to start
sleep 2

# Check if service started successfully
PID=$(cat "${SERVICE_RUN_DIR}/service.pid" 2>/dev/null || echo "")
if [ -n "${PID}" ] && ps -p "${PID}" > /dev/null 2>&1; then
    echo "Service started successfully (PID: ${PID})"
    echo ""
    echo "Service logs:"
    echo "  Console output: ${CONSOLE_LOG}"
    echo "  Application log: ${APP_LOG}"
    echo ""
    echo "To view logs:"
    echo "  tail -f ${CONSOLE_LOG}"
    echo "  tail -f ${APP_LOG}"
    echo ""
    echo "To stop the service:"
    echo "  kill \$(cat ${SERVICE_RUN_DIR}/service.pid)"
else
    echo "Warning: Service may not have started correctly"
    echo "Check logs: ${CONSOLE_LOG}"
    exit 1
fi

