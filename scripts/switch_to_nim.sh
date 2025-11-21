#!/bin/bash
# Helper script to switch june services from TensorRT-LLM to NVIDIA NIM endpoint
#
# This script:
# 1. Verifies NIM service is ready (using verify-nim command)
# 2. Updates LLM_URL in docker-compose.yml or .env file
# 3. Restarts telegram and discord services to use NIM endpoint
#
# Usage:
#   ./scripts/switch_to_nim.sh [--verify-only] [--use-env] [--no-restart]
#
# Options:
#   --verify-only    Only verify NIM is ready, don't make changes
#   --use-env        Update .env file instead of docker-compose.yml
#   --no-restart     Don't restart services after updating configuration
#
# Prerequisites:
#   - NIM service must be running and ready (use verify-nim command first)
#   - Services must be running to restart them

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VERIFY_ONLY=false
USE_ENV=false
NO_RESTART=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --verify-only)
            VERIFY_ONLY=true
            shift
            ;;
        --use-env)
            USE_ENV=true
            shift
            ;;
        --no-restart)
            NO_RESTART=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--verify-only] [--use-env] [--no-restart]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Switch June Services to NIM Endpoint"
echo "=========================================="
echo ""

# Step 1: Verify NIM is ready
echo "Step 1: Verifying NIM service is ready..."
echo "-----------------------------------"
# Run verification from within telegram container (on shared-network) to access nim-qwen3
if ! docker compose exec -T telegram poetry run python -m essence verify-nim --nim-host nim-qwen3 --http-port 8000 --grpc-port 8001 > /tmp/nim_verify.log 2>&1; then
    echo "⚠️  Full verification failed, but checking HTTP endpoint directly..."
    # Fallback: Check HTTP endpoint directly from container
    if docker compose exec -T telegram python3 -c "import httpx; r = httpx.get('http://nim-qwen3:8000/v1/health/ready', timeout=5); exit(0 if r.status_code == 200 else 1)" 2>/dev/null; then
        echo "✅ NIM HTTP endpoint is accessible (gRPC check failed, but HTTP is sufficient for OpenAI-compatible API)"
    else
        echo "❌ NIM service is not ready yet."
        echo ""
        echo "Verification output:"
        cat /tmp/nim_verify.log
        echo ""
        echo "Please wait for NIM service to finish initializing, then try again."
        echo "Check NIM status: cd /home/rlee/dev/home_infra && docker compose ps nim-qwen3"
        echo "Check NIM logs: cd /home/rlee/dev/home_infra && docker compose logs nim-qwen3"
        exit 1
    fi
fi

echo "✅ NIM service is ready!"
echo ""

if [ "$VERIFY_ONLY" = true ]; then
    echo "Verification-only mode: NIM is ready, but no configuration changes made."
    exit 0
fi

# Step 2: Update configuration
echo "Step 2: Updating LLM_URL configuration..."
echo "-----------------------------------"

# NIM uses HTTP/OpenAI-compatible API, not gRPC
NIM_ENDPOINT="http://nim-qwen3:8000"

if [ "$USE_ENV" = true ]; then
    # Update .env file
    ENV_FILE="${JUNE_ENV_FILE:-.env}"
    if [ ! -f "$ENV_FILE" ]; then
        echo "Creating $ENV_FILE file..."
        touch "$ENV_FILE"
    fi
    
    # Check if LLM_URL already exists
    if grep -q "^LLM_URL=" "$ENV_FILE" 2>/dev/null; then
        echo "Updating LLM_URL in $ENV_FILE..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s|^LLM_URL=.*|LLM_URL=$NIM_ENDPOINT|" "$ENV_FILE"
        else
            # Linux
            sed -i "s|^LLM_URL=.*|LLM_URL=$NIM_ENDPOINT|" "$ENV_FILE"
        fi
    else
        echo "Adding LLM_URL to $ENV_FILE..."
        echo "LLM_URL=$NIM_ENDPOINT" >> "$ENV_FILE"
    fi
    echo "✅ Updated $ENV_FILE with LLM_URL=$NIM_ENDPOINT"
    echo ""
    echo "Note: Services will use this value on next restart."
    echo "To apply immediately, restart services: docker compose up -d telegram discord"
else
    # Update docker-compose.yml
    DOCKER_COMPOSE_FILE="docker-compose.yml"
    if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
        echo "❌ Error: $DOCKER_COMPOSE_FILE not found"
        exit 1
    fi
    
    echo "Updating LLM_URL in $DOCKER_COMPOSE_FILE..."
    
    # Update all services (telegram and discord) that use LLM_URL
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|LLM_URL=grpc://tensorrt-llm:8000|LLM_URL=$NIM_ENDPOINT|g" "$DOCKER_COMPOSE_FILE"
    else
        # Linux
        sed -i "s|LLM_URL=grpc://tensorrt-llm:8000|LLM_URL=$NIM_ENDPOINT|g" "$DOCKER_COMPOSE_FILE"
    fi
    
    echo "✅ Updated $DOCKER_COMPOSE_FILE with LLM_URL=$NIM_ENDPOINT"
    echo ""
fi

# Step 3: Restart services
if [ "$NO_RESTART" = false ]; then
    echo "Step 3: Restarting services..."
    echo "-----------------------------------"
    
    if [ "$USE_ENV" = true ]; then
        echo "Restarting telegram and discord services to load new LLM_URL from .env..."
        docker compose up -d telegram discord
    else
        echo "Restarting telegram and discord services to load new LLM_URL from docker-compose.yml..."
        docker compose up -d telegram discord
    fi
    
    echo "✅ Services restarted"
    echo ""
    echo "Waiting 5 seconds for services to start..."
    sleep 5
    
    # Verify services are healthy
    echo "Verifying services are healthy..."
    if docker compose ps telegram discord | grep -q "healthy\|running"; then
        echo "✅ Services are running"
    else
        echo "⚠️  Warning: Some services may not be healthy yet. Check status:"
        echo "   docker compose ps telegram discord"
    fi
else
    echo "Skipping service restart (--no-restart flag set)"
    echo ""
    echo "To apply changes, restart services manually:"
    echo "   docker compose up -d telegram discord"
fi

echo ""
echo "=========================================="
echo "Switch to NIM Complete"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - NIM endpoint: $NIM_ENDPOINT"
if [ "$USE_ENV" = true ]; then
    echo "  - Configuration: Updated .env file"
else
    echo "  - Configuration: Updated docker-compose.yml"
fi
if [ "$NO_RESTART" = false ]; then
    echo "  - Services: Restarted"
else
    echo "  - Services: Not restarted (use --no-restart to skip)"
fi
echo ""
echo "To switch back to TensorRT-LLM:"
if [ "$USE_ENV" = true ]; then
    echo "  Update .env: LLM_URL=grpc://tensorrt-llm:8000"
else
    echo "  Update docker-compose.yml: LLM_URL=grpc://tensorrt-llm:8000"
fi
echo "  Then restart: docker compose up -d telegram discord"
echo ""
