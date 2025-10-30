FROM python:3.11-slim

WORKDIR /pkg

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Copy package
COPY . /pkg

RUN pip install --no-cache-dir build pytest
RUN python -m build

# Install wheel for testing and run tests
RUN pip install dist/inference_core-*.whl
RUN pytest -q || (cat /root/.cache/pytest/* || true; exit 1)


