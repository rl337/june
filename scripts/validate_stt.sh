#!/usr/bin/env bash
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

docker_compose_cmd() {
  if command -v docker-compose &> /dev/null; then
    sg docker -c "cd /home/rlee/dev/june && docker-compose $*"
  else
    sg docker -c "cd /home/rlee/dev/june && docker compose $*"
  fi
}

echo -e "${BLUE}Starting STT service validation...${NC}"
cd /home/rlee/dev/june

# Bring up stt and cli-tools
sg docker -c "docker compose up -d stt cli-tools"

# Wait briefly for STT to start
sleep 5

# Run validation script inside CLI tools
sg docker -c "docker exec june-cli-tools python /app/scripts/test_stt_validate.py"


