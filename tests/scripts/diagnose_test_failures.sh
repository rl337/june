#!/bin/bash
# Comprehensive diagnostic script for test artifact failures

set -e

echo "=========================================="
echo "Test Artifact Failure Diagnostics"
echo "=========================================="
echo ""

# Check 1: Test run directory exists and is writable
echo "1. Checking test run directories..."
TEST_DIRS=$(find /home/rlee/june_test_data -name "run_*" -type d | wc -l)
echo "   Found $TEST_DIRS test run directories"

LATEST_RUN=$(find /home/rlee/june_test_data -name "run_*" -type d | sort -r | head -1)
if [ -n "$LATEST_RUN" ]; then
    echo "   Latest run: $LATEST_RUN"
    FILE_COUNT=$(find "$LATEST_RUN" -type f 2>/dev/null | wc -l)
    DIR_COUNT=$(find "$LATEST_RUN" -type d 2>/dev/null | wc -l)
    echo "   Files: $FILE_COUNT, Directories: $DIR_COUNT"
    if [ -f "$LATEST_RUN/test_output.log" ]; then
        echo "   Output log exists: $(wc -l < "$LATEST_RUN/test_output.log") lines"
    else
        echo "   ⚠️  No test_output.log found"
    fi
fi
echo ""

# Check 2: Dataset exists
echo "2. Checking Alice dataset..."
DATASET="/home/rlee/june_data/datasets/alice_in_wonderland/alice_dataset.json"
if [ -f "$DATASET" ]; then
    PASSAGE_COUNT=$(python3 -c "import json; data=json.load(open('$DATASET')); print(len(data.get('passages', [])))" 2>/dev/null || echo "0")
    echo "   ✅ Dataset exists with $PASSAGE_COUNT passages"
else
    echo "   ❌ Dataset missing: $DATASET"
fi
echo ""

# Check 3: Docker containers
echo "3. Checking Docker containers..."
cd /home/rlee/dev/june
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif command -v docker &> /dev/null && docker compose version &> /dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "   ❌ Docker Compose not found"
    exit 1
fi

echo "   Checking required containers..."
for container in june-nats june-stt june-tts june-gateway june-cli-tools; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        STATUS=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null)
        echo "   ✅ $container: $STATUS"
    else
        echo "   ❌ $container: not running"
    fi
done
echo ""

# Check 4: CLI tools container accessibility
echo "4. Checking CLI tools container..."
if docker ps --format '{{.Names}}' | grep -q "^june-cli-tools$"; then
    echo "   Testing Python script access..."
    if docker exec june-cli-tools test -f /app/root_scripts/test_round_trip_gateway.py; then
        echo "   ✅ Test script accessible"
    else
        echo "   ❌ Test script NOT accessible at /app/root_scripts/test_round_trip_gateway.py"
        echo "   Contents of /app/root_scripts:"
        docker exec june-cli-tools ls -la /app/root_scripts/ 2>&1 || true
    fi
    
    echo "   Testing proto access..."
    if docker exec june-cli-tools test -d /app/proto; then
        PROTO_FILES=$(docker exec june-cli-tools find /app/proto -name "*_pb2.py" 2>/dev/null | wc -l)
        echo "   ✅ Proto directory accessible with $PROTO_FILES pb2 files"
    else
        echo "   ❌ Proto directory NOT accessible"
    fi
    
    echo "   Testing dataset access..."
    if docker exec june-cli-tools test -f /data/datasets/alice_in_wonderland/alice_dataset.json; then
        echo "   ✅ Dataset accessible in container"
    else
        echo "   ❌ Dataset NOT accessible at /data/datasets/alice_in_wonderland/alice_dataset.json"
    fi
    
    echo "   Testing test data directory..."
    if docker exec june-cli-tools test -d /test_data; then
        echo "   ✅ Test data directory mounted"
        RUN_DIRS=$(docker exec june-cli-tools find /test_data -name "run_*" -type d 2>/dev/null | wc -l)
        echo "   Found $RUN_DIRS test run directories"
    else
        echo "   ⚠️  Test data directory not mounted"
    fi
else
    echo "   ❌ CLI tools container not running"
fi
echo ""

# Check 5: Service connectivity
echo "5. Testing service connectivity from CLI container..."
if docker ps --format '{{.Names}}' | grep -q "^june-cli-tools$"; then
    # Test TTS
    echo "   Testing TTS service (tts:50053)..."
    docker exec june-cli-tools timeout 3 bash -c 'echo > /dev/tcp/tts/50053' 2>/dev/null && echo "   ✅ TTS reachable" || echo "   ❌ TTS not reachable"
    
    # Test STT
    echo "   Testing STT service (stt:50052)..."
    docker exec june-cli-tools timeout 3 bash -c 'echo > /dev/tcp/stt/50052' 2>/dev/null && echo "   ✅ STT reachable" || echo "   ❌ STT not reachable"
    
    # Test Gateway
    echo "   Testing Gateway service (gateway:8000)..."
    docker exec june-cli-tools timeout 3 bash -c 'echo > /dev/tcp/gateway/8000' 2>/dev/null && echo "   ✅ Gateway reachable" || echo "   ❌ Gateway not reachable"
fi
echo ""

# Check 6: Python dependencies
echo "6. Checking Python dependencies in CLI container..."
if docker ps --format '{{.Names}}' | grep -q "^june-cli-tools$"; then
    docker exec june-cli-tools python -c "import grpc" 2>/dev/null && echo "   ✅ grpc" || echo "   ❌ grpc missing"
    docker exec june-cli-tools python -c "import httpx" 2>/dev/null && echo "   ✅ httpx" || echo "   ❌ httpx missing"
    docker exec june-cli-tools python -c "import asyncio" 2>/dev/null && echo "   ✅ asyncio" || echo "   ❌ asyncio missing"
fi
echo ""

# Check 7: Test script execution
echo "7. Attempting dry run of test script..."
if docker ps --format '{{.Names}}' | grep -q "^june-cli-tools$"; then
    echo "   Running test script with --help..."
    docker exec -w /app/root_scripts \
        -e JUNE_TEST_DATA_DIR="/test_data/test_diagnostic_$(date +%s)" \
        -e JUNE_DATA_DIR="/data" \
        june-cli-tools python test_round_trip_gateway.py --help 2>&1 | head -5 || echo "   ❌ Script failed to run"
fi
echo ""

# Check 8: Environment variables in orchestration script
echo "8. Checking orchestration script environment variable handling..."
if [ -f "tests/scripts/run_tests_with_artifacts.sh" ]; then
    echo "   Script exists"
    if grep -q "JUNE_TEST_DATA_DIR" tests/scripts/run_tests_with_artifacts.sh; then
        echo "   ✅ JUNE_TEST_DATA_DIR is set in script"
    else
        echo "   ❌ JUNE_TEST_DATA_DIR not found in script"
    fi
else
    echo "   ❌ Orchestration script not found"
fi
echo ""

# Check 9: Artifact saving logic
echo "9. Analyzing artifact saving logic..."
echo "   Expected artifacts per test:"
echo "   - 1 input audio file (passage_XXX_input.wav)"
echo "   - 1 output audio file (passage_XXX_output.wav)"
echo "   - 1 transcript file (passage_XXX.txt)"
echo "   - 1 metadata file (passage_XXX.json)"
echo "   Total per test: 4 files"
echo "   For 100 tests: 400 files + 1 test_summary.json + 1 test_output.log = 402 files"
echo ""

# Summary
echo "=========================================="
echo "Summary"
echo "=========================================="
if [ -n "$LATEST_RUN" ] && [ -f "$LATEST_RUN/test_output.log" ]; then
    echo "Last test output log (last 20 lines):"
    tail -20 "$LATEST_RUN/test_output.log"
else
    echo "⚠️  No test output log found - tests may not have run"
fi




