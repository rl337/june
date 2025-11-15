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

# Install dependencies using poetry
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main

# Ensure permissions
RUN chown -R june:june /app
USER june

# Expose port
EXPOSE 8005

# Run the service
CMD ["poetry", "run", "python", "main.py"]
