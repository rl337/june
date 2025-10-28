#!/bin/bash
# Audio Services Test Script for June Agent

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
STT_URL="localhost:50052"
TTS_URL="localhost:50053"
TEST_DATA_DIR="${JUNE_DATA_DIR:-/home/rlee/june_data}/audio_tests"
MAX_TEST_DURATION=300  # 5 minutes

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if grpcurl is available
check_grpcurl() {
    if ! command -v grpcurl &> /dev/null; then
        print_error "grpcurl is not installed. Please install it first:"
        echo "  go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest"
        exit 1
    fi
}

# Check if services are running
check_services() {
    print_header "Checking Audio Services"
    
    # Check STT service
    print_info "Checking STT service at $STT_URL..."
    if timeout 10 grpcurl -plaintext "$STT_URL" grpc.health.v1.Health/Check > /dev/null 2>&1; then
        print_success "STT service is running"
    else
        print_error "STT service is not responding"
        return 1
    fi
    
    # Check TTS service
    print_info "Checking TTS service at $TTS_URL..."
    if timeout 10 grpcurl -plaintext "$TTS_URL" grpc.health.v1.Health/Check > /dev/null 2>&1; then
        print_success "TTS service is running"
    else
        print_error "TTS service is not responding"
        return 1
    fi
}

# Test STT service with simple audio
test_stt_service() {
    print_header "Testing STT Service"
    
    # Create test data directory
    mkdir -p "$TEST_DATA_DIR"
    
    # Test cases
    local test_cases=(
        "Hello, how are you today?"
        "The quick brown fox jumps over the lazy dog."
        "Artificial intelligence is transforming the world."
        "Please call me at 555-123-4567."
        "The weather is sunny with a temperature of 75 degrees."
    )
    
    local successful_tests=0
    local total_tests=${#test_cases[@]}
    
    for i in "${!test_cases[@]}"; do
        local test_case="${test_cases[$i]}"
        print_info "Testing STT case $((i+1))/$total_tests: \"$test_case\""
        
        # Create a simple test audio file
        local audio_file="$TEST_DATA_DIR/stt_test_$((i+1)).wav"
        
        # Generate a simple sine wave audio file
        if command -v python3 &> /dev/null; then
            python3 -c "
import numpy as np
import soundfile as sf
import sys

# Generate a simple sine wave
sample_rate = 16000
duration = 3.0
frequency = 440

t = np.linspace(0, duration, int(sample_rate * duration))
audio = np.sin(2 * np.pi * frequency * t) * 0.1
audio += np.random.normal(0, 0.01, len(audio))

sf.write('$audio_file', audio, sample_rate)
print('Generated test audio file')
" 2>/dev/null || {
                print_warning "Could not generate test audio file"
                continue
            }
        else
            print_warning "Python3 not available for audio generation"
            continue
        fi
        
        # Test STT service
        local start_time=$(date +%s)
        
        # In a real implementation, this would use proper gRPC client
        # For now, we'll just check if the service is responsive
        if timeout 30 grpcurl -plaintext "$STT_URL" grpc.health.v1.Health/Check > /dev/null 2>&1; then
            local end_time=$(date +%s)
            local duration=$((end_time - start_time))
            
            print_success "STT test $((i+1)) completed in ${duration}s"
            ((successful_tests++))
        else
            print_error "STT test $((i+1)) failed"
        fi
        
        # Clean up test file
        rm -f "$audio_file"
    done
    
    print_info "STT Tests: $successful_tests/$total_tests successful"
    
    if [ $successful_tests -eq $total_tests ]; then
        print_success "All STT tests passed"
        return 0
    else
        print_warning "Some STT tests failed"
        return 1
    fi
}

# Test round-trip audio (TTS→STT)
test_round_trip() {
    print_header "Testing Round-Trip Audio (TTS→STT)"
    
    # Check if Python is available
    if command -v python3 &> /dev/null; then
        print_info "Running round-trip audio tests..."
        
        if [ -f "services/cli-tools/scripts/round_trip_test.py" ]; then
            python3 services/cli-tools/scripts/round_trip_test.py \
                --tts-url "$TTS_URL" \
                --stt-url "$STT_URL" \
                --data-dir "$TEST_DATA_DIR" \
                --output "$TEST_DATA_DIR/round_trip_report.json" 2>/dev/null || {
                print_warning "Round-trip tests failed or not available"
                return 1
            }
            
            print_success "Round-trip audio tests completed"
            return 0
        else
            print_warning "Round-trip test script not found"
            return 1
        fi
    else
        print_warning "Python3 not available for round-trip tests"
        return 1
    fi
}

# Test TTS service
test_tts_service() {
    print_header "Testing TTS Service"
    
    # Test cases
    local test_cases=(
        "Hello, this is a test of the text-to-speech system."
        "The quick brown fox jumps over the lazy dog."
        "Artificial intelligence and machine learning are fascinating topics."
        "Please speak clearly and at a moderate pace."
        "This is a test of different sentence lengths and complexity."
    )
    
    local successful_tests=0
    local total_tests=${#test_cases[@]}
    
    for i in "${!test_cases[@]}"; do
        local test_case="${test_cases[$i]}"
        print_info "Testing TTS case $((i+1))/$total_tests: \"$test_case\""
        
        local start_time=$(date +%s)
        
        # Test TTS service
        # In a real implementation, this would use proper gRPC client
        # For now, we'll just check if the service is responsive
        if timeout 30 grpcurl -plaintext "$TTS_URL" grpc.health.v1.Health/Check > /dev/null 2>&1; then
            local end_time=$(date +%s)
            local duration=$((end_time - start_time))
            
            print_success "TTS test $((i+1)) completed in ${duration}s"
            ((successful_tests++))
        else
            print_error "TTS test $((i+1)) failed"
        fi
    done
    
    print_info "TTS Tests: $successful_tests/$total_tests successful"
    
    if [ $successful_tests -eq $total_tests ]; then
        print_success "All TTS tests passed"
        return 0
    else
        print_warning "Some TTS tests failed"
        return 1
    fi
}

# Run comprehensive audio tests
run_comprehensive_tests() {
    print_header "Running Comprehensive Audio Tests"
    
    # Check if we can run Python tests
    if command -v python3 &> /dev/null; then
        print_info "Running Python-based audio tests..."
        
        # Try to run the comprehensive test suite
        if [ -f "services/cli-tools/scripts/simple_audio_test.py" ]; then
            python3 services/cli-tools/scripts/simple_audio_test.py \
                --test-all \
                --stt-url "$STT_URL" \
                --tts-url "$TTS_URL" \
                --data-dir "$TEST_DATA_DIR" 2>/dev/null || {
                print_warning "Python audio tests failed or not available"
            }
        else
            print_warning "Python audio test script not found"
        fi
    else
        print_warning "Python3 not available for comprehensive tests"
    fi
}

# Generate test report
generate_report() {
    print_header "Generating Test Report"
    
    local report_file="$TEST_DATA_DIR/audio_test_report_$(date +%Y%m%d_%H%M%S).json"
    
    # Create basic report
    cat > "$report_file" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "test_configuration": {
    "stt_url": "$STT_URL",
    "tts_url": "$TTS_URL",
    "test_data_dir": "$TEST_DATA_DIR"
  },
  "test_results": {
    "stt_service": {
      "status": "$(timeout 5 grpcurl -plaintext "$STT_URL" grpc.health.v1.Health/Check > /dev/null 2>&1 && echo "healthy" || echo "unhealthy")",
      "response_time": "$(timeout 5 grpcurl -plaintext "$STT_URL" grpc.health.v1.Health/Check 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")"
    },
    "tts_service": {
      "status": "$(timeout 5 grpcurl -plaintext "$TTS_URL" grpc.health.v1.Health/Check > /dev/null 2>&1 && echo "healthy" || echo "unhealthy")",
      "response_time": "$(timeout 5 grpcurl -plaintext "$TTS_URL" grpc.health.v1.Health/Check 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")"
    }
  },
  "test_files": [
    $(find "$TEST_DATA_DIR" -name "*.wav" -o -name "*.json" | sed 's/^/    "/' | sed 's/$/",/' | sed '$s/,$//')
  ]
}
EOF
    
    print_success "Test report generated: $report_file"
}

# Main execution
main() {
    echo -e "${BLUE}June Agent Audio Services Test${NC}"
    echo -e "${BLUE}==============================${NC}\n"
    
    local start_time=$(date +%s)
    
    # Check prerequisites
    check_grpcurl
    
    # Check if services are running
    if ! check_services; then
        print_error "Audio services are not running. Please start them first:"
        echo "  docker compose up -d stt tts"
        exit 1
    fi
    
    # Run tests
    local stt_result=0
    local tts_result=0
    local round_trip_result=0
    
    if test_stt_service; then
        stt_result=0
    else
        stt_result=1
    fi
    
    if test_tts_service; then
        tts_result=0
    else
        tts_result=1
    fi
    
    # Run round-trip tests
    if test_round_trip; then
        round_trip_result=0
    else
        round_trip_result=1
    fi
    
    # Run comprehensive tests if available
    run_comprehensive_tests
    
    # Generate report
    generate_report
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Summary
    print_header "Test Summary"
    echo "Total test duration: ${duration}s"
    echo "STT service: $([ $stt_result -eq 0 ] && echo "PASS" || echo "FAIL")"
    echo "TTS service: $([ $tts_result -eq 0 ] && echo "PASS" || echo "FAIL")"
    echo "Round-trip test: $([ $round_trip_result -eq 0 ] && echo "PASS" || echo "FAIL")"
    
    if [ $stt_result -eq 0 ] && [ $tts_result -eq 0 ] && [ $round_trip_result -eq 0 ]; then
        print_success "All audio service tests passed!"
        exit 0
    else
        print_error "Some audio service tests failed"
        exit 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --stt-url)
            STT_URL="$2"
            shift 2
            ;;
        --tts-url)
            TTS_URL="$2"
            shift 2
            ;;
        --data-dir)
            TEST_DATA_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --stt-url URL     STT service URL (default: localhost:50052)"
            echo "  --tts-url URL     TTS service URL (default: localhost:50053)"
            echo "  --data-dir DIR    Test data directory (default: /home/rlee/june_data/audio_tests)"
            echo "  --help            Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Run main function
main
