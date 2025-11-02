#!/bin/bash

# run_checks.sh - Test and quality checks for June MCP Client
# This script must be run before any commit or push

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if Poetry is available
check_poetry() {
    print_header "Checking Poetry"
    
    if command -v poetry &> /dev/null; then
        print_success "Poetry found: $(poetry --version)"
        return 0
    else
        print_error "Poetry not found. Install with: curl -sSL https://install.python-poetry.org | python3 -"
        exit 1
    fi
}

# Run unit tests
run_tests() {
    print_header "Running Unit Tests"
    
    if poetry run pytest -v; then
        print_success "All tests passed"
        return 0
    else
        print_error "Tests failed"
        return 1
    fi
}

# Main execution
main() {
    echo -e "${BLUE}June MCP Client - Pre-Commit Checks${NC}"
    echo -e "${BLUE}====================================${NC}\n"
    
    local start_time=$(date +%s)
    local failed_checks=0
    
    # Run all checks
    check_poetry || exit 1
    run_tests || failed_checks=$((failed_checks + 1))
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo -e "\n${BLUE}Checks completed in ${duration} seconds${NC}\n"
    
    if [ $failed_checks -eq 0 ]; then
        echo -e "${GREEN}🎉 All checks passed! Safe to commit and push.${NC}\n"
        exit 0
    else
        print_error "$failed_checks check(s) failed. Fix issues before committing."
        echo -e "\n${RED}❌ Do not commit until all checks pass.${NC}\n"
        exit 1
    fi
}

# Handle script arguments
case "${1:-}" in
    "--help"|"-h")
        echo "Usage: $0"
        echo ""
        echo "Runs tests for June MCP Client."
        echo "This script MUST pass before committing or pushing code."
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac

