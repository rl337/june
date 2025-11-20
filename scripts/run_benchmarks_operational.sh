#!/bin/bash
# Operational workflow script for Phase 18: Model Evaluation and Benchmarking
#
# This script orchestrates the operational tasks for running benchmark evaluations:
# 1. Pre-flight environment check
# 2. LLM service verification (TensorRT-LLM, NIM, or legacy inference-api)
# 3. Benchmark configuration
# 4. Run benchmarks
# 5. Results analysis guidance
#
# Usage:
#   ./scripts/run_benchmarks_operational.sh [--skip-check] [--skip-verify] [--llm-url URL] [--dataset DATASET] [--max-tasks N] [--num-attempts N]
#
# Options:
#   --skip-check      Skip pre-flight environment check
#   --skip-verify     Skip LLM service verification
#   --llm-url URL     LLM service URL (default: tensorrt-llm:8000 for TensorRT-LLM, can use nim-qwen3:8001 for NIM, inference-api:50051 for legacy)
#   --dataset DATASET Dataset to evaluate (humaneval, mbpp, all) [default: humaneval]
#   --max-tasks N     Maximum number of tasks to evaluate [default: all]
#   --num-attempts N  Number of attempts per task for pass@k calculation [default: 1]
#   --output-dir DIR  Output directory for results [default: /tmp/benchmarks/results]
#   --run-now         Run benchmarks immediately after verification (default: show guidance only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SKIP_CHECK=false
SKIP_VERIFY=false
LLM_URL="${LLM_URL:-tensorrt-llm:8000}"
DATASET="${DATASET:-humaneval}"
MAX_TASKS="${MAX_TASKS:-}"
NUM_ATTEMPTS="${NUM_ATTEMPTS:-1}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/benchmarks/results}"
RUN_NOW=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-check)
            SKIP_CHECK=true
            shift
            ;;
        --skip-verify)
            SKIP_VERIFY=true
            shift
            ;;
        --llm-url)
            LLM_URL="$2"
            shift 2
            ;;
        --dataset)
            DATASET="$2"
            shift 2
            ;;
        --max-tasks)
            MAX_TASKS="$2"
            shift 2
            ;;
        --num-attempts)
            NUM_ATTEMPTS="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --run-now)
            RUN_NOW=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-check] [--skip-verify] [--llm-url URL] [--dataset DATASET] [--max-tasks N] [--num-attempts N] [--output-dir DIR] [--run-now]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Benchmark Evaluation - Operational Workflow"
echo "=========================================="
echo ""

# Step 1: Pre-flight environment check
if [ "$SKIP_CHECK" = false ]; then
    echo "Step 1: Pre-flight environment check..."
    echo "----------------------------------------"
    if ! poetry run python -m essence check-environment; then
        echo ""
        echo "❌ Environment check failed. Please fix the issues above before proceeding."
        echo "   Run: poetry run python -m essence check-environment --verbose"
        exit 1
    fi
    echo ""
else
    echo "Step 1: Skipping pre-flight check (--skip-check)"
    echo ""
fi

# Step 2: LLM service verification
if [ "$SKIP_VERIFY" = false ]; then
    echo "Step 2: LLM service verification..."
    echo "----------------------------------------"
    
    # Determine service type from URL
    if [[ "$LLM_URL" == *"tensorrt-llm"* ]] || [[ "$LLM_URL" == *":8000"* ]]; then
        SERVICE_TYPE="TensorRT-LLM"
        echo "Checking TensorRT-LLM service..."
        echo ""
        
        if poetry run python -m essence verify-tensorrt-llm 2>&1 | grep -q "✅"; then
            echo "✅ TensorRT-LLM service is accessible"
            
            # Check model status
            echo "Checking model status..."
            if poetry run python -m essence manage-tensorrt-llm --action status --model qwen3-30b 2>&1 | grep -q "READY"; then
                echo "✅ Model is loaded and ready"
            else
                echo "⚠️  Model is not loaded or not ready"
                echo ""
                echo "Load the model with:"
                echo "  poetry run python -m essence manage-tensorrt-llm --action load --model qwen3-30b"
                echo ""
                read -p "Continue anyway? (y/N): " -n 1 -r
                echo ""
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    exit 0
                fi
            fi
        else
            echo "❌ TensorRT-LLM service is not accessible"
            echo ""
            echo "Start the service in home_infra:"
            echo "  cd /home/rlee/dev/home_infra"
            echo "  docker compose up -d tensorrt-llm"
            echo ""
            echo "Verify service:"
            echo "  poetry run python -m essence verify-tensorrt-llm"
            echo ""
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 0
            fi
        fi
        
    elif [[ "$LLM_URL" == *"nim-qwen3"* ]] || [[ "$LLM_URL" == *":8001"* ]]; then
        SERVICE_TYPE="NVIDIA NIM"
        echo "Checking NVIDIA NIM service..."
        echo ""
        
        # Extract host and ports from URL
        NIM_HOST="nim-qwen3"
        NIM_HTTP_PORT="8003"
        NIM_GRPC_PORT="8001"
        
        if poetry run python -m essence verify-nim --nim-host "$NIM_HOST" --http-port "$NIM_HTTP_PORT" --grpc-port "$NIM_GRPC_PORT" 2>&1 | grep -q "✅"; then
            echo "✅ NVIDIA NIM service is accessible"
        else
            echo "❌ NVIDIA NIM service is not accessible"
            echo ""
            echo "Start the service in home_infra:"
            echo "  cd /home/rlee/dev/home_infra"
            echo "  docker compose up -d nim-qwen3"
            echo ""
            echo "Verify service:"
            echo "  poetry run python -m essence verify-nim --nim-host $NIM_HOST --http-port $NIM_HTTP_PORT --grpc-port $NIM_GRPC_PORT"
            echo ""
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 0
            fi
        fi
        
    elif [[ "$LLM_URL" == *"inference-api"* ]] || [[ "$LLM_URL" == *":50051"* ]]; then
        SERVICE_TYPE="Legacy Inference-API"
        echo "Checking legacy inference-api service..."
        echo ""
        echo "⚠️  Using legacy inference-api service (deprecated)"
        echo "   Consider migrating to TensorRT-LLM or NVIDIA NIM"
        echo ""
        
        # Check if service is running
        if docker compose ps inference-api 2>&1 | grep -q "Up"; then
            echo "✅ Legacy inference-api service is running"
        else
            echo "❌ Legacy inference-api service is not running"
            echo ""
            echo "Start the service:"
            echo "  docker compose --profile legacy up -d inference-api"
            echo ""
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 0
            fi
        fi
    else
        echo "⚠️  Unknown LLM service URL: $LLM_URL"
        echo "   Assuming service is accessible"
    fi
    
    echo ""
else
    echo "Step 2: Skipping LLM service verification (--skip-verify)"
    echo ""
fi

# Step 3: Benchmark configuration
echo "Step 3: Benchmark configuration..."
echo "----------------------------------------"
echo "Configuration:"
echo "  LLM Service: $SERVICE_TYPE ($LLM_URL)"
echo "  Dataset: $DATASET"
if [ -n "$MAX_TASKS" ]; then
    echo "  Max Tasks: $MAX_TASKS"
else
    echo "  Max Tasks: All tasks in dataset"
fi
echo "  Num Attempts: $NUM_ATTEMPTS (for pass@k calculation)"
echo "  Output Directory: $OUTPUT_DIR"
echo ""

# Step 4: Run benchmarks
if [ "$RUN_NOW" = true ]; then
    echo "Step 4: Running benchmarks..."
    echo "----------------------------------------"
    echo ""
    
    # Build command arguments
    ARGS=(
        --dataset "$DATASET"
        --output-dir "$OUTPUT_DIR"
        --llm-url "$LLM_URL"
        --num-attempts "$NUM_ATTEMPTS"
    )
    
    if [ -n "$MAX_TASKS" ]; then
        ARGS+=(--max-tasks "$MAX_TASKS")
    fi
    
    echo "Running benchmarks with command:"
    echo "  poetry run python -m essence run-benchmarks ${ARGS[*]}"
    echo ""
    
    # Run benchmarks
    poetry run python -m essence run-benchmarks "${ARGS[@]}"
    
    echo ""
    echo "✅ Benchmarks completed!"
    echo ""
    echo "Results are available in: $OUTPUT_DIR"
    echo ""
else
    echo "Step 4: Benchmark execution guidance..."
    echo "----------------------------------------"
    echo ""
    echo "To run benchmarks, use one of the following methods:"
    echo ""
    echo "Method 1: Use this script with --run-now flag"
    echo "  ./scripts/run_benchmarks_operational.sh --run-now --llm-url $LLM_URL --dataset $DATASET"
    if [ -n "$MAX_TASKS" ]; then
        echo "    --max-tasks $MAX_TASKS"
    fi
    echo "    --num-attempts $NUM_ATTEMPTS --output-dir $OUTPUT_DIR"
    echo ""
    echo "Method 2: Use the run-benchmarks command directly"
    echo "  poetry run python -m essence run-benchmarks \\"
    echo "    --dataset $DATASET \\"
    echo "    --llm-url $LLM_URL \\"
    echo "    --num-attempts $NUM_ATTEMPTS \\"
    echo "    --output-dir $OUTPUT_DIR"
    if [ -n "$MAX_TASKS" ]; then
        echo "    --max-tasks $MAX_TASKS"
    fi
    echo ""
    echo "Method 3: Use the run_benchmarks.sh wrapper script"
    echo "  ./scripts/run_benchmarks.sh \\"
    echo "    --dataset $DATASET \\"
    echo "    --llm-url $LLM_URL \\"
    echo "    --num-attempts $NUM_ATTEMPTS \\"
    echo "    --output-dir $OUTPUT_DIR"
    if [ -n "$MAX_TASKS" ]; then
        echo "    --max-tasks $MAX_TASKS"
    fi
    echo ""
fi

# Step 5: Results analysis guidance
echo "Step 5: Results analysis..."
echo "----------------------------------------"
echo ""
echo "After benchmarks complete, analyze results:"
echo ""
echo "1. View results summary:"
echo "   cat $OUTPUT_DIR/summary.json"
echo ""
echo "2. Review detailed results:"
echo "   cat $OUTPUT_DIR/results.json"
echo ""
echo "3. Check sandbox snapshots (if enabled):"
echo "   ls -la $OUTPUT_DIR/snapshots/"
echo ""
echo "4. Review sandbox activity logs:"
echo "   poetry run python -m essence review-sandbox --snapshot-dir $OUTPUT_DIR/snapshots/<task-id>"
echo ""
echo "5. Analyze metrics:"
echo "   - Pass@k scores (correctness)"
echo "   - Execution time (efficiency)"
echo "   - Solution quality (code quality metrics)"
echo "   - Resource usage (memory, CPU)"
echo ""

echo "=========================================="
echo "Workflow complete!"
echo "=========================================="
echo ""
echo "Next steps:"
if [ "$RUN_NOW" = false ]; then
    echo "1. Run benchmarks (see Step 4 above)"
    echo "2. Analyze results (see Step 5 above)"
else
    echo "1. Analyze results (see Step 5 above)"
fi
echo "2. Document findings"
echo "3. Use insights to improve agentic flow"
echo ""
echo "For detailed instructions, see:"
echo "  - docs/guides/QWEN3_BENCHMARK_EVALUATION.md"
echo "  - REFACTOR_PLAN.md (Phase 18)"
echo ""
