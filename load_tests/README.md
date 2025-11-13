# Load Testing Framework

Comprehensive load testing framework for June services to validate 10x capacity target.

## Overview

This framework provides load testing capabilities for:
- **Gateway REST API** - HTTP endpoints (chat, LLM, TTS, STT)
- **Gateway WebSocket** - Real-time WebSocket connections
- **gRPC Services** - STT, TTS, and Inference API services

## Features

- **Multiple Test Scenarios**: Baseline, target (10x), ramp-up, spike, and sustained load
- **Comprehensive Metrics**: Latency (p50, p95, p99), throughput, error rates, resource utilization
- **Report Generation**: HTML, JSON, CSV reports with charts and comparisons
- **CI/CD Integration**: Automated load tests in GitHub Actions
- **Before/After Comparisons**: Compare performance improvements

## Installation

```bash
# Install dependencies
pip install -r load_tests/requirements.txt
```

## Quick Start

### Run Baseline Load Test

```bash
# Run all tests with baseline scenario
python load_tests/run_load_tests.py --scenario baseline

# Run specific test type
python load_tests/run_load_tests.py --scenario baseline --test-type rest
python load_tests/run_load_tests.py --scenario baseline --test-type websocket
python load_tests/run_load_tests.py --scenario baseline --test-type grpc
```

### Run Target Load Test (10x Capacity)

```bash
python load_tests/run_load_tests.py --scenario target
```

### Generate Reports

```bash
# Generate report from JSON
python load_tests/generate_report.py load_tests/reports/baseline/20240101_120000/locust_report_*.json

# Compare two reports
python load_tests/generate_report.py \
  load_tests/reports/target/20240101_130000/locust_report_*.json \
  --compare load_tests/reports/baseline/20240101_120000/locust_report_*.json
```

## Test Scenarios

### Baseline
- **Users**: 10
- **Spawn Rate**: 2 users/second
- **Duration**: 5 minutes
- **Purpose**: Establish current capacity baseline

### Target (10x Capacity)
- **Users**: 100
- **Spawn Rate**: 10 users/second
- **Duration**: 10 minutes
- **Purpose**: Validate 10x capacity target

### Ramp Up
- **Users**: 200
- **Spawn Rate**: 5 users/second
- **Duration**: 20 minutes
- **Purpose**: Test system under gradually increasing load

### Spike
- **Users**: 500
- **Spawn Rate**: 50 users/second
- **Duration**: 5 minutes
- **Purpose**: Test system recovery from sudden load spikes

### Sustained
- **Users**: 150
- **Spawn Rate**: 10 users/second
- **Duration**: 30 minutes
- **Purpose**: Identify memory leaks and stability issues

## Configuration

Edit `load_tests/config/load_test_config.yaml` to customize:
- Service endpoints
- Test scenarios
- Metrics to collect
- Report settings

## Metrics Collected

### Latency Metrics
- Average response time
- Median response time
- P50, P75, P90, P95, P99 percentiles
- Min/Max response times

### Throughput Metrics
- Requests per second (RPS)
- Total requests
- Request distribution by endpoint

### Error Metrics
- Total failures
- Error rate by endpoint
- Failure types

### Resource Utilization
- CPU usage
- Memory usage
- GPU utilization
- Database connection pool usage

## Acceptance Criteria

Load tests must meet these criteria:

1. **Latency**: P95 response time < 2s for most requests
2. **Error Rate**: < 1% error rate
3. **Throughput**: System handles target load (10x baseline)
4. **Recovery**: System recovers gracefully after load spikes

## Running Locust UI

For interactive testing and monitoring:

```bash
# Start Locust web UI
locust -f load_tests/locust/gateway_rest.py --host=http://localhost:8000

# Open browser to http://localhost:8089
```

## CI/CD Integration

Load tests are automatically run:
- **Daily**: Scheduled at 2 AM UTC
- **Manual**: Via GitHub Actions workflow dispatch

To trigger manually:
```bash
gh workflow run load_tests.yml -f scenario=target
```

## Report Structure

Reports are saved to `load_tests/reports/<scenario>/<timestamp>/`:

```
reports/
├── baseline/
│   └── 20240101_120000/
│       ├── locust_report_20240101_120000.html
│       ├── locust_report_20240101_120000.json
│       ├── locust_report_20240101_120000_stats.csv
│       └── analysis/
│           ├── metrics.csv
│           ├── summary.txt
│           ├── response_time_by_endpoint.png
│           ├── p95_response_time.png
│           └── error_rate_by_endpoint.png
```

## Troubleshooting

### Services Not Available

Ensure all June services are running:
```bash
docker-compose ps
```

### High Error Rates

1. Check service health: `curl http://localhost:8000/health`
2. Review service logs: `docker-compose logs gateway`
3. Check resource utilization: `docker stats`

### gRPC Tests Failing

Ensure `june-grpc-api` package is installed:
```bash
pip install -e packages/june-grpc-api
```

## Performance Tuning

Based on load test results:

1. **High Latency**: Optimize database queries, add caching, increase connection pools
2. **High Error Rate**: Scale services, increase resource limits, optimize code
3. **Low Throughput**: Horizontal scaling, connection pooling, caching strategy

## Contributing

When adding new test scenarios or endpoints:

1. Update `load_test_config.yaml`
2. Add test cases to Locust files
3. Update documentation
4. Run tests to verify

## References

- [Locust Documentation](https://docs.locust.io/)
- [gRPC Python Guide](https://grpc.io/docs/languages/python/)
- [June Architecture Documentation](../docs/architecture/ARCHITECTURE.md)
