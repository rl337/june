FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared:/app/chat-service-base"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (needed for poetry install and command execution)
COPY essence ./essence

# Copy shared base code
COPY services/chat-service-base /app/chat-service-base

# Copy service code
COPY services/discord .

# Install dependencies using poetry
# First install dependencies only, then install the project itself
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose health check port
EXPOSE 8081

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8081/health || exit 1

# Run the Discord bot via essence command system
CMD ["poetry", "run", "python", "-m", "essence", "discord-service"]

