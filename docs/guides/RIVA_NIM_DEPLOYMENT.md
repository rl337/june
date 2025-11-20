# Riva ASR/TTS NIM Deployment Guide

This guide provides a complete step-by-step workflow for deploying Riva ASR (Speech-to-Text) and Riva TTS (Text-to-Speech) NIM containers in the June project.

## Overview

**Status:** Phase 19 - Operational Deployment Tasks

Riva NIMs provide pre-built, optimized containers for speech-to-text and text-to-speech inference. Unlike custom STT/TTS services, NIMs don't require model compilation or dependency management - they come with optimized models pre-installed.

### Architecture

- **Custom STT/TTS Services:** Currently configured in `june/docker-compose.yml` (Whisper for STT, FastSpeech2 for TTS)
- **Riva NIMs:** Pre-built containers with optimized models (alternative, requires ARM64/DGX Spark compatibility verification)
- **LLM NIM:** Already configured (Qwen3-32B DGX Spark NIM in `home_infra/docker-compose.yml`)

### When to Use Riva NIMs

- **Faster deployment:** No model compilation or dependency management
- **Pre-optimized models:** Models are already optimized by NVIDIA
- **Easier maintenance:** Just pull and run the container
- **Trade-off:** Requires ARM64/DGX Spark compatibility (needs verification)

## Prerequisites

- NVIDIA GPU with sufficient VRAM
- NVIDIA Container Toolkit installed and configured
- Docker with GPU support enabled
- **NGC API Key** - Required for accessing NVIDIA NGC container registry
  - Get your API key from: https://catalog.ngc.nvidia.com/
  - Sign in to NGC, go to your profile → API Keys → Generate API Key
  - Set in `home_infra` environment: `export NGC_API_KEY='your-api-key'`

## Complete Deployment Workflow

### Step 1: Verify NIM Compatibility

**Goal:** Check if Riva ASR/TTS NIMs are available and compatible with ARM64/DGX Spark architecture.

**Method 1: Using Helper Script (Recommended)**

```bash
# Check both STT and TTS NIMs
./scripts/verify_nim_compatibility.sh

# Check only STT NIMs
./scripts/verify_nim_compatibility.sh --stt-only

# Check only TTS NIMs
./scripts/verify_nim_compatibility.sh --tts-only
```

**Method 2: Using list-nims Command**

```bash
# List STT NIMs (DGX Spark compatible)
poetry run python -m essence list-nims --dgx-spark-only --filter stt --ngc-api-key $NGC_API_KEY

# List TTS NIMs (DGX Spark compatible)
poetry run python -m essence list-nims --dgx-spark-only --filter tts --ngc-api-key $NGC_API_KEY
```

**What to Look For:**

- ✅ **ARM64/DGX Spark compatible:** Image path, exact version tag
- ⚠️ **Unknown compatibility:** Marked as "⚠️ Unknown" - needs manual verification
- ❌ **Not compatible:** Continue using custom STT/TTS services

**Output Example:**

```
==========================================
Checking STT (Speech-to-Text) NIMs (stt)
==========================================

Querying NGC catalog for DGX Spark compatible STT NIMs...

| Name              | Image Path                          | DGX Spark | Note                    |
|-------------------|-------------------------------------|-----------|-------------------------|
| Riva-ASR-Parakeet | nvcr.io/nim/riva/riva-asr:1.0.0     | ⚠️ Unknown | Needs verification      |

==========================================
Next Steps for STT (Speech-to-Text) NIM
==========================================

1. **If NIM found with ARM64/DGX Spark support:**
   - Note the exact image path (e.g., nvcr.io/nim/riva/riva-asr:1.0.0)
   - Verify compatibility in NGC catalog: https://catalog.ngc.nvidia.com/
   - Check documentation for exact image tag and architecture support
```

### Step 2: Verify Image Path in NGC Catalog

**Goal:** Confirm the exact image path and ARM64/DGX Spark compatibility.

1. **Access NGC Catalog:**
   - Go to https://catalog.ngc.nvidia.com/
   - Sign in with your NVIDIA account
   - Navigate to **Containers** → **NIM** (or search for "Riva")

2. **Find Riva ASR/TTS Containers:**
   - Search for "riva-asr" or "riva-tts"
   - Look for containers matching the image path from Step 1
   - Check container details for:
     - **Architecture support:** Look for "ARM64" or "DGX Spark" in supported architectures
     - **Exact image tag:** Note the full image path (e.g., `nvcr.io/nim/riva/riva-asr:1.0.0`)
     - **Documentation:** Read release notes for compatibility information

3. **Verify Compatibility:**
   - ✅ **If ARM64/DGX Spark supported:** Proceed to Step 3
   - ❌ **If not supported:** Continue using custom STT/TTS services (already configured)

### Step 3: Generate docker-compose.yml Service Snippet

**Goal:** Generate the service definition for `home_infra/docker-compose.yml`.

**Using Helper Script:**

```bash
# Generate STT (Riva ASR) NIM service snippet
./scripts/generate_nim_compose_snippet.sh --stt --image nvcr.io/nim/riva/riva-asr:1.0.0

# Generate TTS (Riva TTS) NIM service snippet
./scripts/generate_nim_compose_snippet.sh --tts --image nvcr.io/nim/riva/riva-tts:1.0.0

# Custom ports (if needed)
./scripts/generate_nim_compose_snippet.sh --stt --image nvcr.io/nim/riva/riva-asr:1.0.0 --grpc-port 8002 --http-port 8004
```

**Output Example:**

```yaml
# Riva ASR (Speech-to-Text) NIM Service
# Generated by: scripts/generate_nim_compose_snippet.sh
#
# This service provides Riva ASR (Speech-to-Text) inference via NVIDIA NIM container.
# Requires NGC_API_KEY for authentication.
#
nim-riva-asr:
  image: nvcr.io/nim/riva/riva-asr:1.0.0
  container_name: common-nim-riva-asr
  restart: unless-stopped
  expose:
    - "8002"  # gRPC endpoint (internal to shared-network, accessible as nim-riva-asr:8002)
    - "8004"  # HTTP endpoint (internal, for health checks)
  environment:
    - CUDA_VISIBLE_DEVICES=0
    - NGC_API_KEY=${NGC_API_KEY}  # Required for NGC container access
    - ENABLE_TRACING=${ENABLE_TRACING:-true}
    - JAEGER_ENDPOINT=http://common-jaeger:14268/api/traces
    - JAEGER_AGENT_HOST=common-jaeger
    - JAEGER_AGENT_PORT=6831
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids:
              - '0'
            capabilities:
              - gpu
  volumes:
    - ${MODEL_CACHE_DIR:-/home/rlee/models}:/models
    - /var/log/june/nim-riva-asr:/logs
    - /var/data/june/nim-riva-asr:/data
  networks:
    - shared-network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8004/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 120s  # Allow time for model loading
```

### Step 4: Add Service to home_infra/docker-compose.yml

**Goal:** Add the generated service definition to `home_infra/docker-compose.yml`.

1. **Navigate to home_infra:**
   ```bash
   cd /home/rlee/dev/home_infra
   ```

2. **Add Service Definition:**
   - Copy the generated snippet from Step 3
   - Open `docker-compose.yml`
   - Add the service definition following the `nim-qwen3` pattern
   - Ensure proper indentation and YAML syntax

3. **Verify Configuration:**
   - Check that `NGC_API_KEY` is set in environment (or `.env` file)
   - Verify network is `shared-network` (connects to june services)
   - Confirm GPU allocation matches your hardware
   - Check port assignments don't conflict with existing services

**Port Assignments:**
- **LLM NIM:** gRPC 8001, HTTP 8003
- **STT NIM:** gRPC 8002, HTTP 8004 (default)
- **TTS NIM:** gRPC 8005, HTTP 8006 (default)

### Step 5: Start NIM Service

**Goal:** Start the Riva NIM service and verify it's running.

```bash
# Navigate to home_infra
cd /home/rlee/dev/home_infra

# Start STT NIM service
docker compose up -d nim-riva-asr

# Start TTS NIM service
docker compose up -d nim-riva-tts

# Check service status
docker compose ps nim-riva-asr
docker compose ps nim-riva-tts

# View logs
docker compose logs -f nim-riva-asr
docker compose logs -f nim-riva-tts
```

**Expected Output:**

- Service status: `Up` (healthy)
- Logs show: Model loading, service ready, health check passing
- No errors related to architecture compatibility

### Step 6: Verify Service Connectivity

**Goal:** Verify the NIM service is accessible from june services.

**From june project:**

```bash
# Navigate to june project
cd /home/rlee/dev/june

# Verify NIM connectivity (if verify-nim command supports STT/TTS)
poetry run python -m essence verify-nim --nim-host nim-riva-asr --http-port 8004 --grpc-port 8002

# Check GPU utilization
nvidia-smi
```

**Manual Verification:**

```bash
# Test HTTP health endpoint (from june container or host)
curl -f http://nim-riva-asr:8004/health

# Test gRPC connectivity (requires gRPC client)
# Use june services' gRPC clients to test connectivity
```

### Step 7: Update june Services to Use NIM (Optional)

**Goal:** Configure june services to use Riva NIMs instead of custom STT/TTS services.

**Note:** This step is optional - custom STT/TTS services can continue to be used. Only update if you want to switch to NIMs.

1. **Update Service Configuration:**
   - Modify `june/docker-compose.yml` to point STT/TTS services to NIM endpoints
   - Or configure environment variables to use NIM endpoints

2. **Test End-to-End:**
   - Send voice message via Telegram/Discord
   - Verify STT → LLM → TTS pipeline works with NIMs
   - Check latency and quality compared to custom services

## Troubleshooting

### Issue: NIM Service Won't Start

**Symptoms:**
- Service exits immediately
- Logs show architecture mismatch errors

**Solutions:**
- Verify ARM64/DGX Spark compatibility in NGC catalog
- Check `NGC_API_KEY` is set correctly
- Review logs for specific error messages
- Fall back to custom STT/TTS services if NIMs aren't compatible

### Issue: Service Starts But Health Check Fails

**Symptoms:**
- Service status shows "starting" indefinitely
- Health check endpoint returns errors

**Solutions:**
- Check service logs for model loading progress
- Verify GPU is accessible: `nvidia-smi`
- Increase `start_period` in healthcheck if model loading takes longer
- Check network connectivity: `docker network inspect shared-network`

### Issue: gRPC Connectivity Problems

**Symptoms:**
- june services can't connect to NIM
- Connection refused errors

**Solutions:**
- Verify NIM service is on `shared-network`
- Check port assignments match configuration
- Test connectivity from june container: `docker compose exec telegram curl http://nim-riva-asr:8004/health`
- Review network configuration in `home_infra/docker-compose.yml`

## Helper Scripts Reference

### verify_nim_compatibility.sh

**Purpose:** Check NIM availability and compatibility

**Usage:**
```bash
./scripts/verify_nim_compatibility.sh [--stt-only] [--tts-only] [--update-compose]
```

**Options:**
- `--stt-only`: Only check STT NIMs
- `--tts-only`: Only check TTS NIMs
- `--update-compose`: Interactive mode to update docker-compose.yml

### generate_nim_compose_snippet.sh

**Purpose:** Generate docker-compose.yml service snippets

**Usage:**
```bash
./scripts/generate_nim_compose_snippet.sh [--stt] [--tts] [--image IMAGE] [--name NAME] [--grpc-port PORT] [--http-port PORT]
```

**Options:**
- `--stt`: Generate STT (Riva ASR) NIM service snippet
- `--tts`: Generate TTS (Riva TTS) NIM service snippet
- `--image IMAGE`: Docker image path (required)
- `--name NAME`: Service name (optional, has defaults)
- `--grpc-port PORT`: gRPC port (optional, has defaults)
- `--http-port PORT`: HTTP port (optional, has defaults)

### list-nims Command

**Purpose:** List available NIM containers from NGC catalog

**Usage:**
```bash
poetry run python -m essence list-nims [--dgx-spark-only] [--filter stt|tts] [--ngc-api-key KEY] [--format table|markdown]
```

**Options:**
- `--dgx-spark-only`: Only show DGX Spark compatible NIMs
- `--filter stt|tts`: Filter by service type
- `--ngc-api-key KEY`: NGC API key for catalog queries
- `--format table|markdown`: Output format

## Current Status

**LLM NIM:**
- ✅ Qwen3-32B DGX Spark NIM configured in `home_infra/docker-compose.yml`
- ✅ Ready to deploy (requires `NGC_API_KEY`)

**STT NIM:**
- ⚠️ Riva ASR NIM placeholder (needs verification)
- ⚠️ ARM64/DGX Spark compatibility unknown
- ✅ Helper scripts available for verification and deployment

**TTS NIM:**
- ⚠️ Riva TTS NIM placeholder (needs verification)
- ⚠️ ARM64/DGX Spark compatibility unknown
- ✅ Helper scripts available for verification and deployment

## Next Steps

1. **Verify Compatibility:** Use `verify_nim_compatibility.sh` or `list-nims` command to check ARM64/DGX Spark support
2. **Generate Service Definition:** Use `generate_nim_compose_snippet.sh` to create docker-compose.yml snippet
3. **Deploy Service:** Add to `home_infra/docker-compose.yml` and start service
4. **Test Connectivity:** Verify service is accessible from june services
5. **Update june Services:** (Optional) Configure june services to use NIMs instead of custom services

## Related Documentation

- **[NIM Setup Guide](NIM_SETUP.md)** - General NIM setup for LLM inference
- **[Operational Readiness Checklist](../OPERATIONAL_READINESS.md)** - Comprehensive operational tasks guide
- **[NIM Availability](../NIM_AVAILABILITY.md)** - Detailed NIM availability status
- **[Phase 19 Tasks](../../REFACTOR_PLAN.md#phase-19-direct-agent-user-communication)** - Complete Phase 19 task list

## Summary

This guide provides a complete workflow for deploying Riva ASR/TTS NIMs:

1. ✅ **Verify compatibility** using helper scripts or `list-nims` command
2. ✅ **Confirm image path** in NGC catalog
3. ✅ **Generate service snippet** using `generate_nim_compose_snippet.sh`
4. ✅ **Add to docker-compose.yml** in `home_infra`
5. ✅ **Start service** and verify it's running
6. ✅ **Test connectivity** from june services
7. ✅ **Update june services** (optional) to use NIMs

All helper scripts and tools are ready - the remaining work is operational (verification and deployment).
