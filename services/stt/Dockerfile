FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install service-specific Python deps
USER root
RUN pip install numpy openai-whisper soundfile

# Copy shared modules
COPY shared ./shared

# Copy service code
COPY services/stt .

# Ensure permissions
USER root
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50052

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50052').check_connectivity_state(True)" || exit 1

# Run the Whisper-based STT application
ENV STT_MODEL_NAME=tiny.en
ENV STT_DEVICE=cpu
CMD ["python", "main_whisper.py"]


