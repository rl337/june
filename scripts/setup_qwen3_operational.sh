#!/bin/bash
# Operational workflow script for Phase 10.1-10.2: Qwen3 Model Setup on GPU
#
# This script orchestrates the operational tasks for setting up Qwen3 model:
# 1. Pre-flight environment check
# 2. Model download (if needed)
# 3. Service startup guidance
# 4. Verification steps
#
# Usage:
#   ./scripts/setup_qwen3_operational.sh [--skip-check] [--skip-download] [--use-legacy]
#
# Options:
#   --skip-check      Skip pre-flight environment check
#   --skip-download   Skip model download (assumes model already downloaded)
#   --use-legacy      Use legacy inference-api service instead of TensorRT-LLM

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SKIP_CHECK=false
SKIP_DOWNLOAD=false
USE_LEGACY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-check)
            SKIP_CHECK=true
            shift
            ;;
        --skip-download)
            SKIP_DOWNLOAD=true
            shift
            ;;
        --use-legacy)
            USE_LEGACY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-check] [--skip-download] [--use-legacy]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Qwen3 Model Setup - Operational Workflow"
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

# Step 2: Check if model is already downloaded
if [ "$SKIP_DOWNLOAD" = false ]; then
    echo "Step 2: Checking model download status..."
    echo "----------------------------------------"
    if poetry run python -m essence download-models --status 2>&1 | grep "Qwen/Qwen3-30B-A3B-Thinking-2507" | grep -q "✓ CACHED"; then
        echo "✅ Model already downloaded"
        echo ""
    else
        echo "Model not found. Starting download..."
        echo "This may take a significant amount of time (model is ~60GB)."
        echo ""
        read -p "Continue with download? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Download cancelled. Use --skip-download to skip this step."
            exit 0
        fi
        
        echo "Downloading model in container..."
        docker compose run --rm cli-tools \
            poetry run python -m essence download-models --model Qwen/Qwen3-30B-A3B-Thinking-2507
        
        echo ""
        echo "✅ Model download complete"
        echo ""
    fi
else
    echo "Step 2: Skipping model download (--skip-download)"
    echo ""
fi

# Step 3: Service startup guidance
echo "Step 3: Service startup..."
echo "----------------------------------------"
if [ "$USE_LEGACY" = true ]; then
    echo "Using legacy inference-api service..."
    echo ""
    echo "Starting inference-api service:"
    echo "  docker compose --profile legacy up -d inference-api"
    echo ""
    echo "Check service logs:"
    echo "  docker compose logs -f inference-api"
    echo ""
    echo "Verify service is running:"
    echo "  poetry run python -m essence verify-qwen3 --inference-api-url inference-api:50051"
    SERVICE_URL="inference-api:50051"
else
    echo "Using TensorRT-LLM service (default)..."
    echo ""
    echo "TensorRT-LLM should be running in home_infra/shared-network."
    echo "If not already running, start it in home_infra:"
    echo "  cd /home/rlee/dev/home_infra"
    echo "  docker compose up -d tensorrt-llm"
    echo ""
    echo "Verify TensorRT-LLM is accessible:"
    echo "  poetry run python -m essence verify-tensorrt-llm"
    echo ""
    echo "If model needs to be loaded:"
    echo "  poetry run python -m essence manage-tensorrt-llm --action load --model qwen3-30b"
    SERVICE_URL="tensorrt-llm:8000"
fi
echo ""

# Step 4: Verification
echo "Step 4: Verification..."
echo "----------------------------------------"
echo "After starting the service, verify it's working:"
echo ""
if [ "$USE_LEGACY" = true ]; then
    echo "  poetry run python -m essence verify-qwen3 --inference-api-url $SERVICE_URL"
else
    echo "  poetry run python -m essence verify-tensorrt-llm"
    echo "  poetry run python -m essence manage-tensorrt-llm --action status --model qwen3-30b"
fi
echo ""
echo "Check GPU utilization:"
echo "  nvidia-smi"
echo ""
echo "Test inference:"
    echo "  poetry run python -m essence coding-agent --task 'Hello, world!' --llm-url $SERVICE_URL"
echo ""

echo "=========================================="
echo "Setup workflow complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Start the LLM service (see Step 3 above)"
echo "2. Verify the service is running (see Step 4 above)"
echo "3. Test the coding agent or run benchmarks"
echo ""
echo "For detailed instructions, see:"
echo "  - QWEN3_SETUP_PLAN.md"
echo "  - docs/guides/TENSORRT_LLM_SETUP.md"
echo "  - docs/guides/NIM_SETUP.md (for NIM alternative)"
echo ""
