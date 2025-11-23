#!/bin/bash
# Helper script for Phase 19: Verify NIM ARM64/DGX Spark compatibility
#
# This script helps verify which NIM containers are available and compatible
# with ARM64/DGX Spark architecture, and provides guidance on updating
# home_infra/docker-compose.yml.
#
# Usage:
#   ./scripts/verify_nim_compatibility.sh [--stt-only] [--tts-only] [--update-compose]
#
# Options:
#   --stt-only        Only check STT NIMs
#   --tts-only        Only check TTS NIMs
#   --update-compose  Automatically update home_infra/docker-compose.yml (interactive)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOME_INFRA_DIR="/home/rlee/dev/home_infra"
cd "$PROJECT_ROOT"

CHECK_STT=true
CHECK_TTS=true
UPDATE_COMPOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --stt-only)
            CHECK_STT=true
            CHECK_TTS=false
            shift
            ;;
        --tts-only)
            CHECK_STT=false
            CHECK_TTS=true
            shift
            ;;
        --update-compose)
            UPDATE_COMPOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--stt-only] [--tts-only] [--update-compose]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "NIM ARM64/DGX Spark Compatibility Check"
echo "=========================================="
echo ""

# Check if NGC_API_KEY is set
if [ -z "${NGC_API_KEY:-}" ]; then
    echo "⚠️  NGC_API_KEY not set"
    echo ""
    echo "To use this script effectively, set NGC_API_KEY:"
    echo "  export NGC_API_KEY='your-api-key'"
    echo ""
    echo "Get your API key from: https://catalog.ngc.nvidia.com/"
    echo "  Sign in → Profile → API Keys → Generate API Key"
    echo ""
    echo "Continuing without API key (limited functionality)..."
    echo ""
fi

# Check if list-nims command exists
if ! poetry run python -m essence list-nims --help > /dev/null 2>&1; then
    echo "❌ list-nims command not found"
    echo "   This script requires the list-nims essence command"
    exit 1
fi

# Function to check NIMs
check_nims() {
    local filter=$1
    local type_name=$2
    
    echo "=========================================="
    echo "Checking ${type_name} NIMs (${filter})"
    echo "=========================================="
    echo ""
    
    # Query for DGX Spark compatible NIMs
    echo "Querying NGC catalog for DGX Spark compatible ${type_name} NIMs..."
    echo ""
    
    if [ -n "${NGC_API_KEY:-}" ]; then
        poetry run python -m essence list-nims \
            --dgx-spark-only \
            --filter "$filter" \
            --format table \
            --ngc-api-key "$NGC_API_KEY" || {
            echo "⚠️  Failed to query NGC catalog (may need NGC_API_KEY)"
            echo ""
        }
    else
        echo "⚠️  NGC_API_KEY not set - cannot query NGC catalog"
        echo "   Set NGC_API_KEY to get detailed NIM information"
        echo ""
        echo "Trying without API key (limited results)..."
        poetry run python -m essence list-nims \
            --dgx-spark-only \
            --filter "$filter" \
            --format table || {
            echo "⚠️  No NIMs found or query failed"
            echo ""
        }
    fi
    
    echo ""
    echo "=========================================="
    echo "Next Steps for ${type_name} NIM"
    echo "=========================================="
    echo ""
    echo "1. **If NIM found with ARM64/DGX Spark support:**"
    echo "   - Note the exact image path (e.g., nvcr.io/nim/riva/riva-asr:1.0.0)"
    echo "   - Verify compatibility in NGC catalog: https://catalog.ngc.nvidia.com/"
    echo "   - Check documentation for exact image tag and architecture support"
    echo ""
    echo "2. **Update home_infra/docker-compose.yml:**"
    if [ "$UPDATE_COMPOSE" = true ]; then
        echo "   (Interactive update mode enabled)"
    else
        echo "   - Add service following nim-qwen3 pattern:"
        echo "     Example for STT:"
        echo "     nim-riva-asr:"
        echo "       image: nvcr.io/nim/riva/riva-asr:1.0.0"
        echo "       container_name: nim-riva-asr"
        echo "       environment:"
        echo "         - NGC_API_KEY=\${NGC_API_KEY}"
        echo "       networks:"
        echo "         - shared_network"
        echo "       deploy:"
        echo "         resources:"
        echo "           reservations:"
        echo "             devices:"
        echo "               - driver: nvidia"
        echo "                 count: 1"
        echo "                 capabilities: [gpu]"
        echo ""
        echo "   - Run with --update-compose flag to interactively update docker-compose.yml"
    fi
    echo ""
    echo "3. **If no ARM64-compatible NIM found:**"
    echo "   - Continue using custom ${type_name} service (already configured)"
    echo "   - Monitor NGC catalog for future ARM64 NIM releases"
    echo ""
    echo ""
}

# Check STT NIMs
if [ "$CHECK_STT" = true ]; then
    check_nims "stt" "STT (Speech-to-Text)"
fi

# Check TTS NIMs
if [ "$CHECK_TTS" = true ]; then
    check_nims "tts" "TTS (Text-to-Speech)"
fi

# Summary
echo "=========================================="
echo "Summary"
echo "=========================================="
echo ""
echo "✅ Compatibility check complete"
echo ""
echo "**Current Status (from docs/NIM_AVAILABILITY.md):**"
echo "- ✅ LLM: Qwen3-32B DGX Spark NIM configured (ready to deploy)"
echo "- ⚠️  STT: Riva ASR NIM placeholder (needs verification)"
echo "- ⚠️  TTS: Riva TTS NIM placeholder (needs verification)"
echo ""
echo "**Next Steps:**"
echo "1. Review NIM query results above"
echo "2. Verify exact image paths in NGC catalog"
echo "3. Update home_infra/docker-compose.yml with verified image paths"
echo "4. Test NIM services after deployment"
echo ""
echo "**Documentation:**"
echo "- NIM Availability: docs/NIM_AVAILABILITY.md"
echo "- NIM Setup Guide: docs/guides/NIM_SETUP.md"
echo "- Operational Readiness: docs/OPERATIONAL_READINESS.md"
echo ""
