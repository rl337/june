FROM ubuntu:22.04

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    git \
    curl \
    build-essential \
    libffi-dev \
    libssl-dev \
    libsndfile1 \
    ffmpeg \
    espeak \
    espeak-data \
    libespeak1 \
    libespeak-dev \
    && rm -rf /var/lib/apt/lists/*

# Create symbolic link for python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Upgrade pip
RUN python -m pip install --upgrade pip

# Copy requirements and install Python dependencies
COPY pyproject.toml ./
RUN pip install fastapi uvicorn grpcio grpcio-tools nats-py sqlalchemy psycopg2-binary minio prometheus-client soundfile numpy

# Copy protobuf files
# Copy protobuf files (not used directly once june-grpc-api is installed, kept for reference)
COPY proto ./proto

# Copy shared modules
COPY shared ./shared

# Copy service code
COPY services/tts .

# Build and install shared gRPC API package
COPY packages/june-grpc-api /tmp/june-grpc-api
RUN pip install build grpcio-tools && \
    python -m grpc_tools.protoc -I/tmp/june-grpc-api/proto \
    --python_out=/tmp/june-grpc-api/june_grpc_api \
    --grpc_python_out=/tmp/june-grpc-api/june_grpc_api \
    /tmp/june-grpc-api/proto/asr.proto /tmp/june-grpc-api/proto/tts.proto /tmp/june-grpc-api/proto/llm.proto && \
    sed -i "s/^import asr_pb2/from . import asr_pb2/" /tmp/june-grpc-api/june_grpc_api/asr_pb2_grpc.py && \
    sed -i "s/^import tts_pb2/from . import tts_pb2/" /tmp/june-grpc-api/june_grpc_api/tts_pb2_grpc.py && \
    sed -i "s/^import llm_pb2/from . import llm_pb2/" /tmp/june-grpc-api/june_grpc_api/llm_pb2_grpc.py && \
    cd /tmp/june-grpc-api && python -m build && pip install dist/*.whl

# Create non-root user
RUN useradd -m -u 1000 june && chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50053

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50053').check_connectivity_state(True)" || exit 1

# Run the application
CMD ["python", "main.py"]


