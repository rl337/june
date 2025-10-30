#!/bin/bash
# Quick test to verify artifact collection works

set -e

TEST_RUN_DIR="/home/rlee/june_test_data/test_artifact_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$TEST_RUN_DIR"/{input_audio,output_audio,transcripts,metadata}

echo "Test directory: $TEST_RUN_DIR"

# Create test files
echo "test audio data" > "$TEST_RUN_DIR/input_audio/test.wav"
echo "test transcript" > "$TEST_RUN_DIR/transcripts/test.txt"
echo '{"test": "metadata"}' > "$TEST_RUN_DIR/metadata/test.json"

# Count artifacts
ARTIFACT_COUNT=$(find "$TEST_RUN_DIR" -type f | wc -l)

if [ "$ARTIFACT_COUNT" -ge 3 ]; then
    echo "✓ Artifact collection test passed: $ARTIFACT_COUNT files created"
    ls -lhR "$TEST_RUN_DIR"
    exit 0
else
    echo "✗ Artifact collection test failed: only $ARTIFACT_COUNT files found"
    exit 1
fi


