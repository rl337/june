FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Copy poetry configuration files
USER root
COPY pyproject.toml poetry.lock ./

# Copy essence package (needed for poetry install and command execution)
COPY essence ./essence

# Install dependencies using poetry (skip installing project itself with --no-root)
# Use environment variables to disable virtualenv creation
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
RUN poetry install --no-interaction --no-ansi --only main --no-root

# Install june-grpc-api and inference-core packages in editable mode from source
COPY packages/june-grpc-api /tmp/june-grpc-api
COPY packages/inference-core /tmp/inference-core
RUN pip install -e /tmp/june-grpc-api && \
    pip install -e /tmp/inference-core

# Ensure permissions
RUN chown -R june:june /app

# Create log directory with proper permissions
RUN mkdir -p /var/log/june/looping-agent && chown -R june:june /var/log/june

USER june

# Copy log wrapper script
COPY --chmod=755 scripts/log-wrapper.sh /usr/local/bin/log-wrapper.sh

# Copy logrotate configuration
COPY config/logrotate-june-services.conf /etc/logrotate.d/june-services

# Configure logrotate to run every 5 minutes via cron
USER root
RUN echo "*/5 * * * * /usr/sbin/logrotate -f /etc/logrotate.d/june-services >> /var/log/june/looping-agent/logrotate.log 2>&1" | crontab -

# Create entrypoint wrapper to start cron before service
RUN echo '#!/bin/bash' > /entrypoint-wrapper.sh && \
    echo 'cron' >> /entrypoint-wrapper.sh && \
    echo 'exec "$@"' >> /entrypoint-wrapper.sh && \
    chmod +x /entrypoint-wrapper.sh

USER june

# Run the looping agent service via essence command system, wrapped to capture logs
ENTRYPOINT ["/entrypoint-wrapper.sh"]
CMD ["/usr/local/bin/log-wrapper.sh", "looping-agent", "poetry", "run", "python", "-m", "essence", "looping-agent-service"]

