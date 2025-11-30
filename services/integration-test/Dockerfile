FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (needed for poetry install and command execution)
# This includes all service code now (essence/services/integration_test)
COPY essence ./essence

# Install dependencies using poetry (skip installing project itself with --no-root)
# Use environment variables to disable virtualenv creation
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
RUN poetry install --no-interaction --no-ansi --only main --no-root

# Install june-grpc-api and inference-core packages in editable mode from source
# This allows faster iteration during development without rebuilding wheels
COPY packages/june-grpc-api /tmp/june-grpc-api
COPY packages/inference-core /tmp/inference-core
RUN pip install -e /tmp/june-grpc-api && \
    pip install -e /tmp/inference-core

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose health check port
EXPOSE 8082

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

# Copy log wrapper script
COPY scripts/log-wrapper.sh /usr/local/bin/log-wrapper.sh
RUN chmod +x /usr/local/bin/log-wrapper.sh

# Run the integration test service via essence command system, wrapped to capture logs
CMD ["/usr/local/bin/log-wrapper.sh", "integration-test", "poetry", "run", "python", "-m", "essence", "integration-test-service"]
