# June Development Plan

## Status: ✅ **CORE REFACTORING COMPLETE** → 🚀 **FORWARD DEVELOPMENT IN PROGRESS**

**Last Updated:** 2025-11-18

**Note:** Commit count (e.g., "X commits ahead of origin/main") is informational only and does not need to be kept in sync. Do not update commit counts automatically - this creates an infinite loop.

## Goal

Build a complete **voice message → STT → LLM → TTS → voice response** system with **agentic LLM reasoning** before responding, supporting both **Telegram** and **Discord** platforms.

**Extended Goal:** 
- Get Qwen3-30B-A3B-Thinking-2507 running on **GPU** via **TensorRT-LLM** (CPU loading is FORBIDDEN)
- Develop agentic flow that performs reasoning/planning before responding to users
- Evaluate model performance on benchmark datasets
- All operations must be containerized - no host system pollution

## Completed Work Summary

### ✅ Core Refactoring (Phases 1-14) - COMPLETE

All major refactoring phases have been completed:

- ✅ **Service Removal and Cleanup (Phases 1-3):** Removed non-essential services, cleaned up dependencies
- ✅ **Observability (Phases 4-5):** OpenTelemetry tracing, Prometheus metrics implemented
- ✅ **Package Simplification (Phase 6):** Removed unused packages, migrated to Poetry in-place installation
- ✅ **Documentation Cleanup (Phase 7):** Updated all documentation to reflect current architecture
- ✅ **Service Refactoring (Phase 9.1):** All services refactored to minimal architecture
- ✅ **Scripts Cleanup (Phase 11):** Converted reusable tools to commands, removed obsolete scripts
- ✅ **Test Infrastructure (Phases 12-13):** Integration test service with REST API, Prometheus/Grafana monitoring
- ✅ **Message History Debugging (Phase 14):** Implemented `get_message_history()` for Telegram/Discord debugging

**Verification:**
- ✅ All 112 unit tests passing (`pytest tests/essence/`)
- ✅ No linting errors
- ✅ Clean git working tree
- ✅ Minimal architecture achieved
- ✅ All code-related refactoring complete

**Best Practices Established:**
- Minimal architecture - only essential services
- Container-first development - no host system pollution
- Command pattern for reusable tools
- Unit tests with mocked dependencies
- Integration tests via test service (background)
- OpenTelemetry tracing and Prometheus metrics

## Current Architecture

### Essential Services
1. **telegram** - Receives voice messages from Telegram, orchestrates the pipeline
2. **discord** - Receives voice messages from Discord, orchestrates the pipeline
3. **stt** - Speech-to-text conversion (Whisper)
4. **tts** - Text-to-speech conversion (FastSpeech2/espeak)
5. ~~**inference-api**~~ → **TensorRT-LLM** (migration in progress)

### Infrastructure
- **LLM Inference:** Migrating from `inference-api` service to **TensorRT-LLM container** (from home_infra shared-network)
- **From home_infra (shared-network):** nginx, jaeger, prometheus, grafana (available)
- All services communicate via gRPC directly

## Next Development Priorities

### Phase 15: TensorRT-LLM Integration ⏳ IN PROGRESS

**Goal:** Replace `inference-api` service with TensorRT-LLM container for optimized GPU inference.

**Tasks:**
1. **Set up TensorRT-LLM container in home_infra:**
   - Add TensorRT-LLM service to `home_infra/docker-compose.yml`
   - Configure it to connect to shared-network
   - Set up GPU access and resource limits
   - Configure model storage and cache directories

2. **Implement model loading/unloading:**
   - Create API/interface for loading models into TensorRT-LLM
   - Create API/interface for unloading models
   - Support multiple models (load one at a time, unload before loading another)
   - Handle model switching gracefully (unload current, load new)

3. **Migrate june services to use TensorRT-LLM:**
   - Update telegram service to connect to TensorRT-LLM instead of inference-api
   - Update discord service to connect to TensorRT-LLM instead of inference-api
   - Update any other services that use inference-api
   - Remove inference-api service from june docker-compose.yml

4. **Get Qwen3-30B-A3B-Thinking-2507 running:**
   - Load Qwen3 model into TensorRT-LLM container
   - Verify GPU usage (must use GPU, CPU fallback FORBIDDEN)
   - Test model inference via gRPC interface
   - Verify quantization and memory usage

**Critical Requirements:**
- **GPU-only loading:** Large models (30B+) must NEVER load on CPU
- **Fail fast:** TensorRT-LLM must fail if GPU is not available, not attempt CPU loading
- **GPU verification:** Verify GPU availability before model loading
- **Model switching:** Support loading/unloading models dynamically

### Phase 16: End-to-End Pipeline Testing ⏳ TODO

**Goal:** Verify complete voice message → STT → LLM → TTS → voice response flow works end-to-end.

**Tasks:**
1. **Test STT → LLM → TTS flow:**
   - Send voice message via Telegram
   - Verify STT converts to text correctly
   - Verify LLM (Qwen3 via TensorRT-LLM) processes text
   - Verify TTS converts response to audio
   - Verify audio is sent back to user

2. **Test Discord integration:**
   - Repeat above flow for Discord
   - Verify platform-specific handling works correctly

3. **Debug rendering issues:**
   - Use `get_message_history()` to inspect what was actually sent
   - Compare expected vs actual output
   - Fix any formatting/markdown issues
   - Verify message history works for both Telegram and Discord

4. **Performance testing:**
   - Measure latency for each stage (STT, LLM, TTS)
   - Identify bottlenecks
   - Optimize where possible

### Phase 17: Agentic Flow Implementation ⏳ TODO

**Goal:** Implement agentic reasoning/planning before responding to users (not just one-off LLM calls).

**Tasks:**
1. **Design agentic flow architecture:**
   - Define reasoning loop (think → plan → execute → reflect)
   - Determine when to use agentic flow vs direct response
   - Design conversation context management

2. **Implement reasoning loop:**
   - Create agentic reasoning service/component
   - Implement planning phase (break down user request into steps)
   - Implement execution phase (carry out plan)
   - Implement reflection phase (evaluate results, adjust if needed)

3. **Integrate with LLM (Qwen3 via TensorRT-LLM):**
   - Use Qwen3 for reasoning/planning
   - Use Qwen3 for execution (code generation, problem solving)
   - Use Qwen3 for reflection (evaluating results)

4. **Test agentic flow:**
   - Test with simple tasks first
   - Gradually increase complexity
   - Verify reasoning improves response quality
   - Measure performance impact

5. **Optimize for latency:**
   - Balance reasoning depth vs response time
   - Implement timeout mechanisms
   - Cache common reasoning patterns if applicable

### Phase 18: Model Evaluation and Benchmarking ⏳ TODO

**Goal:** Evaluate Qwen3 model performance on benchmark datasets.

**Tasks:**
1. **Set up benchmark evaluation:**
   - Integrate benchmark datasets (HumanEval, MBPP, SWE-bench, CodeXGLUE)
   - Create evaluation framework
   - Set up sandbox execution environment (containers/chroots)

2. **Run evaluations:**
   - Execute benchmarks with Qwen3 model
   - Collect results (correctness, efficiency, solution quality)
   - Compare against baseline/other models if available

3. **Analyze results:**
   - Identify model strengths and weaknesses
   - Document findings
   - Use insights to improve agentic flow

4. **Iterate and improve:**
   - Adjust agentic flow based on evaluation results
   - Test different reasoning strategies
   - Measure improvement over iterations

## Critical Requirements

### GPU-Only Model Loading (MANDATORY)

**CRITICAL:** Large models (30B+ parameters) must **NEVER** be loaded on CPU. Loading a 30B model on CPU consumes 100GB+ of system memory and will cause system instability.

**Requirements:**
1. **All large models must use GPU** - Models like Qwen3-30B-A3B-Thinking-2507 must load on GPU with quantization (4-bit or 8-bit)
2. **TensorRT-LLM handles GPU loading** - TensorRT-LLM container must be configured for GPU-only operation
3. **CPU fallback is FORBIDDEN for large models** - TensorRT-LLM must fail if GPU is not available, not attempt CPU loading
4. **GPU compatibility must be verified before model loading** - TensorRT-LLM should verify GPU availability before starting
5. **Consult external sources for GPU setup** - If GPU is not working:
   - Check TensorRT-LLM documentation for GPU requirements and setup
   - Review NVIDIA documentation for compute capability support
   - Check container GPU access (nvidia-docker, GPU passthrough)
   - Review model quantization and optimization options

## Operational Guide

### When Ready to Use the System

1. **Set up TensorRT-LLM container:**
   ```bash
   cd /home/rlee/dev/home_infra
   # Add tensorrt-llm service configuration to docker-compose.yml
   docker compose up -d tensorrt-llm
   ```

2. **Load Qwen3 model:**
   ```bash
   # Use TensorRT-LLM API to load Qwen3-30B-A3B-Thinking-2507
   # (API/interface to be implemented in Phase 15)
   ```

3. **Start june services:**
   ```bash
   cd /home/rlee/dev/june
   docker compose up -d telegram discord stt tts
   ```

4. **Test end-to-end flow:**
   ```bash
   # Send voice message via Telegram/Discord
   # Verify complete pipeline works
   ```

5. **Debug with message history:**
   ```bash
   # Get message history to debug rendering issues
   poetry run -m essence get-message-history --user-id <id> --limit 10
   ```

6. **Test agentic flow:**
   ```bash
   # Test agentic reasoning with coding tasks
   poetry run -m essence coding-agent --interactive
   ```

7. **Run benchmark evaluations:**
   ```bash
   # Run benchmark evaluations
   poetry run -m essence run-benchmarks --dataset humaneval --max-tasks 10
   ```

**Prerequisites:**
- NVIDIA GPU with 20GB+ VRAM (for Qwen3-30B with quantization)
- NVIDIA Container Toolkit installed and configured
- Docker with GPU support enabled
- TensorRT-LLM container set up in home_infra

## Architecture Principles

### Minimal Architecture
- **Essential services only:** telegram, discord, stt, tts, TensorRT-LLM (via home_infra)
- **LLM inference:** TensorRT-LLM container (from home_infra shared-network) - optimized GPU inference
- **No external dependencies:** All services communicate via gRPC directly
- **In-memory alternatives:** Conversation storage and rate limiting use in-memory implementations
- **Container-first:** All operations run in Docker containers - no host system pollution
- **Command pattern:** All services follow `python -m essence <service-name>` pattern

### Code Organization
- **Service code:** `essence/services/<service-name>/` - Actual service implementation
- **Service config:** `services/<service-name>/` - Dockerfiles and service-specific configuration
- **Shared code:** `essence/chat/` - Shared utilities for telegram and discord
- **Commands:** `essence/commands/` - Reusable tools runnable via `poetry run -m essence <command-name>`
- **Scripts:** `scripts/` - Shell scripts for complex container operations and automation only
- **Tests:** `tests/` - All test code, runnable via pytest

### Testing Philosophy
- **Unit tests:** Classic unit tests with all external services/libraries mocked
- **Integration tests:** Run in background, checked periodically via test service (not waited on)
- **Test service:** REST interface and logs for checking integration test runs
- **All tests runnable via pytest:** No custom test runners - use pytest for everything

### Observability
- **OpenTelemetry tracing:** Implemented across all services
- **Prometheus metrics:** Implemented and exposed
- **Health checks:** All services have health check endpoints
- **Message history:** Debug rendering issues with `get_message_history()`

## Next Steps

1. **Phase 15: TensorRT-LLM Integration** ⏳ IN PROGRESS
   - Set up TensorRT-LLM container in home_infra
   - Implement model loading/unloading
   - Migrate june services to use TensorRT-LLM
   - Get Qwen3 model running

2. **Phase 16: End-to-End Pipeline Testing** ⏳ TODO
   - Test complete voice → STT → LLM → TTS → voice flow
   - Debug rendering issues with message history
   - Performance testing and optimization

3. **Phase 17: Agentic Flow Implementation** ⏳ TODO
   - Design and implement reasoning loop
   - Integrate with Qwen3 via TensorRT-LLM
   - Test and optimize for latency

4. **Phase 18: Model Evaluation and Benchmarking** ⏳ TODO
   - Set up benchmark evaluation framework
   - Run evaluations on Qwen3
   - Analyze results and iterate

## Known Issues

### Test Infrastructure
- ✅ Core test infrastructure complete
- ✅ All 112 unit tests in `tests/essence/` passing
- ⚠️ Some integration/service tests may need updates for TensorRT-LLM migration

### Pre-existing Test Failures
- ✅ All tests now passing (112/112)

## Refactoring Status Summary

**Overall Status:** ✅ **CORE REFACTORING COMPLETE** → 🚀 **FORWARD DEVELOPMENT IN PROGRESS**

**Code Refactoring Status:** ✅ **ALL CODE-RELATED REFACTORING COMPLETE**

All code changes, cleanup, and refactoring tasks have been completed:
- ✅ All removed service dependencies eliminated from code
- ✅ All gateway references cleaned up
- ✅ All obsolete test files and scripts marked appropriately
- ✅ All code references updated to reflect current architecture
- ✅ All unit tests passing (112/112 in tests/essence/)
- ✅ Minimal architecture achieved with only essential services

**Current Development Focus:**
- 🚀 **Phase 15:** TensorRT-LLM Integration (IN PROGRESS)
- ⏳ **Phase 16:** End-to-End Pipeline Testing (TODO)
- ⏳ **Phase 17:** Agentic Flow Implementation (TODO)
- ⏳ **Phase 18:** Model Evaluation and Benchmarking (TODO)

**Current State:**
- ✅ All essential services refactored and working
- ✅ All unit tests passing (112/112 in tests/essence/)
- ✅ Minimal architecture achieved
- ✅ Message history debugging implemented
- 🚀 Migrating from inference-api to TensorRT-LLM
- ⏳ Implementing agentic flow for better responses
- ⏳ Setting up model evaluation framework
