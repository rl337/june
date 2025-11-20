FROM june-base:latest

WORKDIR /app

# Copy essence package
COPY essence/ /app/essence/

# Copy pyproject.toml for dependencies
COPY pyproject.toml poetry.lock /app/

# Install dependencies
RUN poetry install --no-interaction --no-root

# Set Python path
ENV PYTHONPATH=/app

# Run the message API service
CMD ["poetry", "run", "python", "-m", "essence", "message-api-service"]
