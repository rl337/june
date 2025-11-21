# NVIDIA NIM Setup Guide

This guide documents how to set up and use NVIDIA NIM (NVIDIA Inference Microservice) containers for LLM inference in the June project.

## Overview

**Status:** Phase 15 Task 4 - NIM Integration

NVIDIA NIM (NVIDIA Inference Microservice) provides pre-built, optimized containers for LLM inference. Unlike TensorRT-LLM, NIMs don't require model compilation - they come with optimized models pre-installed, making them faster to deploy and iterate with.

### Architecture

- **TensorRT-LLM:** Requires model compilation, optimized for specific hardware (default)
- **NVIDIA NIM:** Pre-built containers with optimized models, no compilation needed (alternative)
- **Legacy inference-api:** Deprecated, available via `--profile legacy` for backward compatibility

### When to Use NIM

- **Faster iteration:** No compilation step required, containers are ready to use
- **Pre-optimized models:** Models are already optimized by NVIDIA
- **Easier deployment:** Just pull and run the container
- **Trade-off:** Less control over optimization settings compared to TensorRT-LLM

## Prerequisites

- NVIDIA GPU with 20GB+ VRAM (for Qwen3-30B)
- NVIDIA Container Toolkit installed and configured
- Docker with GPU support enabled
- **NGC API Key** - Required for accessing NVIDIA NGC container registry
  - Get your API key from: https://catalog.ngc.nvidia.com/
  - Sign in to NGC, go to your profile → API Keys → Generate API Key

## Finding the Correct NIM Image Name

**IMPORTANT:** For DGX Spark (ARM64) systems, use DGX Spark-specific NIM containers that support ARM64 architecture.

### Current Configuration (DGX Spark)

The current configuration uses the DGX Spark-specific NIM container:
- **Image:** `nvcr.io/nim/qwen/qwen3-32b-dgx-spark:1.0.0`
- **Architecture:** ARM64-compatible (DGX Spark)
- **Model:** Qwen3-32B Instruct
- **Catalog:** https://catalog.ngc.nvidia.com/orgs/nim/teams/qwen/containers/qwen3-32b-dgx-spark

### Finding NIM Images

**Option 1: Use list-nims command (Recommended)**
```bash
poetry run python -m essence list-nims --dgx-spark-only --filter llm
```

**Option 2: Access NGC Catalog**

1. Go to https://catalog.ngc.nvidia.com/
2. Sign in with your NVIDIA account
3. Navigate to **Containers** → **NIM**
4. Search for "qwen3" or "dgx-spark"
5. Look for containers with "dgx-spark" in the name for ARM64 compatibility

### Image Name Format

NIM container images follow this format:
```
nvcr.io/nim/<team>/<model-name>:<tag>
```

**DGX Spark NIMs:**
- Qwen3-32B: `nvcr.io/nim/qwen/qwen3-32b-dgx-spark:1.0.0`
- Llama-3.1-8B: `nvcr.io/nim/llama/llama-3.1-8b-instruct-dgx-spark:latest`
- Nemotron-Nano-9B: `nvcr.io/nim/nemotron/nemotron-nano-9b-v2-dgx-spark:latest`

**Note:** Standard NIM containers (without "dgx-spark") are AMD64-only and won't work on ARM64 systems like DGX Spark.

## Infrastructure Setup

### NIM Container (in home_infra)

The NIM container is configured in `/home/rlee/dev/home_infra/docker-compose.yml`:

```yaml
nim-qwen3:
  image: nvcr.io/nim/qwen/qwen3-32b-dgx-spark:1.0.0  # DGX Spark ARM64-compatible
  container_name: common-nim-qwen3
  restart: unless-stopped
  expose:
    - "8001"  # gRPC endpoint (internal to shared-network)
    - "8003"  # HTTP endpoint (internal, for health checks)
  environment:
    - CUDA_VISIBLE_DEVICES=0
    - NGC_API_KEY=${NGC_API_KEY}  # Required for NGC container access
    - MAX_CONTEXT_LENGTH=${NIM_MAX_CONTEXT_LENGTH:-131072}
    - NIM_GPU_MEM_FRACTION=${NIM_GPU_MEMORY_UTILIZATION:-0.60}  # NIM-specific GPU memory fraction (defaults to 0.9). Set to 0.60 to fit in available GPU memory. This is the correct variable name for NIM containers (inference.py reads this).
    - ENABLE_TRACING=${ENABLE_TRACING:-true}
    - JAEGER_ENDPOINT=http://common-jaeger:14268/api/traces
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ['0']
            capabilities: [gpu]
  volumes:
    - ${MODEL_CACHE_DIR:-/home/rlee/models}:/models
    - /var/log/june/nim-qwen3:/logs
    - /var/data/june/nim-qwen3:/data
  networks:
    - shared-network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 120s  # Allow time for model loading
```

### Setting Up NGC API Key

1. **Get your NGC API key:**
   - Go to https://catalog.ngc.nvidia.com/
   - Sign in → Profile → API Keys → Generate API Key

2. **Set environment variable in home_infra:**
   ```bash
   # Option 1: Set in shell environment
   export NGC_API_KEY=your-api-key-here
   
   # Option 2: Add to home_infra/.env file
   echo "NGC_API_KEY=your-api-key-here" >> /home/rlee/dev/home_infra/.env
   ```

3. **Verify API key is set:**
   ```bash
   cd /home/rlee/dev/home_infra
   echo $NGC_API_KEY  # Should show your API key
   ```

### Starting the NIM Service

```bash
# Navigate to home_infra
cd /home/rlee/dev/home_infra

# Start NIM service
docker compose up -d nim-qwen3

# Check status
docker compose ps nim-qwen3

# View logs
docker compose logs -f nim-qwen3
```

### Verifying NIM Setup

Use the `verify-nim` command to check NIM setup:

```bash
# Basic verification
poetry run python -m essence verify-nim

# With custom host/ports
poetry run python -m essence verify-nim \
  --nim-host nim-qwen3 \
  --http-port 8003 \
  --grpc-port 8001

# Check gRPC protocol compatibility
poetry run python -m essence verify-nim --check-protocol

# JSON output
poetry run python -m essence verify-nim --json
```

**Expected output:**
- ✅ HTTP health check: Service responds on port 8003
- ✅ gRPC connectivity: Can connect to port 8001
- ✅ GPU availability: GPU is accessible
- ✅ Overall status: Ready

## Configuration

### Using NIM in June Services

June services can use NIM by setting the `LLM_URL` environment variable. The easiest way is to use the helper script:

**Option 1: Use helper script (Recommended)**
```bash
# Verify NIM is ready first
./scripts/switch_to_nim.sh --verify-only

# Switch to NIM (verifies, updates config, restarts services)
./scripts/switch_to_nim.sh

# Or update .env file instead of docker-compose.yml
./scripts/switch_to_nim.sh --use-env

# Or update config without restarting services
./scripts/switch_to_nim.sh --no-restart
```

**Option 2: Manual configuration**

Update `docker-compose.yml` to use NIM:

```yaml
services:
  telegram:
    environment:
      - LLM_URL=grpc://nim-qwen3:8001  # Use NIM instead of TensorRT-LLM
    # ... rest of configuration
```

Or set in `.env` file:
```bash
LLM_URL=grpc://nim-qwen3:8001
```

**Default configuration:**
- Telegram service: Uses TensorRT-LLM by default (`tensorrt-llm:8000`)
- Discord service: Uses TensorRT-LLM by default (`tensorrt-llm:8000`)
- To switch to NIM: Set `LLM_URL=grpc://nim-qwen3:8001`

**Important:** Always verify NIM is ready before switching:
```bash
poetry run python -m essence verify-nim --nim-host nim-qwen3 --http-port 8003 --grpc-port 8001
```

The helper script (`switch_to_nim.sh`) automatically verifies NIM is ready before making changes.

## Troubleshooting

### Container Not Starting

1. **Check NGC API key:**
   ```bash
   cd /home/rlee/dev/home_infra
   echo $NGC_API_KEY  # Should not be empty
   ```

2. **Check image name:**
   ```bash
   # Try to pull the image manually
   docker pull nvcr.io/nim/qwen/qwen3-32b-dgx-spark:1.0.0
   # If this fails, the image name may be incorrect - check NGC catalog or use list-nims command
   ```

3. **Check GPU availability:**
   ```bash
   nvidia-smi
   docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
   ```

4. **Check container logs:**
   ```bash
   cd /home/rlee/dev/home_infra
   docker compose logs nim-qwen3
   ```

### Authentication Errors

If you see authentication errors:
- Verify `NGC_API_KEY` is set correctly
- Check that the API key is valid (not expired)
- Ensure the API key has access to NIM containers
- Try logging in manually: `docker login nvcr.io` (use your NGC API key as password)

### Image Pull Errors

If image pull fails:
- Verify the image name is correct (check NGC catalog)
- Check if you have access to the container (some containers require approval)
- Try pulling with explicit authentication:
  ```bash
  echo $NGC_API_KEY | docker login nvcr.io -u '$oauthtoken' --password-stdin
  docker pull nvcr.io/nim/qwen/qwen3-32b-dgx-spark:1.0.0
  ```

### gRPC Connection Errors

If `verify-nim` shows gRPC connection errors:
- Check that NIM service is running: `docker compose ps nim-qwen3`
- Verify port 8001 is exposed on shared-network
- Check network connectivity: `docker network inspect shared_network`
- Check firewall rules (if applicable)

### Health Check Failures

If health checks fail:
- Check container logs: `docker compose logs nim-qwen3`
- Verify health endpoint: `curl http://nim-qwen3:8003/health` (from another container)
- Check if model is still loading (may take 2-5 minutes for large models)
- Verify GPU memory is sufficient: `nvidia-smi`

## Comparison: NIM vs TensorRT-LLM

| Feature | TensorRT-LLM | NVIDIA NIM |
|---------|--------------|------------|
| **Setup Time** | Longer (requires compilation) | Faster (pre-built) |
| **Optimization** | Full control | Pre-optimized by NVIDIA |
| **Model Flexibility** | Any model | Pre-selected models |
| **Deployment** | More complex | Simpler |
| **Performance** | Highly optimized for your hardware | Optimized for general use |
| **Use Case** | Production, specific optimization needs | Faster iteration, prototyping |

## Next Steps

1. **Verify NIM setup:**
   ```bash
   poetry run python -m essence verify-nim
   ```

2. **Test with June services:**
   - Update `LLM_URL` to use NIM
   - Start telegram/discord services
   - Send a test message

3. **Monitor performance:**
   - Check GPU usage: `nvidia-smi`
   - Check service logs: `docker compose logs telegram`
   - Check metrics in Prometheus/Grafana

## References

- **NGC Catalog:** https://catalog.ngc.nvidia.com/
- **NIM Documentation:** Check NGC catalog for container-specific documentation
- **TensorRT-LLM Setup:** See `docs/guides/TENSORRT_LLM_SETUP.md` for comparison
- **Verify Command:** `poetry run python -m essence verify-nim --help`

## Notes

- **Image Name:** The current configuration uses `nvcr.io/nim/qwen/qwen3-32b-dgx-spark:1.0.0` which is the DGX Spark ARM64-compatible version. For other architectures, use standard NIM containers (without "dgx-spark" suffix).
- **NGC API Key:** Required for pulling NIM containers. Store securely and don't commit to version control.
- **Model Loading:** Large models (32B+) may take 5-10 minutes to download and load on first startup. Health checks account for this with `start_period: 120s`. Subsequent starts are faster as model files are cached.
- **ARM64 Compatibility:** DGX Spark NIMs are specifically built for ARM64 architecture. Standard NIM containers are AMD64-only and won't work on ARM64 systems.
