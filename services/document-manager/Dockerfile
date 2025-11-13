FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install service-specific Python deps
USER root
RUN pip install fastapi uvicorn

# Copy service code
COPY services/document-manager .

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose HTTP port
EXPOSE 8007

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8007/health', timeout=5)" || exit 1

# Run the Document Manager service
ENV DOC_DB_PATH=/app/data/documents.db
ENV DOC_SERVICE_PORT=8007

# Create data directory
RUN mkdir -p /app/data && chown june:june /app/data

CMD ["python", "main.py"]
