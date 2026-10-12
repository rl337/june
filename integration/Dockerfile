# June integration-test image: recipe E2E suite (offline + optional live JuneSpark).
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JUNE_INTEGRATION=1 \
    JUNE_INTEGRATION_ARTIFACTS=/artifacts \
    HOME=/tmp/june-integration \
    PYTEST_ADDOPTS="-p no:cacheprovider"

RUN useradd --create-home --uid 10001 june

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY tests /app/tests

RUN pip install --no-cache-dir '.[dev,harness]' && \
    mkdir -p /tmp/june-integration /artifacts && \
    chown june:june /tmp/june-integration /artifacts

USER june

# Default: offline integration tests (always). Live JuneSpark tests run when
# JUNESPARK_BASE_URL is set (compose/network must reach the inference host).
CMD ["pytest", "-q", "tests/integration", "-m", "integration"]
