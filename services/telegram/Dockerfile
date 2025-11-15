FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (needed for poetry install and command execution)
COPY essence ./essence

# Copy service code
COPY services/telegram .

# Install dependencies using poetry
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root && \
    poetry install --no-interaction --no-ansi

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose health check port
EXPOSE 8080

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the Telegram bot via essence command system
CMD ["poetry", "run", "python", "-m", "essence", "telegram-service"]

