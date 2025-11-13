FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install service-specific Python deps from requirements.txt
USER root
COPY services/telegram/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy service code
COPY services/telegram .

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose health check port
EXPOSE 8080

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the Telegram bot
CMD ["python", "main.py"]

