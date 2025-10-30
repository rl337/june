FROM python:3.11-slim

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies directly
RUN pip install --no-cache-dir fastapi uvicorn httpx pydantic grpcio nats-py prometheus-client python-jose python-multipart

# Copy shared modules
COPY shared ./shared
# Ensure shared package is importable even if PYTHONPATH is ignored
RUN mkdir -p /usr/local/lib/python3.11/site-packages/shared && \
    cp -r ./shared/* /usr/local/lib/python3.11/site-packages/shared/

# Install june-grpc-api from prebuilt wheel
COPY packages/june-grpc-api/dist/*.whl /tmp/
RUN pip install /tmp/june_grpc_api-*.whl

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





