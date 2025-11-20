#!/bin/bash
# Operational workflow script for Phase 15: NVIDIA NIM Setup
#
# This script orchestrates the operational tasks for setting up NVIDIA NIM:
# 1. Pre-flight environment check
# 2. NGC API key verification
# 3. Image name verification guidance
# 4. Service startup guidance
# 5. Verification steps
#
# Usage:
#   ./scripts/setup_nim_operational.sh [--skip-check] [--skip-verify]
#
# Options:
#   --skip-check      Skip pre-flight environment check
#   --skip-verify     Skip NGC API key and image name verification prompts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SKIP_CHECK=false
SKIP_VERIFY=false

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
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-check] [--skip-verify]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "NVIDIA NIM Setup - Operational Workflow"
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

# Step 2: NGC API key verification
if [ "$SKIP_VERIFY" = false ]; then
    echo "Step 2: NGC API key verification..."
    echo "----------------------------------------"
    echo "NVIDIA NIM requires an NGC API key to pull containers from NGC registry."
    echo ""
    echo "To get your NGC API key:"
    echo "  1. Go to https://catalog.ngc.nvidia.com/"
    echo "  2. Sign in with your NVIDIA account"
    echo "  3. Navigate to your profile → API Keys → Generate API Key"
    echo ""
    
    # Check if NGC_API_KEY is set in home_infra
    HOME_INFRA_DIR="/home/rlee/dev/home_infra"
    if [ -d "$HOME_INFRA_DIR" ]; then
        if [ -f "$HOME_INFRA_DIR/.env" ]; then
            if grep -q "NGC_API_KEY=" "$HOME_INFRA_DIR/.env"; then
                echo "✅ Found NGC_API_KEY in $HOME_INFRA_DIR/.env"
            else
                echo "⚠️  NGC_API_KEY not found in $HOME_INFRA_DIR/.env"
                echo ""
                echo "Add NGC_API_KEY to $HOME_INFRA_DIR/.env:"
                echo "  echo 'NGC_API_KEY=your-api-key-here' >> $HOME_INFRA_DIR/.env"
            fi
        else
            echo "⚠️  .env file not found in $HOME_INFRA_DIR"
            echo ""
            echo "Create $HOME_INFRA_DIR/.env and add:"
            echo "  NGC_API_KEY=your-api-key-here"
        fi
    else
        echo "⚠️  home_infra directory not found at $HOME_INFRA_DIR"
        echo "   Make sure home_infra is set up correctly."
    fi
    echo ""
    
    read -p "Have you set up your NGC API key? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Please set up your NGC API key before proceeding."
        echo "See docs/guides/NIM_SETUP.md for detailed instructions."
        exit 0
    fi
    echo ""
else
    echo "Step 2: Skipping NGC API key verification (--skip-verify)"
    echo ""
fi

# Step 3: Image name verification guidance
if [ "$SKIP_VERIFY" = false ]; then
    echo "Step 3: Image name verification..."
    echo "----------------------------------------"
    echo "IMPORTANT: Verify the NIM image name in home_infra/docker-compose.yml"
    echo ""
    echo "The image name may need to be updated based on the NGC catalog."
    echo "Current configuration uses: nvcr.io/nvstaging/nim_qwen3_30b_instruct:latest"
    echo ""
    echo "To find the correct image name:"
    echo "  1. Go to https://catalog.ngc.nvidia.com/"
    echo "  2. Navigate to Containers → NIM (or search for 'NIM')"
    echo "  3. Search for 'qwen3' or 'qwen'"
    echo "  4. Find the container matching your requirements (30B, A3B architecture)"
    echo "  5. Update home_infra/docker-compose.yml with the correct image name"
    echo ""
    echo "See docs/guides/NIM_SETUP.md for detailed instructions."
    echo ""
    
    read -p "Have you verified the image name? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Please verify the image name before proceeding."
        echo "See docs/guides/NIM_SETUP.md for detailed instructions."
        exit 0
    fi
    echo ""
else
    echo "Step 3: Skipping image name verification (--skip-verify)"
    echo ""
fi

# Step 4: Service startup guidance
echo "Step 4: Service startup..."
echo "----------------------------------------"
echo "Starting NIM service in home_infra..."
echo ""
echo "Commands to start the service:"
echo "  cd /home/rlee/dev/home_infra"
echo "  docker compose up -d nim-qwen3"
echo ""
echo "Check service logs:"
echo "  cd /home/rlee/dev/home_infra"
echo "  docker compose logs -f nim-qwen3"
echo ""
echo "Check service status:"
echo "  cd /home/rlee/dev/home_infra"
echo "  docker compose ps nim-qwen3"
echo ""

# Step 5: Verification
echo "Step 5: Verification..."
echo "----------------------------------------"
echo "After starting the service, verify it's working:"
echo ""
echo "From june project directory:"
echo "  poetry run python -m essence verify-nim --nim-host nim-qwen3 --http-port 8003 --grpc-port 8001"
echo ""
echo "Check GPU utilization:"
echo "  nvidia-smi"
echo ""
echo "Test gRPC connectivity:"
echo "  poetry run python -m essence verify-nim --nim-host nim-qwen3 --http-port 8003 --grpc-port 8001 --check-grpc"
echo ""
echo "Test protocol compatibility:"
echo "  poetry run python -m essence verify-nim --nim-host nim-qwen3 --http-port 8003 --grpc-port 8001 --check-protocol"
echo ""
echo "Test inference (if coding agent is available):"
echo "  poetry run python -m essence coding-agent --task 'Hello, world!' --llm-url grpc://nim-qwen3:8001"
echo ""

echo "=========================================="
echo "Setup workflow complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Start the NIM service (see Step 4 above)"
echo "2. Verify the service is running (see Step 5 above)"
echo "3. Test gRPC connectivity from june services"
echo "4. Verify protocol compatibility"
echo ""
echo "For detailed instructions, see:"
echo "  - docs/guides/NIM_SETUP.md"
echo "  - REFACTOR_PLAN.md (Phase 15)"
echo ""
