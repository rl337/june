FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (if needed)
COPY essence ./essence

# Copy service code
COPY services/knowledge-graph .

# Install dependencies using poetry
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose HTTP port
EXPOSE 8006

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8006/health', timeout=5)" || exit 1

# Run the Knowledge Graph service
ENV KG_DB_PATH=/app/data/kg.db
ENV KG_SERVICE_PORT=8006

# Create data directory
RUN mkdir -p /app/data && chown june:june /app/data

CMD ["poetry", "run", "python", "main.py"]
