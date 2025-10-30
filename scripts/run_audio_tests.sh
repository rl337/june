#!/bin/bash
# Complete Audio Services Deployment and Testing Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check Docker permissions
check_docker_permissions() {
    print_header "Checking Docker Permissions"
    
    if docker ps >/dev/null 2>&1; then
        print_success "Docker permissions are working"
        return 0
    else
        print_error "Docker permissions not working"
        print_info "To fix Docker permissions, run:"
        echo "  sudo usermod -aG docker $USER"
        echo "  newgrp docker"
        echo "  # Or log out and log back in"
        return 1
    fi
}

# Deploy audio services
deploy_audio_services() {
    print_header "Deploying Audio Services"
    
    # Start NATS (required dependency)
    print_info "Starting NATS..."
    docker compose up -d nats
    sleep 5
    
    # Start STT service
    print_info "Starting STT service..."
    docker compose up -d stt
    
    # Start TTS service
    print_info "Starting TTS service..."
    docker compose up -d tts
    
    print_success "Audio services deployed"
}

# Wait for services to be ready
wait_for_services() {
    print_header "Waiting for Services to be Ready"
    
    local max_wait=300  # 5 minutes
    local wait_time=0
    
    # Wait for STT service
    print_info "Waiting for STT service..."
    while [ $wait_time -lt $max_wait ]; do
        if timeout 5 grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check > /dev/null 2>&1; then
            print_success "STT service is ready"
            break
        fi
        sleep 5
        wait_time=$((wait_time + 5))
        print_info "Still waiting for STT service... (${wait_time}s)"
    done
    
    if [ $wait_time -ge $max_wait ]; then
        print_error "STT service did not become ready"
        return 1
    fi
    
    # Reset wait time
    wait_time=0
    
    # Wait for TTS service
    print_info "Waiting for TTS service..."
    while [ $wait_time -lt $max_wait ]; do
        if timeout 5 grpcurl -plaintext localhost:50053 grpc.health.v1.Health/Check > /dev/null 2>&1; then
            print_success "TTS service is ready"
            break
        fi
        sleep 5
        wait_time=$((wait_time + 5))
        print_info "Still waiting for TTS service... (${wait_time}s)"
    done
    
    if [ $wait_time -ge $max_wait ]; then
        print_error "TTS service did not become ready"
        return 1
    fi
}

# Run round-trip tests
run_round_trip_tests() {
    print_header "Running Round-Trip Tests"
    
    if command -v python3 &> /dev/null; then
        print_info "Running round-trip TTS→STT tests..."
        
        if [ -f "services/cli-tools/scripts/round_trip_test.py" ]; then
            python3 services/cli-tools/scripts/round_trip_test.py \
                --tts-url "localhost:50053" \
                --stt-url "localhost:50052" \
                --test-cases 10 \
                --data-dir "/tmp/round_trip_tests" \
                --output "/tmp/round_trip_report.json"
            
            if [ $? -eq 0 ]; then
                print_success "Round-trip tests passed!"
            else
                print_warning "Round-trip tests had issues"
            fi
        else
            print_error "Round-trip test script not found"
            return 1
        fi
    else
        print_error "Python3 not available for round-trip tests"
        return 1
    fi
}

# Run comprehensive audio tests
run_comprehensive_tests() {
    print_header "Running Comprehensive Audio Tests"
    
    if [ -f "scripts/test_audio_services.sh" ]; then
        print_info "Running comprehensive audio tests..."
        ./scripts/test_audio_services.sh
        
        if [ $? -eq 0 ]; then
            print_success "Comprehensive audio tests passed!"
        else
            print_warning "Some comprehensive tests had issues"
        fi
    else
        print_error "Comprehensive test script not found"
        return 1
    fi
}

# Show service status
show_status() {
    print_header "Service Status"
    
    echo "Docker containers:"
    docker compose ps stt tts nats
    
    echo -e "\nService URLs:"
    echo "  STT Service: localhost:50052"
    echo "  TTS Service: localhost:50053"
    echo "  NATS: localhost:4222"
    
    echo -e "\nHealth checks:"
    if timeout 5 grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check > /dev/null 2>&1; then
        print_success "STT service is healthy"
    else
        print_error "STT service is unhealthy"
    fi
    
    if timeout 5 grpcurl -plaintext localhost:50053 grpc.health.v1.Health/Check > /dev/null 2>&1; then
        print_success "TTS service is healthy"
    else
        print_error "TTS service is unhealthy"
    fi
}

# Cleanup function
cleanup() {
    print_header "Cleaning Up"
    
    print_info "Stopping audio services..."
    docker compose stop stt tts nats
    
    print_success "Cleanup completed"
}

# Main execution
main() {
    echo -e "${BLUE}June Agent Audio Services Deployment and Testing${NC}"
    echo -e "${BLUE}===============================================${NC}\n"
    
    # Check Docker permissions first
    if ! check_docker_permissions; then
        print_error "Cannot proceed without Docker permissions"
        print_info "Please fix Docker permissions first:"
        echo "  1. Run: sudo usermod -aG docker $USER"
        echo "  2. Run: newgrp docker"
        echo "  3. Or log out and log back in"
        echo "  4. Then run this script again"
        exit 1
    fi
    
    # Deploy services
    deploy_audio_services
    
    # Wait for services
    if ! wait_for_services; then
        print_error "Services did not become ready"
        exit 1
    fi
    
    # Show initial status
    show_status
    
    # Run tests
    print_header "Running Tests"
    
    # Run round-trip tests
    run_round_trip_tests
    
    # Run comprehensive tests
    run_comprehensive_tests
    
    # Final status
    show_status
    
    print_success "Audio services deployment and testing completed!"
    
    # Ask if user wants to cleanup
    echo ""
    read -p "Do you want to stop the services? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cleanup
    else
        print_info "Services are still running. Use 'docker compose stop stt tts nats' to stop them."
    fi
}

# Handle script interruption
trap 'print_warning "Script interrupted"; cleanup; exit 1' INT TERM

# Run main function
main "$@"





