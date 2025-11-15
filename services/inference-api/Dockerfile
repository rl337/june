FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (needed for poetry install)
COPY essence ./essence

# Install dependencies using poetry (skip installing project itself with --no-root)
# Use environment variables to disable virtualenv creation
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
RUN poetry install --no-interaction --no-ansi --only main --no-root

## shared module removed; use inference_core instead

# Copy service code
COPY services/inference-api .

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD poetry run python -c "import grpc; grpc.insecure_channel('localhost:50051').check_connectivity_state(True)" || exit 1

# Run the passthrough LLM application by default
CMD ["poetry", "run", "python", "main_passthrough.py"]


