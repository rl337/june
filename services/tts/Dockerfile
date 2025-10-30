FROM june-base:latest

# Set working directory
WORKDIR /app
ENV PYTHONPATH="/app:/app/shared"

# Install TTS-specific system deps
USER root
RUN apt-get update && apt-get install -y \
    espeak \
    espeak-data \
    libespeak1 \
    libespeak-dev \
    && rm -rf /var/lib/apt/lists/*

# Install service-specific Python deps
RUN pip install soundfile numpy

# Copy shared modules
COPY shared ./shared

# Copy service code
COPY services/tts .

# Ensure permissions and switch back
RUN chown -R june:june /app
USER june

# Expose gRPC port
EXPOSE 50053

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; grpc.insecure_channel('localhost:50053').check_connectivity_state(True)" || exit 1

# Run the application
CMD ["python", "main.py"]


