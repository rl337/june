FROM ubuntu:22.04

# Base image for June services with shared dependencies and tools installed.

WORKDIR /app

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

RUN ln -s /usr/bin/python3.10 /usr/bin/python && \
    python -m pip install --upgrade pip

# Install runtime libs common to services
RUN pip install grpcio nats-py prometheus-client pydantic uvicorn fastapi

# Install shared wheels: june-grpc-api and inference-core
COPY ../../packages/june-grpc-api/dist/*.whl /tmp/
COPY ../../packages/inference-core/dist/*.whl /tmp/
RUN pip install /tmp/june_grpc_api-*.whl /tmp/inference_core-*.whl

# Provide default non-root user
RUN useradd -m -u 1000 june
USER june


