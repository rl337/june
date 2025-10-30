# CLI Tools Container for June Agent
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    build-essential \
    ffmpeg \
    libsndfile1 \
    rustc \
    cargo \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements for CLI tools
COPY requirements-cli.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-cli.txt

# Install june-grpc-api from prebuilt wheel
COPY ../../packages/june-grpc-api/dist/*.whl /tmp/
RUN pip install /tmp/june_grpc_api-*.whl

# Copy CLI scripts
COPY scripts/ /app/scripts/

# Set environment variables
ENV MODEL_CACHE_DIR=/models
ENV HUGGINGFACE_CACHE_DIR=/models/huggingface
ENV TRANSFORMERS_CACHE_DIR=/models/transformers
ENV PYTHONPATH=/app

# Create model cache directories
RUN mkdir -p /models/{huggingface,transformers,whisper,tts}

# Make scripts executable
RUN chmod +x /app/scripts/*.py

# Default command
CMD ["bash"]


