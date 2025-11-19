# Qwen3 Benchmark Evaluation Guide

This guide explains how to set up and run benchmark evaluations for the Qwen3-30B-A3B-Thinking-2507 model using the June benchmark evaluation framework.

## Overview

The benchmark evaluation system provides:
- **Sandboxed execution** - Each task runs in an isolated Docker container
- **Full activity logging** - All commands, file operations, and resource usage are captured
- **Efficiency metrics** - Tracks not just correctness but also problem-solving efficiency
- **Reviewable snapshots** - Complete sandbox state persists for post-hoc analysis
- **Accurate pass@k calculation** - Supports multiple attempts per task for proper pass@k metrics (pass@1, pass@5, pass@10, pass@100)

## Prerequisites

1. **Qwen3 model loaded** - TensorRT-LLM service must be running in home_infra with Qwen3-30B-A3B-Thinking-2507 loaded (or legacy inference-api service)
2. **Docker** - For sandbox container creation
3. **Docker Compose** - For orchestrating services
4. **Sufficient resources**:
   - GPU: 20GB+ VRAM (for Qwen3-30B with quantization)
   - CPU: 4+ cores recommended
   - RAM: 32GB+ recommended
   - Disk: 10GB+ for datasets and results

## Quick Start

### 1. Start TensorRT-LLM Service (Recommended)

Ensure TensorRT-LLM is running in home_infra with the Qwen3 model loaded:

```bash
# Start TensorRT-LLM service (in home_infra)
cd /home/rlee/dev/home_infra
docker compose up -d tensorrt-llm

# Check if model is loaded
poetry run -m essence manage-tensorrt-llm --action status --model qwen3-30b

# Verify TensorRT-LLM is accessible
poetry run -m essence verify-tensorrt-llm
```

**Alternative: Legacy Inference API**

If using the legacy inference-api service:

```bash
# Start inference-api service (legacy)
docker compose --profile legacy up -d inference-api

# Check if model is loaded (wait for "Model loaded successfully" in logs)
docker compose logs -f inference-api
```

### 2. Run Benchmark Evaluation

Run a small evaluation to test the setup:

```bash
# Run HumanEval with first 5 tasks (recommended - uses command pattern)
poetry run -m essence run-benchmarks --dataset humaneval --max-tasks 5

# Alternative: Use shell script wrapper
./scripts/run_benchmarks.sh --dataset humaneval --max-tasks 5
```

### 3. Review Results

Results are saved to `/tmp/benchmarks/results` by default. Review a specific task:

```bash
# Review a specific sandbox snapshot
./scripts/review_sandbox.sh /tmp/benchmarks/results/sandboxes/humaneval_0_snapshot

# Or use Python tool
poetry run python scripts/review_sandbox.py /tmp/benchmarks/results humaneval_0
```

## Configuration

### Command-Line Options

The `run-benchmarks` command supports various configuration options:

```bash
poetry run -m essence run-benchmarks \
  --dataset humaneval \          # Dataset: humaneval, mbpp, or all
  --max-tasks 10 \               # Limit number of tasks (default: all)
  --output-dir /path/to/results \ # Output directory
  --llm-url tensorrt-llm:8000 \  # gRPC endpoint (default: tensorrt-llm:8000 for TensorRT-LLM)
  --model-name Qwen/Qwen3-30B-A3B-Thinking-2507 \  # Model name
  --sandbox-image python:3.11-slim \  # Sandbox base image
  --sandbox-memory 4g \          # Max memory per sandbox
  --sandbox-cpu 2.0 \            # Max CPU per sandbox
  --timeout 300 \                 # Max time per task (seconds)
  --max-iterations 10 \           # Max agent iterations per task
  --num-attempts 5 \              # Number of attempts per task for pass@k calculation (default: 1)
  --enable-network                # Enable network access in sandboxes
```

**Note:** The default `--llm-url` is `tensorrt-llm:8000` for TensorRT-LLM. Use `inference-api:50051` for the legacy service or `nim-qwen3:8001` for NVIDIA NIM.

### Environment Variables

You can also set these via environment variables:

```bash
export DATASET=humaneval
export MAX_TASKS=10
export OUTPUT_DIR=/tmp/my_benchmarks
export LLM_URL=tensorrt-llm:8000  # Default: tensorrt-llm:8000 (use inference-api:50051 for legacy, nim-qwen3:8001 for NVIDIA NIM)
export MODEL_NAME="Qwen/Qwen3-30B-A3B-Thinking-2507"
export SANDBOX_IMAGE=python:3.11-slim
export SANDBOX_MEMORY=4g
export SANDBOX_CPU=2.0
export TIMEOUT=300
export MAX_ITERATIONS=10
export BENCHMARK_NUM_ATTEMPTS=5  # Number of attempts per task for pass@k calculation (default: 1)
export ENABLE_NETWORK=false

poetry run -m essence run-benchmarks
```

**Note:** The command also accepts `INFERENCE_API_URL` for backward compatibility, but `LLM_URL` is preferred.

### Pass@k Calculation

The benchmark evaluator supports accurate pass@k calculation when multiple attempts per task are configured:

- **pass@1**: Always accurate (single attempt per task)
- **pass@5, pass@10, pass@100**: Accurate when `--num-attempts >= k`

**Example: Calculate pass@5 accurately:**

```bash
# Run with 5 attempts per task to get accurate pass@5
poetry run -m essence run-benchmarks \
  --dataset humaneval \
  --max-tasks 10 \
  --num-attempts 5

# This will calculate:
# - pass@1: Accurate (checks first attempt)
# - pass@5: Accurate (checks if at least one of first 5 attempts passed)
# - pass@10: Uses pass@5 as best estimate (only 5 attempts available)
# - pass@100: Uses pass@5 as best estimate (only 5 attempts available)
```

**Note:** Each attempt uses different random seeds/sampling parameters, so results may vary between attempts. The evaluator groups results by task and calculates pass@k as: (# tasks with at least one passing attempt in first k attempts) / total_tasks.

## Supported Datasets

### HumanEval

Python coding problems (164 problems total).

```bash
# Download and evaluate all HumanEval tasks (recommended - uses command pattern)
poetry run -m essence run-benchmarks --dataset humaneval

# Evaluate first 10 tasks
poetry run -m essence run-benchmarks --dataset humaneval --max-tasks 10

# Alternative: Use shell script wrapper
./scripts/run_benchmarks.sh --dataset humaneval --max-tasks 10
```

The dataset is automatically downloaded from GitHub on first use.

### MBPP (Mostly Basic Python Problems)

974 Python coding problems.

```bash
# Note: MBPP requires manual download or HuggingFace dataset
# See dataset_loader.py for instructions
poetry run -m essence run-benchmarks --dataset mbpp

# Alternative: Use shell script wrapper
./scripts/run_benchmarks.sh --dataset mbpp
```

### All Datasets

Run evaluation on all supported datasets:

```bash
poetry run -m essence run-benchmarks --dataset all

# Alternative: Use shell script wrapper
./scripts/run_benchmarks.sh --dataset all
```

## Understanding Results

### Evaluation Report

After evaluation completes, you'll find:

```
/tmp/benchmarks/results/
├── humaneval/
│   ├── evaluation_report.json      # Summary report
│   ├── humaneval_0_result.json     # Individual task results
│   ├── humaneval_1_result.json
│   └── sandboxes/
│       ├── humaneval_0_snapshot/   # Sandbox snapshots
│       └── humaneval_1_snapshot/
└── combined_report.json             # Combined report (if multiple datasets)
```

### Report Format

The evaluation report (`evaluation_report.json`) contains:

```json
{
  "dataset": "humaneval",
  "model_name": "Qwen/Qwen3-30B-A3B-Thinking-2507",
  "timestamp": "2024-01-01T00:00:00",
  "total_tasks": 164,
  "successful_tasks": 150,
  "passed_tests": 120,
  "pass_at_1": 0.73,
  "pass_at_k": {
    "1": 0.73,
    "5": 0.73,
    "10": 0.73,
    "100": 0.73
  },
  "average_execution_time": 45.2,
  "average_iterations": 2.1,
  "average_commands": 8.5,
  "average_tokens": 450,
  "efficiency_score": 0.65,
  "task_results": [...]
}
```

### Metrics Explained

- **pass_at_1**: Percentage of tasks that passed tests on first attempt
- **pass_at_k**: Pass rate with k attempts. For accurate pass@k calculation (k > 1), use `--num-attempts k` when running benchmarks. With `--num-attempts 1` (default), only pass@1 is accurate; pass@5, pass@10, and pass@100 use pass@1 as a placeholder.
- **average_execution_time**: Average time to solve a task (seconds)
- **average_iterations**: Average number of agent iterations per task
- **average_commands**: Average number of shell commands executed
- **average_tokens**: Average number of tokens generated
- **efficiency_score**: Composite metric (0-1) combining correctness and resource efficiency

## Reviewing Sandbox Snapshots

### Using Review Tools

Review what the agent did to solve a specific task:

```bash
# Review by snapshot directory
./scripts/review_sandbox.sh /tmp/benchmarks/results/sandboxes/humaneval_0_snapshot

# Review by output dir + task ID
./scripts/review_sandbox.sh /tmp/benchmarks/results humaneval_0

# JSON output for programmatic access
poetry run python scripts/review_sandbox.py /tmp/benchmarks/results humaneval_0 --json
```

### Review Output

The review tool shows:
- **Metadata**: Task ID, container name, workspace directory
- **Metrics**: Commands executed, files created, duration, memory, CPU usage
- **Command Timeline**: All commands run with timestamps, return codes, stdout/stderr
- **File System Tree**: Files created/modified in the sandbox
- **Efficiency Metrics**: Commands per second, files per second, time per command/iteration

## Troubleshooting

### TensorRT-LLM Not Ready

If you see errors about TensorRT-LLM not being available:

```bash
# Check if TensorRT-LLM is running (in home_infra)
cd /home/rlee/dev/home_infra
docker compose ps tensorrt-llm

# Check model status
poetry run -m essence manage-tensorrt-llm --action status --model qwen3-30b

# Verify TensorRT-LLM setup
poetry run -m essence verify-tensorrt-llm

# Check logs
docker compose logs tensorrt-llm | grep -i "model\|error"
```

**Legacy Inference API:**

If using the legacy inference-api service:

```bash
# Check if inference-api is running
docker compose ps inference-api

# Check logs for model loading status
docker compose logs inference-api | grep -i "model\|error"

# Restart inference-api if needed
docker compose restart inference-api
```

### Sandbox Creation Fails

If sandbox containers fail to create:

```bash
# Check Docker is running
docker ps

# Check available resources
docker stats

# Increase sandbox memory limit if needed
poetry run -m essence run-benchmarks --dataset humaneval --sandbox-memory 8g

# Alternative: Use shell script wrapper
./scripts/run_benchmarks.sh --sandbox-memory 8g
```

### Dataset Download Fails

If dataset download fails:

```bash
# HumanEval: Check internet connection
# The script downloads from GitHub

# MBPP: Manual download required
# See essence/agents/dataset_loader.py for instructions
```

### Out of Memory

If you see OOM errors:

```bash
# Reduce sandbox memory
poetry run -m essence run-benchmarks --dataset humaneval --sandbox-memory 2g

# Reduce max tasks
poetry run -m essence run-benchmarks --dataset humaneval --max-tasks 5

# Alternative: Use shell script wrapper
./scripts/run_benchmarks.sh --sandbox-memory 2g --max-tasks 5

# Check GPU memory
nvidia-smi
```

## Advanced Usage

### Running in Container

Run benchmarks in the cli-tools container:

```bash
# Run benchmarks in cli-tools container
docker compose run --rm cli-tools \
  poetry run -m essence run-benchmarks --dataset humaneval --max-tasks 10

# Or enter container interactively
docker compose exec cli-tools bash
cd /workspace
poetry run -m essence run-benchmarks --dataset humaneval --max-tasks 10
```

### Custom Sandbox Image

Use a custom base image for sandboxes:

```bash
poetry run -m essence run-benchmarks \
  --dataset humaneval \
  --sandbox-image python:3.12-slim

# Alternative: Use shell script wrapper
./scripts/run_benchmarks.sh --sandbox-image python:3.12-slim
```

### Network Access in Sandboxes

Enable network access for tasks that need internet:

```bash
poetry run -m essence run-benchmarks --dataset humaneval --enable-network

# Alternative: Use shell script wrapper
./scripts/run_benchmarks.sh --enable-network
```

**Warning**: Network access reduces isolation. Only enable if necessary.

### Long-Running Evaluations

For full dataset evaluations, consider running in background:

```bash
# Run in background with logging
# Run in background (recommended - uses command pattern)
nohup poetry run -m essence run-benchmarks --dataset humaneval > benchmark.log 2>&1 &

# Alternative: Use shell script wrapper
nohup ./scripts/run_benchmarks.sh --dataset humaneval > benchmark.log 2>&1 &

# Monitor progress
tail -f benchmark.log

# Check results when complete
ls -lh /tmp/benchmarks/results/humaneval/
```

## Best Practices

1. **Start Small**: Test with `--max-tasks 5` before running full datasets
2. **Monitor Resources**: Watch GPU/CPU/memory usage during evaluation
3. **Review Snapshots**: Use review tools to understand agent behavior
4. **Save Results**: Keep evaluation reports for comparison
5. **Iterate**: Adjust timeout, iterations, and resources based on results

## Next Steps

- Compare results with published baselines
- Analyze efficiency metrics to optimize agent behavior
- Review sandbox snapshots to understand problem-solving patterns
- Experiment with different model parameters and configurations
