#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

docker_compose_cmd() {
  if command -v docker-compose &> /dev/null; then
    sg docker -c "cd /home/rlee/dev/june && docker-compose $*"
  else
    sg docker -c "cd /home/rlee/dev/june && docker compose $*"
  fi
}

echo -e "${BLUE}Starting gateway-only validation...${NC}"

cd /home/rlee/dev/june

# Bring up gateway and mock-sink only
docker_compose_cmd down --remove-orphans >/dev/null 2>&1 || true
docker_compose_cmd --profile tools up -d mock-sink >/dev/null
docker_compose_cmd up -d gateway >/dev/null

echo -e "${BLUE}Waiting for gateway health...${NC}"
for i in {1..30}; do
  if curl -s -f http://localhost:8000/health >/dev/null 2>&1; then
    echo -e "${GREEN}Gateway is healthy${NC}"
    break
  fi
  sleep 1
done

echo -e "${BLUE}Running gateway health test from CLI tools...${NC}"
# Ensure CLI tools up
docker_compose_cmd --profile tools up -d cli-tools >/dev/null

sg docker -c "docker exec -e GATEWAY_URL=http://gateway:8000 june-cli-tools pytest -q /app/gateway_tests/test_gateway_health.py -q" || true

echo -e "${BLUE}Gateway logs (last 50 lines):${NC}"
sg docker -c "docker logs --tail 50 june-gateway" || true

echo -e "${BLUE}Mock sink logs (last 50 lines):${NC}"
sg docker -c "docker logs --tail 50 june-mock-sink" || true

echo -e "${GREEN}Gateway validation run complete${NC}"


