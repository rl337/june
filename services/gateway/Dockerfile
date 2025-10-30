FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies directly
RUN pip install --no-cache-dir fastapi uvicorn httpx pydantic grpcio build grpcio-tools

# Copy shared modules
COPY shared ./shared

# Build and install june-grpc-api from local source
COPY packages/june-grpc-api /tmp/june-grpc-api
RUN python -m grpc_tools.protoc -I/tmp/june-grpc-api/proto \
    --python_out=/tmp/june-grpc-api/june_grpc_api \
    --grpc_python_out=/tmp/june-grpc-api/june_grpc_api \
    /tmp/june-grpc-api/proto/asr.proto /tmp/june-grpc-api/proto/tts.proto /tmp/june-grpc-api/proto/llm.proto && \
    cd /tmp/june-grpc-api && python -m build && pip install dist/*.whl

# Copy service code
COPY services/gateway/ .

# Create non-root user
RUN useradd -m -u 1000 june && chown -R june:june /app
USER june

# Expose ports
EXPOSE 8000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "main.py"]





