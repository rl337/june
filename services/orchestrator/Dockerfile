FROM june-base:latest

WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (if needed)
COPY essence ./essence

# Copy service code
COPY services/orchestrator .

# Install dependencies using poetry (skip installing project itself with --no-root)
# Set config globally and ensure it persists
RUN poetry config virtualenvs.create false --global && \
    poetry config virtualenvs.in-project false --global && \
    poetry install --no-interaction --no-ansi --only main --no-root

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose port
EXPOSE 8005

# Run the service
CMD ["poetry", "run", "python", "main.py"]
