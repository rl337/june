#!/bin/bash
# Operational workflow script for Phase 16 Task 5: Performance Testing
#
# This script orchestrates the operational tasks for running performance tests:
# 1. Pre-flight environment check
# 2. Service verification (STT, TTS, LLM)
# 3. Performance test configuration
# 4. Run performance tests
# 5. Results analysis guidance
#
# Usage:
#   ./scripts/run_performance_tests_operational.sh [--skip-check] [--skip-verify] [--scenario SCENARIO] [--test-type TYPE] [--run-now]
#
# Options:
#   --skip-check      Skip pre-flight environment check
#   --skip-verify     Skip service verification
#   --scenario SCENARIO  Test scenario (baseline, target, ramp_up, spike, sustained) [default: baseline]
#   --test-type TYPE     Test type (grpc, all) [default: grpc]
#   --run-now         Run performance tests immediately after verification (default: show guidance only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SKIP_CHECK=false
SKIP_VERIFY=false
SCENARIO="${SCENARIO:-baseline}"
TEST_TYPE="${TEST_TYPE:-grpc}"
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
        --scenario)
            SCENARIO="$2"
            shift 2
            ;;
        --test-type)
            TEST_TYPE="$2"
            shift 2
            ;;
        --run-now)
            RUN_NOW=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-check] [--skip-verify] [--scenario SCENARIO] [--test-type TYPE] [--run-now]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Performance Testing - Operational Workflow"
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

# Step 2: Service verification
if [ "$SKIP_VERIFY" = false ]; then
    echo "Step 2: Service verification..."
    echo "----------------------------------------"
    
    SERVICES_OK=true
    
    # Check STT service
    echo "Checking STT service..."
    if docker compose ps stt 2>&1 | grep -q "Up"; then
        echo "✅ STT service is running"
    else
        echo "❌ STT service is not running"
        echo "   Start with: docker compose up -d stt"
        SERVICES_OK=false
    fi
    
    # Check TTS service
    echo "Checking TTS service..."
    if docker compose ps tts 2>&1 | grep -q "Up"; then
        echo "✅ TTS service is running"
    else
        echo "❌ TTS service is not running"
        echo "   Start with: docker compose up -d tts"
        SERVICES_OK=false
    fi
    
    # Check LLM service (TensorRT-LLM, NIM, or legacy inference-api)
    echo "Checking LLM service..."
    LLM_SERVICE=""
    
    # Check TensorRT-LLM (default)
    if poetry run python -m essence verify-tensorrt-llm 2>&1 | grep -q "✅"; then
        echo "✅ TensorRT-LLM service is accessible"
        LLM_SERVICE="TensorRT-LLM"
    # Check NIM
    elif poetry run python -m essence verify-nim --nim-host nim-qwen3 --http-port 8003 --grpc-port 8001 2>&1 | grep -q "✅"; then
        echo "✅ NVIDIA NIM service is accessible"
        LLM_SERVICE="NIM"
    # Check legacy inference-api
    elif docker compose ps inference-api 2>&1 | grep -q "Up"; then
        echo "✅ Legacy inference-api service is running"
        LLM_SERVICE="Legacy Inference-API"
    else
        echo "❌ No LLM service is accessible"
        echo "   Options:"
        echo "   - TensorRT-LLM (default): cd /home/rlee/dev/home_infra && docker compose up -d tensorrt-llm"
        echo "   - NVIDIA NIM: cd /home/rlee/dev/home_infra && docker compose up -d nim-qwen3"
        echo "   - Legacy inference-api: docker compose --profile legacy up -d inference-api"
        SERVICES_OK=false
    fi
    
    echo ""
    
    if [ "$SERVICES_OK" = false ]; then
        echo "⚠️  Some services are not running. Performance tests may fail."
        echo ""
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 0
        fi
    fi
    echo ""
else
    echo "Step 2: Skipping service verification (--skip-verify)"
    echo ""
fi

# Step 3: Performance test configuration
echo "Step 3: Performance test configuration..."
echo "----------------------------------------"
echo "Configuration:"
echo "  Scenario: $SCENARIO"
echo "  Test Type: $TEST_TYPE"
echo ""

# Validate scenario
case "$SCENARIO" in
    baseline|target|ramp_up|spike|sustained)
        echo "✅ Valid scenario: $SCENARIO"
        ;;
    *)
        echo "❌ Invalid scenario: $SCENARIO"
        echo "   Valid scenarios: baseline, target, ramp_up, spike, sustained"
        exit 1
        ;;
esac

# Validate test type
case "$TEST_TYPE" in
    grpc|all)
        echo "✅ Valid test type: $TEST_TYPE"
        ;;
    rest|websocket)
        echo "⚠️  Test type '$TEST_TYPE' is obsolete (Gateway service was removed)"
        echo "   Use 'grpc' or 'all' instead"
        exit 1
        ;;
    *)
        echo "❌ Invalid test type: $TEST_TYPE"
        echo "   Valid test types: grpc, all"
        exit 1
        ;;
esac

echo ""

# Step 4: Run performance tests
if [ "$RUN_NOW" = true ]; then
    echo "Step 4: Running performance tests..."
    echo "----------------------------------------"
    echo ""
    
    # Check if load_tests dependencies are installed
    if ! python3 -c "import locust" 2>/dev/null; then
        echo "⚠️  Locust is not installed. Installing dependencies..."
        pip install -r load_tests/requirements.txt
    fi
    
    echo "Running performance tests with command:"
    echo "  python load_tests/run_load_tests.py --scenario $SCENARIO --test-type $TEST_TYPE"
    echo ""
    
    # Run performance tests
    python load_tests/run_load_tests.py --scenario "$SCENARIO" --test-type "$TEST_TYPE"
    
    echo ""
    echo "✅ Performance tests completed!"
    echo ""
    echo "Results are available in: load_tests/reports/$SCENARIO/"
    echo ""
else
    echo "Step 4: Performance test execution guidance..."
    echo "----------------------------------------"
    echo ""
    echo "To run performance tests, use one of the following methods:"
    echo ""
    echo "Method 1: Use this script with --run-now flag"
    echo "  ./scripts/run_performance_tests_operational.sh --run-now --scenario $SCENARIO --test-type $TEST_TYPE"
    echo ""
    echo "Method 2: Use the run_load_tests.py script directly"
    echo "  python load_tests/run_load_tests.py --scenario $SCENARIO --test-type $TEST_TYPE"
    echo ""
    echo "Method 3: Run with custom configuration"
    echo "  python load_tests/run_load_tests.py \\"
    echo "    --config load_tests/config/load_test_config.yaml \\"
    echo "    --scenario $SCENARIO \\"
    echo "    --test-type $TEST_TYPE \\"
    echo "    --output-dir load_tests/reports/$SCENARIO"
    echo ""
    echo "Available scenarios:"
    echo "  - baseline: 10 users, 2 users/sec, 5 minutes (establish baseline)"
    echo "  - target: 100 users, 10 users/sec, 10 minutes (10x capacity validation)"
    echo "  - ramp_up: 200 users, 5 users/sec, 20 minutes (gradual increase)"
    echo "  - spike: 500 users, 50 users/sec, 5 minutes (sudden spike)"
    echo "  - sustained: 150 users, 10 users/sec, 30 minutes (stability test)"
    echo ""
    echo "Available test types:"
    echo "  - grpc: Test gRPC services (STT, TTS, LLM) - RECOMMENDED"
    echo "  - all: Run all available test types (currently only grpc)"
    echo ""
fi

# Step 5: Results analysis guidance
echo "Step 5: Results analysis..."
echo "----------------------------------------"
echo ""
echo "After performance tests complete, analyze results:"
echo ""
echo "1. View HTML report:"
echo "   open load_tests/reports/$SCENARIO/locust_report_*.html"
echo ""
echo "2. View JSON report:"
echo "   cat load_tests/reports/$SCENARIO/locust_report_*.json"
echo ""
echo "3. View CSV reports:"
echo "   ls -la load_tests/reports/$SCENARIO/locust_report_*.csv"
echo ""
echo "4. Generate comparison report:"
echo "   python load_tests/generate_report.py \\"
echo "     load_tests/reports/$SCENARIO/locust_report_*.json \\"
echo "     --compare load_tests/reports/baseline/locust_report_*.json"
echo ""
echo "5. Analyze key metrics:"
echo "   - Latency (p50, p95, p99): Response time percentiles"
echo "   - Throughput: Requests per second"
echo "   - Error rate: Percentage of failed requests"
echo "   - Resource utilization: CPU, memory, GPU usage"
echo ""
echo "6. Identify bottlenecks:"
echo "   - Check which service has highest latency"
echo "   - Identify error patterns"
echo "   - Review resource utilization trends"
echo "   - Compare against baseline scenario"
echo ""

echo "=========================================="
echo "Workflow complete!"
echo "=========================================="
echo ""
echo "Next steps:"
if [ "$RUN_NOW" = false ]; then
    echo "1. Run performance tests (see Step 4 above)"
    echo "2. Analyze results (see Step 5 above)"
else
    echo "1. Analyze results (see Step 5 above)"
fi
echo "2. Document findings"
echo "3. Optimize identified bottlenecks"
echo "4. Re-run tests to measure improvements"
echo ""
echo "For detailed instructions, see:"
echo "  - load_tests/README.md"
echo "  - REFACTOR_PLAN.md (Phase 16 Task 5)"
echo ""
