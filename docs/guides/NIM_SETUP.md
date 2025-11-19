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

**IMPORTANT:** The NIM image name in `home_infra/docker-compose.yml` may need verification. Follow these steps to find the correct image name:

### Step 1: Access NGC Catalog

1. Go to https://catalog.ngc.nvidia.com/
2. Sign in with your NVIDIA account
3. Navigate to **Containers** → **NIM** (or search for "NIM")

### Step 2: Find Qwen3 NIM Container

1. Search for "qwen3" or "qwen" in the NGC catalog
2. Look for containers with names like:
   - `nim_qwen3_30b_instruct`
   - `nim-qwen3-30b-instruct`
   - `qwen3-30b-instruct-nim`
3. Check the container details for:
   - Model size (should match 30B)
   - Architecture (should match A3B or your target architecture)
   - Instruction format (should match your use case)

### Step 3: Verify Image Name Format

NIM container images typically follow this format:
```
nvcr.io/nvidia/<container-name>:<tag>
```

**Common formats:**
- Production: `nvcr.io/nvidia/nim_qwen3_30b_instruct:latest`
- Staging: `nvcr.io/nvstaging/nim_qwen3_30b_instruct:latest` (may be used during development)
- Versioned: `nvcr.io/nvidia/nim_qwen3_30b_instruct:24.10` (specific version)

**Note:** The current configuration uses `nvcr.io/nvstaging/nim_qwen3_30b_instruct:latest`. Verify this is correct or update to the production image name from the NGC catalog.

### Step 4: Update docker-compose.yml

Once you've found the correct image name, update `home_infra/docker-compose.yml`:

```yaml
nim-qwen3:
  image: nvcr.io/nvidia/nim_qwen3_30b_instruct:latest  # Update with correct image name
  # ... rest of configuration
```

## Infrastructure Setup

### NIM Container (in home_infra)

The NIM container is configured in `/home/rlee/dev/home_infra/docker-compose.yml`:

```yaml
nim-qwen3:
  image: nvcr.io/nvstaging/nim_qwen3_30b_instruct:latest  # Verify this is correct
  container_name: common-nim-qwen3
  restart: unless-stopped
  expose:
    - "8001"  # gRPC endpoint (internal to shared-network)
    - "8003"  # HTTP endpoint (internal, for health checks)
  environment:
    - CUDA_VISIBLE_DEVICES=0
    - NGC_API_KEY=${NGC_API_KEY}  # Required for NGC container access
    - MAX_CONTEXT_LENGTH=${NIM_MAX_CONTEXT_LENGTH:-131072}
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
poetry run -m essence verify-nim

# With custom host/ports
poetry run -m essence verify-nim \
  --nim-host nim-qwen3 \
  --http-port 8003 \
  --grpc-port 8001

# Check gRPC protocol compatibility
poetry run -m essence verify-nim --check-protocol

# JSON output
poetry run -m essence verify-nim --json
```

**Expected output:**
- ✅ HTTP health check: Service responds on port 8003
- ✅ gRPC connectivity: Can connect to port 8001
- ✅ GPU availability: GPU is accessible
- ✅ Overall status: Ready

## Configuration

### Using NIM in June Services

June services can use NIM by setting the `LLM_URL` environment variable:

```bash
# In docker-compose.yml or environment
LLM_URL=grpc://nim-qwen3:8001
```

**Default configuration:**
- Telegram service: Uses TensorRT-LLM by default (`tensorrt-llm:8000`)
- Discord service: Uses TensorRT-LLM by default (`tensorrt-llm:8000`)
- To switch to NIM: Set `LLM_URL=grpc://nim-qwen3:8001`

### Service Configuration

Update `docker-compose.yml` to use NIM:

```yaml
services:
  telegram:
    environment:
      - LLM_URL=grpc://nim-qwen3:8001  # Use NIM instead of TensorRT-LLM
    # ... rest of configuration
```

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
   docker pull nvcr.io/nvstaging/nim_qwen3_30b_instruct:latest
   # If this fails, the image name may be incorrect - check NGC catalog
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
  docker pull nvcr.io/nvstaging/nim_qwen3_30b_instruct:latest
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
   poetry run -m essence verify-nim
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
- **Verify Command:** `poetry run -m essence verify-nim --help`

## Notes

- **Image Name Verification:** The image name `nvcr.io/nvstaging/nim_qwen3_30b_instruct:latest` in `home_infra/docker-compose.yml` should be verified against the NGC catalog before deployment. Staging images (`nvstaging`) may be used during development, but production should use `nvcr.io/nvidia/...` images.
- **NGC API Key:** Required for pulling NIM containers. Store securely and don't commit to version control.
- **Model Loading:** Large models (30B+) may take 2-5 minutes to load. Health checks account for this with `start_period: 120s`.
