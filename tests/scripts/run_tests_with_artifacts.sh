#!/bin/bash
# Test Orchestration Script with Artifact Collection
# Spins up fresh containers, runs tests, collects artifacts, then shuts down
#
# ⚠️ **OBSOLETE:** This script is obsolete in its current form because it references
# the gateway service, which has been removed as part of the refactoring. The gateway
# service was removed to achieve a minimal architecture with direct gRPC communication
# between services.
#
# **Status:** This script is kept for reference but is not functional in its current
# form. It starts the gateway container, runs gateway-specific tests, and collects
# gateway artifacts. The script could potentially be updated to orchestrate tests
# for the remaining services (telegram, discord, stt, tts, inference-api) if needed.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Docker Compose command support
docker_compose_cmd() {
    # Use sg docker for proper permissions
    # Build command with all arguments properly quoted
    local cmd_args=()
    for arg in "$@"; do
        cmd_args+=("$(printf '%q' "$arg")")
    done
    
    if command -v docker-compose &> /dev/null; then
        eval "sg docker -c \"cd /home/rlee/dev/june && docker-compose ${cmd_args[*]}\""
    elif command -v docker &> /dev/null && sg docker -c "docker compose version" &> /dev/null 2>&1; then
        eval "sg docker -c \"cd /home/rlee/dev/june && docker compose ${cmd_args[*]}\""
    else
        return 1
    fi
}

print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Configuration
JUNE_DATA_DIR="${JUNE_DATA_DIR:-/home/rlee/june_data}"
JUNE_TEST_DATA_DIR="${JUNE_TEST_DATA_DIR:-/home/rlee/june_test_data}"
MODEL_CACHE_DIR="${MODEL_CACHE_DIR:-/home/rlee/models}"

# Test run directory
TEST_RUN_DIR="${JUNE_TEST_DATA_DIR}/run_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$TEST_RUN_DIR"

print_header "Test Orchestration with Artifact Collection"
echo "Test Run Directory: $TEST_RUN_DIR"
echo "Model Artifacts: ${JUNE_DATA_DIR}/model_artifacts"
echo "Test Artifacts: ${TEST_RUN_DIR}"
echo ""

# Step 1: Ensure directories exist
print_header "Step 1: Checking Directories"

# Create model cache directory
if [ ! -d "$MODEL_CACHE_DIR" ]; then
    print_warning "Model cache directory does not exist: $MODEL_CACHE_DIR"
    print_info "Creating directory..."
    mkdir -p "$MODEL_CACHE_DIR"
fi

# Create model artifacts directories
print_info "Ensuring model artifacts directories exist..."
mkdir -p "${JUNE_DATA_DIR}/model_artifacts/stt"
mkdir -p "${JUNE_DATA_DIR}/model_artifacts/tts"
mkdir -p "${JUNE_DATA_DIR}/model_artifacts/inference-api"
mkdir -p "${JUNE_DATA_DIR}/model_artifacts/gateway"
print_success "Model artifacts directories ready"

# Check if models exist
MODEL_COUNT=$(find "$MODEL_CACHE_DIR" -name "*.bin" -o -name "*.safetensors" 2>/dev/null | wc -l)
if [ "$MODEL_COUNT" -eq 0 ]; then
    print_warning "No models found in cache. Downloading models..."
    if command -v poetry &> /dev/null; then
        print_info "Running model download..."
        poetry run python -m essence download-models --all || {
            print_warning "Model download had issues. Continuing anyway..."
        }
    else
        print_warning "Poetry not found. Skipping model download."
    fi
else
    print_success "Found $MODEL_COUNT model files in cache"
fi

# Step 2: Start fresh containers
print_header "Step 2: Starting Fresh Containers"

# Stop and remove existing containers
print_info "Cleaning up existing containers..."
cd /home/rlee/dev/june
docker_compose_cmd down --remove-orphans 2>/dev/null || true

# Start required services for testing (including CLI tools)
print_info "Starting services: nats, stt, tts, gateway, cli-tools..."
docker_compose_cmd --profile tools up -d nats stt tts gateway cli-tools || {
    print_error "Failed to start services"
    print_info "Attempting to start individually..."
    docker_compose_cmd up -d nats || print_warning "NATS failed"
    sleep 2
    docker_compose_cmd up -d stt || print_warning "STT failed"
    docker_compose_cmd up -d tts || print_warning "TTS failed"
    docker_compose_cmd up -d gateway || print_warning "Gateway failed"
    docker_compose_cmd --profile tools up -d cli-tools || print_warning "CLI tools failed"
}

# Wait for services to be ready
print_info "Waiting for services to be ready..."
sleep 10

# Check service health
print_info "Checking service health..."
SERVICES_READY=0
for i in {1..30}; do
    if curl -s -f "http://localhost:8000/health" > /dev/null 2>&1; then
        SERVICES_READY=1
        break
    fi
    sleep 2
done

if [ $SERVICES_READY -eq 0 ]; then
    print_warning "Services may not be fully ready, but continuing with tests..."
    print_info "Checking which services are actually running..."
    sg docker -c "docker ps --format '{{.Names}}'" | grep june- || print_warning "No june containers found"
fi

# Step 3: Copy model artifacts from containers (if any)
print_header "Step 3: Collecting Model Artifacts from Containers"

mkdir -p "${JUNE_DATA_DIR}/model_artifacts"

# Function to copy artifacts from container
copy_container_artifacts() {
    local container_name=$1
    local container_path=$2
    local host_path=$3
    
    if sg docker -c "docker ps --format '{{.Names}}'" | grep -q "^${container_name}$"; then
        print_info "Copying artifacts from $container_name..."
        if sg docker -c "docker exec $container_name test -d $container_path" 2>/dev/null; then
            sg docker -c "docker cp ${container_name}:${container_path} ${host_path}/" 2>/dev/null || {
                print_warning "Could not copy from $container_name:$container_path"
            }
        else
            print_info "  No artifacts found at $container_path in $container_name"
        fi
    else
        print_warning "  Container $container_name is not running"
    fi
}

# Copy artifacts from each service
copy_container_artifacts "june-stt" "/app/model_artifacts" "${JUNE_DATA_DIR}/model_artifacts/stt"
copy_container_artifacts "june-tts" "/app/model_artifacts" "${JUNE_DATA_DIR}/model_artifacts/tts"
copy_container_artifacts "june-inference-api" "/app/model_artifacts" "${JUNE_DATA_DIR}/model_artifacts/inference-api"
copy_container_artifacts "june-gateway" "/app/model_artifacts" "${JUNE_DATA_DIR}/model_artifacts/gateway"

print_success "Model artifacts collected to ${JUNE_DATA_DIR}/model_artifacts"

# Step 4: Run tests
print_header "Step 4: Running Gateway Round-Trip Tests"

# Export the specific test run directory so Python script uses it
export JUNE_TEST_DATA_DIR="$TEST_RUN_DIR"
export JUNE_DATA_DIR="$JUNE_DATA_DIR"

# Generate Alice dataset if needed (run in CLI tools container)
if [ ! -f "${JUNE_DATA_DIR}/datasets/alice_in_wonderland/alice_dataset.json" ]; then
    print_info "Generating Alice dataset..."
    if sg docker -c "docker ps --format '{{.Names}}'" | grep -q "^june-cli-tools$"; then
        sg docker -c "docker exec -e JUNE_DATA_DIR=/data june-cli-tools poetry run python -m essence generate-alice-dataset" || {
            print_error "Failed to generate dataset"
            exit 1
        }
    else
        print_error "CLI tools container not running - cannot generate dataset"
        exit 1
    fi
fi

# Run tests inside CLI tools container
print_info "Running Gateway round-trip tests..."
print_info "Using test run directory: $TEST_RUN_DIR"
print_info "Running test script inside CLI tools container..."

# Calculate test run directory path inside container
# The TEST_RUN_DIR on host maps to /test_data/run_* inside container
TEST_RUN_NAME=$(basename "$TEST_RUN_DIR")
CONTAINER_TEST_RUN_DIR="/test_data/${TEST_RUN_NAME}"

print_info "Container test run directory: $CONTAINER_TEST_RUN_DIR"

# Verify CLI tools container is running
if ! sg docker -c "docker ps --format '{{.Names}}'" | grep -q "^june-cli-tools$"; then
    print_error "CLI tools container is not running. Cannot execute tests."
    exit 1
fi

# Run the script inside the container
print_info "Executing test script with TEST_LIMIT=${TEST_LIMIT:-10}"
TEST_RESULT=0
sg docker -c "docker exec \
    -e JUNE_TEST_DATA_DIR=\"${CONTAINER_TEST_RUN_DIR}\" \
    -e JUNE_DATA_DIR=/data \
    -e TTS_SERVICE_ADDRESS=tts:50053 \
    -e STT_SERVICE_ADDRESS=stt:50052 \
    -e GATEWAY_URL=http://gateway:8000 \
    -w /app/root_scripts \
    june-cli-tools python test_round_trip_gateway.py --limit \"${TEST_LIMIT:-10}\"" 2>&1 | tee "${TEST_RUN_DIR}/test_output.log" || {
    TEST_RESULT=$?
    print_warning "Tests completed with exit code $TEST_RESULT"
}

# Verify artifacts were created
print_info "Verifying test artifacts..."
ARTIFACT_COUNT=$(find "$TEST_RUN_DIR" -type f 2>/dev/null | wc -l)
if [ "$ARTIFACT_COUNT" -eq 0 ]; then
    print_error "No artifacts found in test run directory: $TEST_RUN_DIR"
    print_info "Check test output log: ${TEST_RUN_DIR}/test_output.log"
else
    print_success "Found $ARTIFACT_COUNT files in test run directory"
    print_info "Artifact breakdown:"
    find "$TEST_RUN_DIR" -type f -o -type d | head -20 | while read -r item; do
        if [ -f "$item" ]; then
            print_info "  File: $item ($(stat -c%s "$item" 2>/dev/null || echo 0) bytes)"
        fi
    done
fi

# Step 5: Collect test artifacts from containers
print_header "Step 5: Collecting Test Artifacts from Containers"

mkdir -p "${TEST_RUN_DIR}/container_artifacts"

# Copy logs and runtime artifacts from each container
collect_container_test_artifacts() {
    local container_name=$1
    local artifact_dir="${TEST_RUN_DIR}/container_artifacts/${container_name}"
    mkdir -p "$artifact_dir"
    
    if sg docker -c "docker ps --format '{{.Names}}'" | grep -q "^${container_name}$"; then
        print_info "Collecting artifacts from $container_name..."
        
        # Copy logs
        docker_compose_cmd logs "$container_name" > "${artifact_dir}/logs.txt" 2>&1 || true
        
        # Copy any test artifacts from container
        sg docker -c "docker exec $container_name find /app -name '*.wav' -o -name '*.json' -o -name 'test_*' -type f 2>/dev/null" | while read -r file; do
            if [ -n "$file" ]; then
                local rel_path=$(echo "$file" | sed 's|^/app/||')
                local dest_dir="${artifact_dir}/$(dirname "$rel_path")"
                mkdir -p "$dest_dir"
                sg docker -c "docker cp ${container_name}:${file} ${artifact_dir}/${rel_path}" 2>/dev/null || true
            fi
        done
        
        # Copy any model output artifacts
        if sg docker -c "docker exec $container_name test -d /app/model_outputs" 2>/dev/null; then
            sg docker -c "docker cp ${container_name}:/app/model_outputs ${artifact_dir}/" 2>/dev/null || true
        fi
        
        print_success "Collected artifacts from $container_name"
    else
        print_warning "$container_name is not running, skipping artifact collection"
    fi
}

collect_container_test_artifacts "june-stt"
collect_container_test_artifacts "june-tts"
collect_container_test_artifacts "june-gateway"
collect_container_test_artifacts "june-inference-api"

# Step 6: Create test run summary
print_header "Step 6: Creating Test Run Summary"

SUMMARY_FILE="${TEST_RUN_DIR}/test_run_summary.json"
cat > "$SUMMARY_FILE" <<EOF
{
  "test_run_directory": "$TEST_RUN_DIR",
  "test_timestamp": "$(date -Iseconds)",
  "model_cache_directory": "$MODEL_CACHE_DIR",
  "model_artifacts_directory": "${JUNE_DATA_DIR}/model_artifacts",
  "test_artifacts_directory": "$TEST_RUN_DIR",
  "services_started": ["nats", "stt", "tts", "gateway"],
  "test_exit_code": $TEST_RESULT,
  "artifacts_collected": {
    "model_artifacts": "$(find ${JUNE_DATA_DIR}/model_artifacts -type f 2>/dev/null | wc -l) files",
    "test_audio_input": "$(find ${TEST_RUN_DIR}/input_audio -type f 2>/dev/null | wc -l) files",
    "test_audio_output": "$(find ${TEST_RUN_DIR}/output_audio -type f 2>/dev/null | wc -l) files",
    "test_transcripts": "$(find ${TEST_RUN_DIR}/transcripts -type f 2>/dev/null | wc -l) files",
    "test_metadata": "$(find ${TEST_RUN_DIR}/metadata -type f 2>/dev/null | wc -l) files",
    "container_artifacts": "$(find ${TEST_RUN_DIR}/container_artifacts -type f 2>/dev/null | wc -l) files"
  }
}
EOF

print_success "Test run summary saved to $SUMMARY_FILE"

# Step 7: Shut down containers
print_header "Step 7: Shutting Down Containers"

print_info "Stopping containers..."
cd /home/rlee/dev/june
docker_compose_cmd down

print_success "Containers stopped"

# Final summary
print_header "Test Run Complete"
echo "Test Run Directory: $TEST_RUN_DIR"
echo "Model Artifacts: ${JUNE_DATA_DIR}/model_artifacts"
echo ""
echo "Test Artifacts:"
ls -lh "$TEST_RUN_DIR" | tail -10
echo ""
echo "To view artifacts:"
echo "  cd $TEST_RUN_DIR"
echo "  ls -R"

exit $TEST_RESULT

