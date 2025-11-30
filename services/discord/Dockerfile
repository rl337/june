FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared:/app/chat-service-base"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (needed for poetry install and command execution)
# This includes all service code now (essence/services/discord)
COPY essence ./essence

# Copy VERSION file and set version label
ARG SERVICE_VERSION=1.0.0
COPY essence/services/discord/VERSION /app/VERSION
LABEL org.opencontainers.image.version="${SERVICE_VERSION}"
LABEL june.service.version="${SERVICE_VERSION}"

# Install dependencies using poetry (skip installing project itself with --no-root)
# Use environment variables to disable virtualenv creation
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
RUN poetry install --no-interaction --no-ansi --only main --no-root

# Install inference-core package in editable mode from source
# This allows faster iteration during development without rebuilding wheels
COPY packages/inference-core /tmp/inference-core
RUN pip install -e /tmp/inference-core

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose health check port
EXPOSE 8081

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8081/health || exit 1

# Copy log wrapper script
COPY scripts/log-wrapper.sh /usr/local/bin/log-wrapper.sh
RUN chmod +x /usr/local/bin/log-wrapper.sh

# Run the Discord bot via essence command system, wrapped to capture logs
# Logs go to both stdout/stderr (Docker) and /logs/discord.log (Promtail)
CMD ["/usr/local/bin/log-wrapper.sh", "discord", "poetry", "run", "python", "-m", "essence", "discord-service"]

