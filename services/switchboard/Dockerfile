# Switchboard Service Dockerfile
# Agent-as-a-Service API for June project

FROM python:3.11-slim

# Create non-root user (UID 1000)
RUN groupadd -r june && useradd -r -g june -u 1000 june

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock* ./

# Install Poetry if not already installed
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

# Install dependencies using poetry (skip installing project itself with --no-root)
# Use environment variables to disable virtualenv creation
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
RUN poetry install --no-interaction --no-ansi --only main --no-root

# Copy agenticness package - it's mounted as a volume in docker-compose
# The volume mount will make it available at /home/rlee/dev/agenticness
# We need to ensure PYTHONPATH includes it or install it as a package
# For now, we'll add it to PYTHONPATH via environment variable in docker-compose
# Also copy any local files if they exist
COPY --chown=june:june . /app

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose service port
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

# Copy log wrapper script
COPY scripts/log-wrapper.sh /usr/local/bin/log-wrapper.sh
RUN chmod +x /usr/local/bin/log-wrapper.sh

# Run the switchboard service, wrapped to capture logs
# Logs go to both stdout/stderr (Docker) and /logs/switchboard.log (Promtail)
CMD ["/usr/local/bin/log-wrapper.sh", "switchboard", "poetry", "run", "python", "-m", "agenticness", "switchboard", "--host", "0.0.0.0", "--port", "8082"]

