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

# Install june-grpc-api from prebuilt wheel
COPY packages/june-grpc-api/dist/*.whl /tmp/
COPY packages/inference-core/dist/*.whl /tmp/
RUN pip install /tmp/june_grpc_api-*.whl /tmp/inference_core-*.whl

# Copy service code
COPY services/gateway .

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose ports
EXPOSE 8000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["poetry", "run", "python", "main.py"]





