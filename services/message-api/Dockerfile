FROM june-base:latest

WORKDIR /app

# Copy essence package
COPY essence/ /app/essence/

# Copy VERSION file and set version label
ARG SERVICE_VERSION=1.0.0
COPY essence/services/message_api/VERSION /app/VERSION
LABEL org.opencontainers.image.version="${SERVICE_VERSION}"
LABEL june.service.version="${SERVICE_VERSION}"

# Copy pyproject.toml for dependencies
COPY pyproject.toml poetry.lock /app/

# Install dependencies
RUN poetry install --no-interaction --no-root

# Set Python path
ENV PYTHONPATH=/app

# Run the message API service
CMD ["poetry", "run", "python", "-m", "essence", "message-api-service"]
