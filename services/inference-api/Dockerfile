FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

## shared module removed; use inference_core instead

# Copy service code
COPY services/inference-api .

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50051').check_connectivity_state(True)" || exit 1

# Run the passthrough LLM application by default
CMD ["python", "main_passthrough.py"]


