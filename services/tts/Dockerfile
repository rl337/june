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
# Source Rust environment for TTS package build
RUN . $HOME/.cargo/env && \
    poetry install --no-interaction --no-ansi --only main --no-root

# Install inference-core package in editable mode from source
# This allows faster iteration during development without rebuilding wheels
# Note: inference-core may install numpy 2.x, but TTS requires numpy 1.22.0
COPY packages/inference-core /tmp/inference-core
RUN pip install -e /tmp/inference-core[audio]

# Install TTS with compatible numpy version AFTER inference-core
# TTS requires numpy==1.22.0, so we need to downgrade numpy after inference-core installs it
# Also ensure scipy is compatible with numpy 1.22.0 (scipy<1.10.0 or scipy>=1.11.0 with numpy>=1.21.6)
RUN pip install --force-reinstall "numpy==1.22.0" "scipy>=1.11.0,<1.12.0" "TTS>=0.20.0,<0.23.0"

## shared module removed; use inference_core instead

# Copy service code to a subdirectory to avoid any conflicts
RUN mkdir -p /app/services/tts
COPY services/tts/main.py /app/services/tts/main.py
COPY services/tts/model_artifacts /app/services/tts/model_artifacts

# Re-copy pyproject.toml and essence to ensure they're definitely present
# (they should be from earlier, but this ensures they're there after all COPY operations)
COPY pyproject.toml poetry.lock /app/
COPY essence /app/essence

# Ensure permissions and switch back
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50053

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50053').check_connectivity_state(True)" || exit 1

# Run the TTS service via essence command system
# Use poetry run to ensure proper Python environment and path setup
WORKDIR /app
CMD ["poetry", "run", "python", "-m", "essence", "tts"]


