#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/3] Building june-grpc-api package image and running smoke tests..."
sg docker -c "docker build -t pkg-june-grpc-api:latest packages/june-grpc-api"

echo "[2/3] Building inference-core package image and running unit tests..."
# Copy june-grpc-api wheel to inference-core for server tests
cp packages/june-grpc-api/dist/*.whl packages/inference-core/ 2>/dev/null || echo "Note: june-grpc-api wheel not found, server tests may be skipped"
sg docker -c "docker build -t pkg-inference-core:latest packages/inference-core"
rm -f packages/inference-core/*.whl 2>/dev/null || true

echo "[3/3] Building wheels via scripts and verifying installation in cli-tools..."
bash scripts/build_june_grpc_api_wheel.sh >/dev/null
bash scripts/build_inference_core_wheel.sh >/dev/null
sg docker -c "docker compose build cli-tools"
sg docker -c "docker run --rm pkg-inference-core:latest python -c 'import inference_core; print(\"inference_core_ok\")'"
sg docker -c "docker run --rm pkg-june-grpc-api:latest python -c 'import june_grpc_api; print(\"june_grpc_api_ok\")'"

echo "All checks completed successfully."


