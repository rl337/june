FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install service-specific Python deps
USER root
RUN pip install python-telegram-bot[webhooks] pydub

# Copy service code
COPY services/telegram .

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose health check port (if needed)
EXPOSE 8080

# Health check (will be implemented in Phase 7)
# For now, just check if the process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f "python.*main.py" || exit 1

# Run the Telegram bot
CMD ["python", "main.py"]

