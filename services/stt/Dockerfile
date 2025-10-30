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
    && rm -rf /var/lib/apt/lists/*

# Create symbolic link for python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Upgrade pip
RUN python -m pip install --upgrade pip

# Copy requirements and install Python dependencies
COPY pyproject.toml ./
RUN pip install fastapi uvicorn grpcio nats-py sqlalchemy psycopg2-binary minio prometheus-client numpy openai-whisper soundfile

# Install june-grpc-api from prebuilt wheel
COPY packages/june-grpc-api/dist/*.whl /tmp/
RUN pip install /tmp/june_grpc_api-*.whl

# Copy shared modules
COPY shared ./shared

# Copy service code
COPY services/stt .

# Create non-root user
RUN useradd -m -u 1000 june && chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50052

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50052').check_connectivity_state(True)" || exit 1

# Run the Whisper-based STT application
ENV STT_MODEL_NAME=tiny.en
ENV STT_DEVICE=cpu
CMD ["python", "main_whisper.py"]


