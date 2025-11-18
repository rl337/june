#!/bin/bash
# Set Test Mode Configuration for June Agent
# Usage: ./tests/scripts/set_test_mode.sh [mock|stt_tts_roundtrip]

set -e

MODE=${1:-mock}

case "$MODE" in
    mock)
        echo "Setting configuration to: Full Mock Mode"
        echo "All services will run in pass-through mode for connectivity testing"
        export JUNE_TEST_MODE=mock
        export INFERENCE_MODE=mock
        export STT_MODE=mock
        export TTS_MODE=mock
        ;;
    stt_tts_roundtrip)
        echo "Setting configuration to: STT/TTS Round-Trip Mode"
        echo "TTS and STT services will use real models for audio validation"
        export JUNE_TEST_MODE=stt_tts_roundtrip
        export INFERENCE_MODE=mock
        export STT_MODE=real
        export TTS_MODE=real
        ;;
    *)
        echo "Unknown mode: $MODE"
        echo "Available modes:"
        echo "  mock              - Full mock mode (all services pass-through)"
        echo "  stt_tts_roundtrip - STT/TTS round-trip mode (real TTS/STT)"
        exit 1
        ;;
esac

echo ""
echo "Configuration set to: $MODE"
echo ""
echo "Environment variables set:"
echo "  JUNE_TEST_MODE=$JUNE_TEST_MODE"
echo "  INFERENCE_MODE=$INFERENCE_MODE"
echo "  STT_MODE=$STT_MODE"
echo "  TTS_MODE=$TTS_MODE"
echo ""
echo "To use this configuration, export these variables or add them to .env"
echo ""
echo "Example:"
echo "  source ./tests/scripts/set_test_mode.sh $MODE"
echo "  docker compose up -d"





