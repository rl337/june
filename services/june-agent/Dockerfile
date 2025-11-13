FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy packages (if building from monorepo)
COPY ../../packages/june-mcp-client /app/packages/june-mcp-client
COPY ../../packages/inference-core /app/packages/inference-core

# Install packages
RUN pip install --no-cache-dir -e packages/june-mcp-client
RUN pip install --no-cache-dir -e packages/inference-core

# Copy service code
COPY main.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Run service
CMD ["python3", "main.py"]
