#!/bin/bash
# Run Benchmark Evaluations
#
# Orchestrates benchmark evaluation with sandboxed execution.
# All operations run in containers - no host system pollution.
#
# Usage:
#   ./scripts/run_benchmarks.sh [--dataset DATASET] [--max-tasks N] [--output-dir DIR]
#
# Examples:
#   ./scripts/run_benchmarks.sh --dataset humaneval --max-tasks 10
#   ./scripts/run_benchmarks.sh --dataset all --output-dir /tmp/my_results

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
DATASET="${DATASET:-humaneval}"
MAX_TASKS="${MAX_TASKS:-}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/benchmarks/results}"
INFERENCE_API_URL="${INFERENCE_API_URL:-inference-api:50051}"
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3-30B-A3B-Thinking-2507}"
SANDBOX_IMAGE="${SANDBOX_IMAGE:-python:3.11-slim}"
SANDBOX_MEMORY="${SANDBOX_MEMORY:-4g}"
SANDBOX_CPU="${SANDBOX_CPU:-2.0}"
TIMEOUT="${TIMEOUT:-300}"
MAX_ITERATIONS="${MAX_ITERATIONS:-10}"
ENABLE_NETWORK="${ENABLE_NETWORK:-false}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dataset)
            DATASET="$2"
            shift 2
            ;;
        --max-tasks)
            MAX_TASKS="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --inference-api-url)
            INFERENCE_API_URL="$2"
            shift 2
            ;;
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --sandbox-image)
            SANDBOX_IMAGE="$2"
            shift 2
            ;;
        --sandbox-memory)
            SANDBOX_MEMORY="$2"
            shift 2
            ;;
        --sandbox-cpu)
            SANDBOX_CPU="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --max-iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        --enable-network)
            ENABLE_NETWORK="true"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dataset DATASET          Dataset to evaluate (humaneval, mbpp, all) [default: humaneval]"
            echo "  --max-tasks N              Maximum number of tasks to evaluate [default: all]"
            echo "  --output-dir DIR           Output directory for results [default: /tmp/benchmarks/results]"
            echo "  --inference-api-url URL    gRPC endpoint for inference API [default: inference-api:50051]"
            echo "  --model-name NAME          Model name to evaluate [default: Qwen/Qwen3-30B-A3B-Thinking-2507]"
            echo "  --sandbox-image IMAGE      Docker base image for sandboxes [default: python:3.11-slim]"
            echo "  --sandbox-memory MEM       Maximum memory for sandboxes [default: 4g]"
            echo "  --sandbox-cpu CPU          Maximum CPU for sandboxes [default: 2.0]"
            echo "  --timeout SECONDS          Maximum time per task [default: 300]"
            echo "  --max-iterations N         Maximum agent iterations per task [default: 10]"
            echo "  --enable-network           Enable network access in sandboxes [default: disabled]"
            echo "  --help, -h                 Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build command arguments
ARGS=(
    --dataset "$DATASET"
    --output-dir "$OUTPUT_DIR"
    --inference-api-url "$INFERENCE_API_URL"
    --model-name "$MODEL_NAME"
    --sandbox-image "$SANDBOX_IMAGE"
    --sandbox-memory "$SANDBOX_MEMORY"
    --sandbox-cpu "$SANDBOX_CPU"
    --timeout "$TIMEOUT"
    --max-iterations "$MAX_ITERATIONS"
)

if [[ -n "$MAX_TASKS" ]]; then
    ARGS+=(--max-tasks "$MAX_TASKS")
fi

if [[ "$ENABLE_NETWORK" == "true" ]]; then
    ARGS+=(--enable-network)
fi

# Check if running in container or on host
if [[ -f /.dockerenv ]] || [[ -n "${DOCKER_CONTAINER:-}" ]]; then
    # Running in container - use Python directly
    echo "Running benchmarks in container..."
    cd "$PROJECT_ROOT"
    poetry run python scripts/run_benchmarks.py "${ARGS[@]}"
else
    # Running on host - use docker compose
    echo "Running benchmarks via docker compose..."
    cd "$PROJECT_ROOT"
    
    # Ensure inference-api is running
    if ! docker compose ps inference-api | grep -q "Up"; then
        echo "Starting inference-api service..."
        docker compose up -d inference-api
        echo "Waiting for inference-api to be ready..."
        sleep 10
    fi
    
    # Run benchmark script in cli-tools container
    docker compose run --rm \
        -v "$PROJECT_ROOT:/workspace" \
        -v "$OUTPUT_DIR:$OUTPUT_DIR" \
        -e DATASET="$DATASET" \
        -e MAX_TASKS="$MAX_TASKS" \
        -e OUTPUT_DIR="$OUTPUT_DIR" \
        -e INFERENCE_API_URL="$INFERENCE_API_URL" \
        -e MODEL_NAME="$MODEL_NAME" \
        -e SANDBOX_IMAGE="$SANDBOX_IMAGE" \
        -e SANDBOX_MEMORY="$SANDBOX_MEMORY" \
        -e SANDBOX_CPU="$SANDBOX_CPU" \
        -e TIMEOUT="$TIMEOUT" \
        -e MAX_ITERATIONS="$MAX_ITERATIONS" \
        -e ENABLE_NETWORK="$ENABLE_NETWORK" \
        cli-tools \
        bash -c "cd /workspace && poetry run python scripts/run_benchmarks.py ${ARGS[*]}"
fi

echo "Benchmark evaluation completed!"
echo "Results saved to: $OUTPUT_DIR"
