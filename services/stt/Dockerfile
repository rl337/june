FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (if needed)
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
    pip install -e /tmp/inference-core[audio]

## shared module removed; use inference_core instead

# Copy service code
COPY services/stt .

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50052

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50052').check_connectivity_state(True)" || exit 1

# Run the STT service via essence command system
ENV STT_MODEL_NAME=base.en
ENV STT_DEVICE=cpu
CMD ["poetry", "run", "python", "-m", "essence", "stt"]


