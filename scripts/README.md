# Scripts Directory

This directory contains **shell scripts for infrastructure and automation only**.

## Purpose

The `scripts/` directory is for:
- **Shell scripts** that help with passing complex options to container runs or other tools
- **Infrastructure/automation scripts** (not reusable tools)
- Examples: `setup_docker.sh`, `refactor_agent_loop.sh`, `run_all_checks.sh`

## What Goes Where

### Scripts (`scripts/`)
- Shell scripts for infrastructure/automation
- Complex container operations
- Build and deployment scripts

### Commands (`essence/commands/`)
- **All reusable Python tools** that users/agents might run
- Run via: `poetry run python -m essence <command-name>`
- Examples: `download-models`, `monitor-gpu`, `review-sandbox`, `benchmark-qwen3`, `verify-qwen3`

### Tests (`tests/`)
- All test code, runnable via pytest
- Test utilities should be in `tests/` or `tests/scripts/`

## Available Commands

Reusable tools have been migrated to commands. Use these instead of scripts:

- **`poetry run python -m essence download-models`** - Download models (replaces `scripts/download_models.py`)
- **`poetry run python -m essence monitor-gpu`** - Monitor GPU metrics (replaces `scripts/monitor_gpu.py`)
- **`poetry run python -m essence review-sandbox`** - Review sandbox snapshots (replaces `scripts/review_sandbox.py`)
- **`poetry run python -m essence verify-qwen3`** - Verify Qwen3 quantization (replaces `scripts/verify_qwen3_quantization.py`)
- **`poetry run python -m essence benchmark-qwen3`** - Benchmark Qwen3 performance (replaces `scripts/benchmark_qwen3_performance.py`)
- **`poetry run python -m essence run-benchmarks`** - Run benchmark evaluations with sandboxed execution (replaces `scripts/run_benchmarks.py`)
- **`poetry run python -m essence generate-alice-dataset`** - Generate Alice's Adventures in Wonderland dataset (replaces `scripts/generate_alice_dataset.py`)

## Remaining Scripts

### Infrastructure Scripts (Keep)
- `setup_docker.sh` - Docker setup
- `setup_docker_permissions.sh` - Docker permissions setup
- `refactor_agent_loop.sh` - Agent loop automation
- `run_all_checks.sh` - Run all checks
- `run_benchmarks.sh` - Benchmark automation wrapper
- `review_sandbox.sh` - Shell wrapper for review_sandbox command
- `deploy_audio_services.sh` - Audio services deployment
- `setup_qwen3_operational.sh` - Operational workflow for Phase 10.1-10.2 (Qwen3 model setup on GPU)
- `setup_nim_operational.sh` - Operational workflow for Phase 15 (NVIDIA NIM setup)
- `setup_phase19_operational.sh` - Operational workflow for Phase 19 (Direct Agent-User Communication)
- `verify_nim_compatibility.sh` - Helper script for Phase 19 NIM ARM64/DGX Spark compatibility verification
- `generate_nim_compose_snippet.sh` - Generates docker-compose.yml service snippets for Riva ASR/TTS NIMs
- `run_benchmarks_operational.sh` - Operational workflow for Phase 18 (Model evaluation and benchmarking)
- `run_performance_tests_operational.sh` - Operational workflow for Phase 16 Task 5 (Performance testing)

### Test Utilities (Should Move to tests/)
- `test_phase21_round_trip.py` - Automated test script for Phase 21 USER_MESSAGES.md round trip verification
- `test_*.py` files - Should be moved to `tests/scripts/` or converted to pytest
- `run_audio_tests.sh` - Should be moved to `tests/scripts/` or converted to pytest
- `test_artifact_collection.sh` - Should be moved to `tests/scripts/` or converted to pytest

### Dataset/Data Scripts
- All dataset generation tools have been converted to commands (see Available Commands above)

## Guidelines

1. **New reusable tools** → Create as `essence/commands/<command_name>.py`
2. **New test utilities** → Create in `tests/scripts/` or as pytest tests
3. **New infrastructure scripts** → Create in `scripts/` (shell scripts only)
4. **Never add Python tools to scripts/** → Use commands instead
