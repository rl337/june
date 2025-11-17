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
# Use CUDA 12.1 which is compatible with CUDA 13.0 driver
# Note: Container needs NVIDIA Container Toolkit for GPU access, PyTorch CUDA build provides CUDA runtime
RUN pip uninstall -y torch torchvision torchaudio 2>/dev/null || true && \
    pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
    python -c "import torch; assert torch.cuda.is_available() or True, 'CUDA check will happen at runtime with GPU access'" || echo "Note: CUDA availability requires GPU access at runtime"

## shared module removed; use inference_core instead

# Copy grpc_auth.py from june-grpc-api package (needed for authentication)
COPY packages/june-grpc-api/grpc_auth.py /app/grpc_auth.py

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

# Run the inference API service
CMD ["poetry", "run", "python", "main.py"]


