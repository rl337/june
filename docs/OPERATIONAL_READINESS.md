# Operational Readiness Checklist

This document provides a comprehensive checklist for operational tasks that require services to be running. Use this guide to prepare for and execute operational work.

## Prerequisites

Before starting any operational tasks, ensure:

- ✅ All code implementation is complete (451 tests passing, 1 skipped)
- ✅ All infrastructure is ready (commands, tools, documentation)
- ✅ GitHub Actions are passing
- ✅ No uncommitted changes in git
- ✅ Docker and Docker Compose are installed and working
- ✅ GPU access is configured (for LLM inference)
- ✅ Required environment variables are documented

## Phase 10.1-10.2: Qwen3 Model Setup on GPU

### Prerequisites
- [ ] `HUGGINGFACE_TOKEN` environment variable set
- [ ] GPU available and accessible from Docker containers
- [ ] Sufficient disk space for model download (~60GB for Qwen3-30B)
- [ ] Network connectivity for model download

### Steps
1. **Pre-flight check:**
   ```bash
   poetry run python -m essence check-environment
   ```

2. **Model download (if needed):**
   ```bash
   docker compose run --rm cli-tools poetry run python -m essence download-models --model Qwen/Qwen3-30B-A3B-Thinking-2507
   ```
   Or use helper script:
   ```bash
   ./scripts/setup_qwen3_operational.sh
   ```

3. **Service startup:**
   - TensorRT-LLM (default): Start in `home_infra` project
   - Legacy inference-api: `docker compose up -d inference-api --profile legacy`

4. **Verification:**
   - Test model loading
   - Verify GPU utilization
   - Test basic inference

### Helper Script
- `scripts/setup_qwen3_operational.sh` - Orchestrates all steps

## Phase 15: NIM gRPC Connectivity Testing

### Prerequisites
- [ ] `NGC_API_KEY` environment variable set in `home_infra`
- [ ] NIM service configured in `home_infra/docker-compose.yml`
- [ ] Correct NIM image name verified from NGC catalog
- [ ] Network connectivity between `june` and `home_infra` services

### Steps
1. **Pre-flight check:**
   ```bash
   poetry run python -m essence check-environment
   ```

2. **NGC API key verification:**
   - Verify `NGC_API_KEY` is set in `home_infra` environment
   - Test NGC API access

3. **Image name verification:**
   - Check NGC catalog for correct image name
   - Verify image name in `home_infra/docker-compose.yml`

4. **Service startup:**
   ```bash
   cd /home/rlee/dev/home_infra
   docker compose up -d nim-qwen3
   ```

5. **Verification:**
   ```bash
   cd /home/rlee/dev/june
   poetry run python -m essence verify-nim --nim-host nim-qwen3 --http-port 8003 --grpc-port 8001
   ```

6. **gRPC connectivity test:**
   - Test gRPC connectivity from june services
   - Verify protocol compatibility
   - Test inference requests

### Helper Script
- `scripts/setup_nim_operational.sh` - Orchestrates all steps

## Phase 16: End-to-End Pipeline Testing

### Prerequisites
- [ ] All services running (STT, TTS, LLM)
- [ ] Telegram/Discord bot tokens configured
- [ ] Network connectivity between all services
- [ ] Test user accounts available

### Steps
1. **Service verification:**
   ```bash
   docker compose ps
   ```
   Verify all required services are running:
   - STT service
   - TTS service
   - LLM service (TensorRT-LLM, NIM, or legacy inference-api)

2. **Pre-flight check:**
   ```bash
   poetry run python -m essence check-environment
   ```

3. **Test complete pipeline:**
   - Send voice message via Telegram/Discord
   - Verify STT transcription
   - Verify LLM response generation
   - Verify TTS audio synthesis
   - Verify audio response delivery

4. **Performance testing:**
   - Measure latency for each stage
   - Identify bottlenecks
   - Document metrics

### Helper Script
- `scripts/run_performance_tests_operational.sh` - Orchestrates performance testing

## Phase 18: Benchmark Evaluation

### Prerequisites
- [ ] LLM service running (TensorRT-LLM, NIM, or legacy inference-api)
- [ ] Sufficient GPU memory for model inference
- [ ] Disk space for benchmark results
- [ ] Network connectivity to LLM service

### Steps
1. **Service verification:**
   ```bash
   # Check TensorRT-LLM
   poetry run python -m essence verify-tensorrt-llm
   
   # Or check NIM
   poetry run python -m essence verify-nim --nim-host nim-qwen3 --http-port 8003 --grpc-port 8001
   
   # Or check legacy inference-api
   docker compose ps inference-api
   ```

2. **Pre-flight check:**
   ```bash
   poetry run python -m essence check-environment
   ```

3. **Run benchmarks:**
   ```bash
   poetry run python -m essence run-benchmarks --dataset humaneval --llm-url grpc://tensorrt-llm:8000
   ```
   Or use helper script:
   ```bash
   ./scripts/run_benchmarks_operational.sh --run-now
   ```

4. **Analyze results:**
   - Review correctness metrics
   - Review efficiency metrics
   - Document findings

### Helper Script
- `scripts/run_benchmarks_operational.sh` - Orchestrates benchmark execution

## Phase 19: Direct Agent-User Communication

### Prerequisites
- [ ] Telegram/Discord bot tokens configured
- [ ] Whitelist user IDs identified
- [ ] Telegram/Discord services can be started/stopped
- [ ] Agent loop script ready (`scripts/refactor_agent_loop.sh`)

### Steps
1. **Configure whitelisted users:**
   ```bash
   export TELEGRAM_WHITELISTED_USERS="user_id1,user_id2"
   export DISCORD_WHITELISTED_USERS="user_id1,user_id2"
   ```

2. **Start services with whitelist:**
   ```bash
   docker compose up -d telegram discord
   ```

3. **Verify whitelist configuration:**
   - Check service logs for whitelist loading
   - Verify routing logic

4. **Test end-to-end communication:**
   - Send test message from whitelisted user
   - Verify message appears in `USER_REQUESTS.md`
   - Verify agent reads and responds
   - Verify response synced to `USER_REQUESTS.md`

5. **Test features:**
   - Message grouping and editing
   - Periodic polling detects responses
   - Service conflict prevention

### Verification Commands
- Check service status: `poetry run python -m essence check-service-status`
- Read user requests: `poetry run python -m essence read-user-requests`
- Poll for responses: `poetry run python -m essence poll-user-responses`

## Common Operational Tasks

### Service Management
- **Start services:** `docker compose up -d <service>`
- **Stop services:** `docker compose stop <service>`
- **View logs:** `docker compose logs -f <service>`
- **Check status:** `docker compose ps`

### Environment Variables
Key environment variables for operational tasks:
- `HUGGINGFACE_TOKEN` - For model downloads
- `NGC_API_KEY` - For NIM service (set in `home_infra`)
- `TELEGRAM_BOT_TOKEN` - For Telegram service
- `DISCORD_BOT_TOKEN` - For Discord service
- `TELEGRAM_WHITELISTED_USERS` - For Phase 19
- `DISCORD_WHITELISTED_USERS` - For Phase 19

### Network Configuration
- **june_network** - Internal network for june services
- **shared-network** - External network connecting to home_infra services
- Services communicate via gRPC directly

### Troubleshooting
- **Service not starting:** Check logs with `docker compose logs <service>`
- **Network issues:** Verify Docker networks are configured correctly
- **GPU not accessible:** Check NVIDIA Container Toolkit installation
- **Model download fails:** Verify `HUGGINGFACE_TOKEN` and network connectivity

## Quick Reference

### Helper Scripts
- `scripts/setup_qwen3_operational.sh` - Phase 10.1-10.2
- `scripts/setup_nim_operational.sh` - Phase 15
- `scripts/run_performance_tests_operational.sh` - Phase 16 Task 5
- `scripts/run_benchmarks_operational.sh` - Phase 18

### Verification Commands
- `poetry run python -m essence check-environment` - Pre-flight checks
- `poetry run python -m essence verify-tensorrt-llm` - TensorRT-LLM verification
- `poetry run python -m essence verify-nim` - NIM verification
- `poetry run python -m essence check-service-status` - Service status

### Documentation
- `REFACTOR_PLAN.md` - Main refactoring plan with all phases
- `QWEN3_SETUP_PLAN.md` - Detailed Qwen3 setup instructions
- `docs/guides/TENSORRT_LLM_SETUP.md` - TensorRT-LLM setup guide
- `docs/guides/NIM_SETUP.md` - NIM setup guide
- `docs/guides/AGENT_COMMUNICATION.md` - Phase 19 communication guide

## Status

**Current State:** All code implementation complete. All infrastructure ready. Project is ready for operational work.

**Last Updated:** 2025-11-20
