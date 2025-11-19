# June Development Plan

## Status: ✅ **CORE REFACTORING COMPLETE** → 🚀 **FORWARD DEVELOPMENT IN PROGRESS**

**Last Updated:** 2025-11-18 (Phase 15.4: Created setup-triton-repository command for model repository structure management)

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
- ✅ **Qwen3 Setup and Coding Agent (Phase 10):** Model download infrastructure, coding agent with tool calling, benchmark evaluation framework with sandbox isolation (see QWEN3_SETUP_PLAN.md for details)

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

### Phase 10: Qwen3 Setup and Coding Agent ✅ COMPLETED

**Goal:** Get Qwen3-30B-A3B-Thinking-2507 running on GPU in containers and develop coding agent for benchmark evaluation.

**Status:** All infrastructure and code implementation complete. Operational tasks (model download, service startup) can be done when ready to use.

**Completed Tasks:**
1. ✅ **Model Download Infrastructure:**
   - ✅ `essence/commands/download_models.py` command implemented
   - ✅ Containerized download (runs in cli-tools container)
   - ✅ Model cache directory configured (`/home/rlee/models` → `/models` in container)
   - ✅ GPU-only loading for large models (30B+) with CPU fallback prevention
   - ✅ Duplicate load prevention (checks if model already loaded)

2. ✅ **Coding Agent:**
   - ✅ `essence/agents/coding_agent.py` - CodingAgent class implemented
   - ✅ Tool calling interface (file operations, code execution, directory listing)
   - ✅ Multi-turn conversation support
   - ✅ Sandboxed execution via `essence/agents/sandbox.py`
   - ✅ CLI command: `essence/commands/coding_agent.py`

3. ✅ **Benchmark Evaluation:**
   - ✅ `essence/agents/evaluator.py` - BenchmarkEvaluator class implemented
   - ✅ `essence/agents/dataset_loader.py` - Dataset loaders (HumanEval, MBPP)
   - ✅ `essence/commands/run_benchmarks.py` - Benchmark runner command
   - ✅ Sandbox isolation with full activity logging
   - ✅ Efficiency metrics capture (commands executed, time to solution, resource usage)

4. ✅ **Verification Tools:**
   - ✅ `essence/commands/verify_qwen3.py` - Model verification command
   - ✅ `essence/commands/benchmark_qwen3.py` - Performance benchmarking command
   - ✅ `essence/commands/check_environment.py` - Pre-flight environment validation

**Operational Tasks (When Ready to Use):**
- ⏳ Model download (if not already done): `docker compose run --rm cli-tools poetry run -m essence download-models --model Qwen/Qwen3-30B-A3B-Thinking-2507`
- ⏳ Service startup: `docker compose up -d inference-api` (or TensorRT-LLM once Phase 15 is complete)
- ⏳ Testing & validation: Test model loading, GPU utilization, coding agent, benchmark evaluations

**See:** `QWEN3_SETUP_PLAN.md` for detailed setup instructions and operational guide.

### Phase 15: TensorRT-LLM Integration ⏳ IN PROGRESS

**Goal:** Replace `inference-api` service with TensorRT-LLM container for optimized GPU inference.

**Current Status:** Code migration complete (Task 3 ✅). TensorRT-LLM container setup complete (Task 1 ✅). Model loading/unloading API implemented (Task 2 ✅). Remaining task (4) requires model compilation and actual model loading.

**IMPORTANT:** The agent CAN and SHOULD work on the `home_infra` project at `/home/rlee/dev/home_infra` to complete these tasks. This is NOT external work - it's part of the june project infrastructure. The agent has full access to modify `home_infra/docker-compose.yml` and related configuration files.

**Tasks:**
1. **Set up TensorRT-LLM container in home_infra:** ✅ COMPLETED
   - ✅ Added TensorRT-LLM service to `home_infra/docker-compose.yml`
   - ✅ Configured it to connect to shared-network
   - ✅ Set up GPU access and resource limits (device 0, GPU capabilities)
   - ✅ Configured model storage and cache directories (`/home/rlee/models` → `/models`)
   - ✅ Exposed port 8000 internally on shared-network (accessible as `tensorrt-llm:8000`)
   - ✅ Added health check endpoint
   - ✅ Configured environment variables for model name, quantization, context length
   - ✅ Added Jaeger tracing integration
   - ✅ Configured Triton model repository path (`/models/triton-repository`)
   - ✅ Added Triton command-line arguments (--model-repository, --allow-gpu-metrics, --allow-http)
   - ⏳ **Note:** Model repository directory structure must be created and models must be compiled before use (see Task 4)

2. **Implement model loading/unloading:** ✅ COMPLETED
   - ✅ Created `essence/commands/manage_tensorrt_llm.py` command for model management
   - ✅ Implemented `TensorRTLLMManager` class that interacts with Triton Inference Server's model repository API
   - ✅ Supports loading models via HTTP POST `/v2/repository/models/{model_name}/load`
   - ✅ Supports unloading models via HTTP POST `/v2/repository/models/{model_name}/unload`
   - ✅ Supports listing available models via GET `/v2/repository/index`
   - ✅ Supports checking model status via GET `/v2/models/{model_name}/ready`
   - ✅ CLI interface: `poetry run -m essence manage-tensorrt-llm --action {load|unload|list|status} --model <name>`
   - ✅ Uses httpx for HTTP client (already in dependencies)
   - ✅ Proper error handling for timeouts, connection errors, and API errors
   - ✅ Model switching: Can unload current model and load new one (one at a time)
   - ⏳ **Note:** Models must be compiled/prepared and placed in Triton's model repository before they can be loaded. This API handles loading/unloading operations only. Model compilation/preparation is a separate step (see Task 4).

3. **Migrate june services to use TensorRT-LLM:** ✅ COMPLETED (Code changes)
   - ✅ Updated telegram service configuration to default to TensorRT-LLM (tensorrt-llm:8000)
   - ✅ Updated discord service (uses same config via get_llm_address())
   - ✅ Updated CodingAgent to default to TensorRT-LLM
   - ✅ Updated BenchmarkEvaluator to default to TensorRT-LLM
   - ✅ Updated coding-agent command to default to TensorRT-LLM
   - ✅ Updated run-benchmarks command to default to TensorRT-LLM
   - ✅ Updated check-environment to remove inference-api from required services
   - ✅ Updated error messages and documentation to reference TensorRT-LLM
   - ✅ All changes maintain backward compatibility via LLM_URL/INFERENCE_API_URL environment variables
   - ✅ Updated docker-compose.yml: Changed LLM_URL to tensorrt-llm:8000 for telegram and discord services
   - ✅ Removed inference-api from depends_on (TensorRT-LLM will be in home_infra/shared-network)
   - ✅ Added legacy profile to inference-api service to disable by default
   - ✅ Updated AGENTS.md to reflect TensorRT-LLM as current implementation
   - ✅ Updated README.md to reference TensorRT-LLM setup and usage
   - ⏳ **Remaining:** Fully remove inference-api service from docker-compose.yml (waiting for TensorRT-LLM setup and verification in home_infra)

4. **Get Qwen3-30B-A3B-Thinking-2507 running:** ⏳ TODO (requires TensorRT-LLM container setup from task 1, model loading API from task 2, and model compilation/preparation)
   - **Model Repository Setup:** ✅ Helper command created
     - ✅ Created `essence/commands/setup_triton_repository.py` command for repository management
     - ✅ Supports creating model directory structure: `poetry run -m essence setup-triton-repository --action create --model <name>`
     - ✅ Supports validating model structure: `poetry run -m essence setup-triton-repository --action validate --model <name>`
     - ✅ Supports listing models in repository: `poetry run -m essence setup-triton-repository --action list`
     - ✅ Creates README.md with instructions for each model directory
     - ⏳ **Remaining:** Create actual model repository structure and place compiled files
     - Each model needs: compiled TensorRT-LLM engine files, config.pbtxt, tokenizer files
   - **Model Compilation:**
     - Compile Qwen3-30B-A3B-Thinking-2507 using TensorRT-LLM build tools
     - Configure quantization (8-bit as specified in environment variables)
     - Set max context length (131072 tokens)
     - Place compiled model in repository structure
   - **Model Loading:**
     - Use `manage-tensorrt-llm` command to load model: `poetry run -m essence manage-tensorrt-llm --action load --model <name>`
     - Verify model appears in repository index
   - **Verification:**
     - Verify GPU usage (must use GPU, CPU fallback FORBIDDEN)
     - Test model inference via gRPC interface (tensorrt-llm:8000)
     - Verify quantization and memory usage
     - Check model status: `poetry run -m essence manage-tensorrt-llm --action status --model <name>`

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

**Status:** Benchmark evaluation framework already complete (Phase 10 ✅). Remaining tasks are operational (running evaluations, analyzing results).

**Note:** The benchmark evaluation framework was completed in Phase 10:
- ✅ `essence/agents/evaluator.py` - BenchmarkEvaluator class implemented
- ✅ `essence/agents/dataset_loader.py` - Dataset loaders (HumanEval, MBPP)
- ✅ `essence/commands/run_benchmarks.py` - Benchmark runner command
- ✅ Sandbox isolation with full activity logging
- ✅ Efficiency metrics capture

**Tasks:**
1. **Run benchmark evaluations (framework ready):**
   - Execute benchmarks with Qwen3 model (via TensorRT-LLM once Phase 15 is complete)
   - Framework supports: HumanEval, MBPP (SWE-bench, CodeXGLUE can be added if needed)
   - Sandbox execution environment already implemented

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
