FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared:/app/chat-service-base"

# Install service-specific Python deps from requirements.txt
USER root
COPY services/discord/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy shared base code
COPY services/chat-service-base /app/chat-service-base

# Copy service code
COPY services/discord .

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose health check port
EXPOSE 8081

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8081/health || exit 1

# Run the Discord bot via essence module
CMD ["poetry", "run", "python", "-m", "essence", "discord-service"]

