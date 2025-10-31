FROM python:3.11-slim

WORKDIR /pkg

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Copy package (and any .whl files for dependencies)
COPY . /pkg

RUN pip install --no-cache-dir build pytest pytest-asyncio

RUN python -m build

# Install wheel and dependencies for testing
RUN pip install dist/inference_core-*.whl
RUN pip install soundfile numpy || echo "Optional audio dependencies not available"
# Install june-grpc-api if wheel is available (needed for server tests)
RUN if ls june_grpc_api-*.whl 1> /dev/null 2>&1; then pip install june_grpc_api-*.whl; else echo "june-grpc-api wheel not found, server tests will be skipped"; fi

RUN pytest -v tests/ || (cat /root/.cache/pytest/* || true; exit 1)


