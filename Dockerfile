FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    JUNE_DATA_DIR=/data \
    JUNE_CONSOLE_DEMO=1

RUN useradd --create-home --uid 10001 june
COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir '.[container]' && \
    mkdir -p /data && chown june:june /data

USER june
VOLUME ["/data"]
EXPOSE 8080

CMD ["june", "serve", "--host", "0.0.0.0", "--port", "8080"]
