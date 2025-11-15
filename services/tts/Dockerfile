FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install TTS-specific system deps
USER root
RUN apt-get update && apt-get install -y \
    espeak \
    espeak-data \
    libespeak1 \
    libespeak-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy poetry configuration files
COPY pyproject.toml poetry.lock ./

# Copy essence package (if needed)
COPY essence ./essence

# Install dependencies using poetry (skip installing project itself with --no-root)
# Set config globally and ensure it persists
# Then install TTS separately with compatible numpy
RUN poetry config virtualenvs.create false --global && \
    poetry config virtualenvs.in-project false --global && \
    poetry install --no-interaction --no-ansi --only main --no-root && \
    pip install "numpy==1.22.0" "TTS>=0.20.0,<0.23.0"

## shared module removed; use inference_core instead

# Copy service code
COPY services/tts .

# Ensure permissions and switch back
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50053

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50053').check_connectivity_state(True)" || exit 1

# Run the application
CMD ["poetry", "run", "python", "main.py"]


