FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install service-specific Python deps
USER root
RUN pip install fastapi uvicorn

# Copy service code
COPY services/todo-service .

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose HTTP port
EXPOSE 8004

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health', timeout=5)" || exit 1

# Run the TODO service
# Defaults - can be overridden via environment variables
ENV TODO_DB_PATH=/app/data/todos.db
ENV TODO_SERVICE_PORT=8004

# Create data directory
RUN mkdir -p /app/data && chown june:june /app/data

CMD ["python", "main.py"]

