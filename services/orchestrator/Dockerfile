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
# Use environment variables to disable virtualenv creation
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
RUN poetry install --no-interaction --no-ansi --only main --no-root

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose port
EXPOSE 8005

# Run the service
CMD ["poetry", "run", "python", "main.py"]
