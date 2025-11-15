FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Copy poetry configuration files
COPY pyproject.toml poetry.lock ./

# Copy essence package (if needed)
COPY essence ./essence

# Install dependencies using poetry (skip installing project itself with --no-root)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main --no-root

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

# Run the Whisper-based STT application
ENV STT_MODEL_NAME=base.en
ENV STT_DEVICE=cpu
CMD ["poetry", "run", "python", "main_whisper.py"]


