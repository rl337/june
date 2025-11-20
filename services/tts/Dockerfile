FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"
# Ensure PYTHONPATH is used by poetry run
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_VIRTUALENVS_IN_PROJECT=false

# Install TTS-specific system deps
USER root
RUN apt-get update && apt-get install -y \
    espeak \
    espeak-data \
    libespeak1 \
    libespeak-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Rust compiler (required for sudachipy dependency in TTS package)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    . $HOME/.cargo/env && \
    rustc --version

# Copy poetry configuration files
COPY pyproject.toml poetry.lock ./

# Copy essence package (if needed)
COPY essence ./essence

# Install dependencies using poetry (skip installing project itself with --no-root)
# Then install TTS separately with compatible numpy
# Source Rust environment for TTS package build
RUN . $HOME/.cargo/env && \
    poetry install --no-interaction --no-ansi --only main --no-root && \
    pip install "numpy==1.22.0" "TTS>=0.20.0,<0.23.0"

# Install inference-core package in editable mode from source
# This allows faster iteration during development without rebuilding wheels
COPY packages/inference-core /tmp/inference-core
RUN pip install -e /tmp/inference-core[audio]

## shared module removed; use inference_core instead

# Copy service code (only specific files, not the entire directory)
# This ensures we don't overwrite essence/ or other files
COPY services/tts/main.py ./
COPY services/tts/model_artifacts ./model_artifacts

# Ensure pyproject.toml and essence are still present after copying service code
COPY pyproject.toml poetry.lock ./
COPY essence ./essence

# Ensure permissions and switch back
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50053

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50053').check_connectivity_state(True)" || exit 1

# Run the TTS service via essence command system
# Use python directly since dependencies are installed and PYTHONPATH is set
# PYTHONPATH="/app:/app/shared" ensures essence module can be imported
WORKDIR /app
CMD ["python", "-m", "essence", "tts"]


