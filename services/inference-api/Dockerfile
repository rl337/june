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

# Reinstall inference-core and june-grpc-api wheels to ensure latest versions
COPY packages/inference-core/dist/*.whl /tmp/
COPY packages/june-grpc-api/dist/*.whl /tmp/
RUN pip install --force-reinstall --no-deps /tmp/inference_core-*.whl /tmp/june_grpc_api-*.whl

# Install PyTorch with CUDA support (replace CPU-only version installed by poetry)
# Install AFTER copying service code to ensure it's not overwritten
# Try CUDA 12.4 index first (has newer PyTorch versions), fallback to 12.1
# Note: Container needs NVIDIA Container Toolkit for GPU access
RUN pip uninstall -y torch torchvision torchaudio 2>/dev/null || true && \
    (pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 || \
     pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121) && \
    python -c "import torch; print(f'PyTorch {torch.__version__} installed'); print(f'CUDA compiled: {torch.version.cuda if torch.version.cuda else \"None (CPU build)\"}')"

## shared module removed; use inference_core instead

# Copy grpc_auth.py from june-grpc-api package (needed for authentication)
COPY packages/june-grpc-api/grpc_auth.py /app/grpc_auth.py

# Copy service code
COPY services/inference-api .

# Reinstall PyTorch with CUDA support AFTER copying service code
# (ensures PyTorch CUDA is not overwritten by any service code dependencies)
RUN pip uninstall -y torch torchvision torchaudio 2>/dev/null || true && \
    (pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 || \
     pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121) && \
    python -c "import torch; print(f'Final PyTorch {torch.__version__}'); print(f'CUDA compiled: {torch.version.cuda if torch.version.cuda else \"None\"}')"

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD poetry run python -c "import grpc; grpc.insecure_channel('localhost:50051').check_connectivity_state(True)" || exit 1

# Run the inference API service
CMD ["poetry", "run", "python", "main.py"]


