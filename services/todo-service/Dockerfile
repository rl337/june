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
    CMD python -c "import requests; requests.get('http://localhost:8004/health', timeout=5)" || exit 1

# Run the TODO service
ENV TODO_DB_PATH=/home/rlee/june_data/todo_service/todos.db
ENV TODO_SERVICE_PORT=8004
CMD ["python", "main.py"]

