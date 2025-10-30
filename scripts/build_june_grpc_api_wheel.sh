#!/usr/bin/env bash
set -euo pipefail

PKG_DIR="$(cd "$(dirname "$0")/.." && pwd)/packages/june-grpc-api"
cd "$PKG_DIR"

PY=python3

# Use isolated venv for build deps
VENV_DIR=".venv-build"
rm -rf "$VENV_DIR"
$PY -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install --upgrade build grpcio-tools >/dev/null

# Generate stubs into package dir under generated/
mkdir -p june_grpc_api/generated
python -m grpc_tools.protoc -I proto \
  --python_out=june_grpc_api/generated \
  --grpc_python_out=june_grpc_api/generated \
  proto/asr.proto proto/tts.proto proto/llm.proto

# Fix relative imports in generated *_pb2_grpc.py
sed -i "s/^import asr_pb2 /from . import asr_pb2 /" june_grpc_api/generated/asr_pb2_grpc.py || true
sed -i "s/^import tts_pb2 /from . import tts_pb2 /" june_grpc_api/generated/tts_pb2_grpc.py || true
sed -i "s/^import llm_pb2 /from . import llm_pb2 /" june_grpc_api/generated/llm_pb2_grpc.py || true

python -m build
echo "Built wheel(s):"
ls -1 dist/*.whl

deactivate
rm -rf "$VENV_DIR"


