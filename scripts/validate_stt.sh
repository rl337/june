#!/bin/bash
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

# Build and start STT only + CLI tools
docker_compose_cmd --profile tools up -d cli-tools >/dev/null
docker_compose_cmd up -d stt >/dev/null

echo -e "${BLUE}Waiting for STT to be ready...${NC}"
sleep 8

echo -e "${BLUE}Download small LibriSpeech subset...${NC}"
sg docker -c "docker exec -e JUNE_DATA_DIR=/data june-cli-tools python /app/scripts/download_librispeech_small.py"

echo -e "${BLUE}Generate gRPC Python stubs for ASR proto...${NC}"
sg docker -c "docker exec june-cli-tools python -m grpc_tools.protoc -I/app/proto --python_out=/app/proto --grpc_python_out=/app/proto /app/proto/asr.proto"

echo -e "${BLUE}Run STT validation (via host.docker.internal:50052)...${NC}"
sg docker -c "docker exec -e JUNE_DATA_DIR=/data -e STT_SERVICE_ADDRESS=host.docker.internal:50052 june-cli-tools python /app/scripts/test_stt_validate.py" || true

echo -e "${GREEN}STT validation complete${NC}"


