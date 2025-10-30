FROM python:3.11-slim

WORKDIR /pkg

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY . /pkg

RUN pip install --no-cache-dir build grpcio-tools pytest

# Generate stubs into package, build wheel, and run a smoke test import
RUN mkdir -p june_grpc_api/generated && \
    python -m grpc_tools.protoc -I proto --python_out=june_grpc_api/generated --grpc_python_out=june_grpc_api/generated proto/asr.proto proto/tts.proto proto/llm.proto && \
    sed -i "s/^import asr_pb2 /from . import asr_pb2 /" june_grpc_api/generated/asr_pb2_grpc.py && \
    sed -i "s/^import tts_pb2 /from . import tts_pb2 /" june_grpc_api/generated/tts_pb2_grpc.py && \
    sed -i "s/^import llm_pb2 /from . import llm_pb2 /" june_grpc_api/generated/llm_pb2_grpc.py && \
    python -m build && \
    pip install dist/june_grpc_api-*.whl && \
    python - << 'PY'
from june_grpc_api import generated, asr, tts, llm
print('import_ok')
PY


