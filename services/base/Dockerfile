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
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3.10 /usr/bin/python && \
    python -m pip install --upgrade pip

# Install poetry for Python dependency management
RUN pip install poetry && \
    poetry --version

# Install runtime libs common to services
RUN pip install grpcio nats-py prometheus-client pydantic uvicorn fastapi scipy

# Install cron and logrotate for log rotation
RUN apt-get update && apt-get install -y cron logrotate && rm -rf /var/lib/apt/lists/*

# Note: Packages (june-grpc-api, inference-core) are now installed in editable mode
# by individual service Dockerfiles that need them, not in the base image.
# This allows faster iteration during development without rebuilding wheels.

# Provide default non-root user
RUN useradd -m -u 1000 june
USER june



