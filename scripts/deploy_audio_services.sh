#!/bin/bash
# Deploy and Test STT/TTS Services for June Agent

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

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker ps &> /dev/null; then
        print_error "Docker is not running or user doesn't have permission"
        print_info "Try running: sudo usermod -aG docker $USER && newgrp docker"
        exit 1
    fi
    
    print_success "Docker is available and running"
}

# Check if docker compose is available
check_docker_compose() {
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    elif docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        print_error "Docker Compose is not available"
        exit 1
    fi
    
    print_success "Docker Compose is available: $COMPOSE_CMD"
}

# Build STT and TTS services
build_services() {
    print_header "Building STT and TTS Services"
    
    # Build STT service
    print_info "Building STT service..."
    if $COMPOSE_CMD build stt; then
        print_success "STT service built successfully"
    else
        print_error "Failed to build STT service"
        exit 1
    fi
    
    # Build TTS service
    print_info "Building TTS service..."
    if $COMPOSE_CMD build tts; then
        print_success "TTS service built successfully"
    else
        print_error "Failed to build TTS service"
        exit 1
    fi
}

# Start STT and TTS services
start_services() {
    print_header "Starting STT and TTS Services"
    
    # Start NATS (required dependency)
    print_info "Starting NATS..."
    if $COMPOSE_CMD up -d nats; then
        print_success "NATS started"
    else
        print_error "Failed to start NATS"
        exit 1
    fi
    
    # Wait for NATS to be ready
    print_info "Waiting for NATS to be ready..."
    sleep 5
    
    # Start STT service
    print_info "Starting STT service..."
    if $COMPOSE_CMD up -d stt; then
        print_success "STT service started"
    else
        print_error "Failed to start STT service"
        exit 1
    fi
    
    # Start TTS service
    print_info "Starting TTS service..."
    if $COMPOSE_CMD up -d tts; then
        print_success "TTS service started"
    else
        print_error "Failed to start TTS service"
        exit 1
    fi
}

# Wait for services to be ready
wait_for_services() {
    print_header "Waiting for Services to be Ready"
    
    local max_wait=300  # 5 minutes
    local wait_time=0
    
    # Wait for STT service
    print_info "Waiting for STT service to be ready..."
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
        print_error "STT service did not become ready within ${max_wait}s"
        return 1
    fi
    
    # Reset wait time
    wait_time=0
    
    # Wait for TTS service
    print_info "Waiting for TTS service to be ready..."
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
        print_error "TTS service did not become ready within ${max_wait}s"
        return 1
    fi
}

# Test services
test_services() {
    print_header "Testing Audio Services"
    
    # Run the audio test script
    if [ -f "scripts/test_audio_services.sh" ]; then
        print_info "Running comprehensive audio tests..."
        if ./scripts/test_audio_services.sh; then
            print_success "Audio service tests passed"
        else
            print_warning "Some audio service tests failed"
        fi
    else
        print_warning "Audio test script not found, running basic tests..."
        
        # Basic health checks
        if timeout 10 grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check > /dev/null 2>&1; then
            print_success "STT service health check passed"
        else
            print_error "STT service health check failed"
        fi
        
        if timeout 10 grpcurl -plaintext localhost:50053 grpc.health.v1.Health/Check > /dev/null 2>&1; then
            print_success "TTS service health check passed"
        else
            print_error "TTS service health check failed"
        fi
    fi
}

# Show service status
show_status() {
    print_header "Service Status"
    
    echo "Docker containers:"
    $COMPOSE_CMD ps stt tts nats
    
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
    $COMPOSE_CMD stop stt tts nats
    
    print_success "Cleanup completed"
}

# Main execution
main() {
    echo -e "${BLUE}June Agent STT/TTS Deployment and Testing${NC}"
    echo -e "${BLUE}==========================================${NC}\n"
    
    # Parse command line arguments
    local action="deploy"
    local cleanup_after=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --test-only)
                action="test"
                shift
                ;;
            --cleanup)
                cleanup_after=true
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --test-only    Only run tests (assume services are running)"
                echo "  --cleanup      Stop services after testing"
                echo "  --help         Show this help message"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
    
    if [ "$action" = "deploy" ]; then
        # Full deployment process
        check_docker
        check_docker_compose
        build_services
        start_services
        wait_for_services
    fi
    
    # Test services
    test_services
    
    # Show status
    show_status
    
    # Cleanup if requested
    if [ "$cleanup_after" = true ]; then
        cleanup
    fi
    
    print_success "STT/TTS deployment and testing completed!"
}

# Handle script interruption
trap 'print_warning "Script interrupted"; cleanup; exit 1' INT TERM

# Run main function
main "$@"





