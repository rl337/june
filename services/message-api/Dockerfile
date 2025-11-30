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

# Copy log wrapper script
COPY scripts/log-wrapper.sh /usr/local/bin/log-wrapper.sh
RUN chmod +x /usr/local/bin/log-wrapper.sh

# Run the message API service, wrapped to capture logs
CMD ["/usr/local/bin/log-wrapper.sh", "message-api", "poetry", "run", "python", "-m", "essence", "message-api-service"]
