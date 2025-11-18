# Testing Guide

This guide explains how to run and write tests for the June project, following the testing strategy defined in Phase 12.

## Quick Start

### Run All Tests

```bash
# Run all tests
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run with coverage
poetry run pytest --cov=essence --cov-report=html
```

### Run Unit Tests Only

```bash
# Run all unit tests (fast, mocked)
poetry run pytest tests/essence/ tests/services/ -v

# Run specific unit test file
poetry run pytest tests/essence/chat/test_message_splitting.py -v
```

### Run Integration Tests

Integration tests require running services. See [Integration Test Service](#integration-test-service) section below.

```bash
# Run integration tests (requires services running)
poetry run pytest tests/integration/ -v
```

## Unit Tests

### Requirements

Unit tests must follow these requirements (Phase 12):

1. **All external services/libraries must be mocked**
   - Mock gRPC clients
   - Mock HTTP clients
   - Mock database connections
   - Mock file system operations

2. **Fast execution (< 1 minute for full suite)**
   - Unit tests should complete quickly
   - Use `@pytest.mark.slow` for tests that take > 1 second

3. **No dependencies on running services**
   - Tests should run without any services running
   - All external dependencies must be mocked

4. **All tests runnable via pytest**
   - Use standard pytest conventions
   - No custom test runners

### Running Unit Tests

```bash
# Run all unit tests
poetry run pytest tests/essence/ tests/services/ -v

# Run tests for specific module
poetry run pytest tests/essence/chat/ -v

# Run specific test file
poetry run pytest tests/essence/chat/test_message_splitting.py -v

# Run specific test function
poetry run pytest tests/essence/chat/test_message_splitting.py::test_split_long_message -v

# Run with coverage
poetry run pytest tests/essence/ --cov=essence --cov-report=html
```

### Writing Unit Tests

**Example: Unit test with mocks**

```python
import pytest
from unittest.mock import Mock, AsyncMock, patch
from essence.chat.message_builder import MessageBuilder

def test_message_builder_creates_text_message():
    """Test that MessageBuilder creates text messages correctly."""
    builder = MessageBuilder(service_name="test")
    message = builder.create_text_message("Hello, world!")
    
    assert message is not None
    assert message.text == "Hello, world!"
    assert message.type == "text"

@pytest.mark.asyncio
async def test_voice_handler_with_mocked_services():
    """Test voice handler with mocked gRPC services."""
    # Mock gRPC clients
    mock_stt_client = AsyncMock()
    mock_stt_client.transcribe.return_value = "Hello, world"
    
    mock_llm_client = AsyncMock()
    mock_llm_client.generate.return_value = "Response text"
    
    mock_tts_client = AsyncMock()
    mock_tts_client.synthesize.return_value = b"audio_data"
    
    # Test handler with mocks
    # ... test implementation ...
    
    assert mock_stt_client.transcribe.called
    assert mock_llm_client.generate.called
    assert mock_tts_client.synthesize.called
```

**Best Practices:**

1. **Use pytest fixtures for common setup:**
   ```python
   @pytest.fixture
   def mock_stt_client():
       client = AsyncMock()
       client.transcribe.return_value = "transcribed text"
       return client
   ```

2. **Mock external dependencies:**
   ```python
   @patch('essence.services.telegram.handlers.grpc_client')
   def test_with_mocked_grpc(mock_grpc):
       # Test implementation
       pass
   ```

3. **Test error cases:**
   ```python
   def test_handles_missing_config():
       with pytest.raises(ValueError, match="Configuration required"):
           service = Service(config=None)
   ```

4. **Use async fixtures for async tests:**
   ```python
   @pytest.fixture
   async def async_setup():
       # Async setup
       yield
       # Async teardown
   ```

## Integration Tests

### Requirements

Integration tests follow these requirements (Phase 12):

1. **Run in background (not waited on)**
   - Tests are started and run asynchronously
   - Results checked via REST API or logs

2. **Check end-to-end functionality with real services**
   - Use real services (STT, TTS, Inference API)
   - Test complete workflows

3. **Results available via REST API or logs**
   - Integration test service provides REST API
   - Test results stored and retrievable

4. **Can be checked periodically**
   - Tests don't block execution
   - Status can be polled

### Integration Test Service

**Status:** ✅ COMPLETED (Phase 12)

The integration test service provides:
- REST API for starting test runs
- Status checking endpoint
- Results retrieval
- Log viewing
- Test run history
- Health check and metrics endpoints

#### Starting the Integration Test Service

**Using the command:**

```bash
# Start the integration test service
poetry run python -m essence integration-test-service

# With custom port
poetry run python -m essence integration-test-service --port 8082

# With custom host and port
poetry run python -m essence integration-test-service --host 0.0.0.0 --port 8082
```

**Using environment variables:**

```bash
export INTEGRATION_TEST_SERVICE_PORT=8082
export INTEGRATION_TEST_SERVICE_HOST=0.0.0.0
poetry run python -m essence integration-test-service
```

**Service endpoints:**
- Default port: `8082`
- Health check: `http://localhost:8082/health`
- Metrics: `http://localhost:8082/metrics`

#### REST API Reference

**1. Start a Test Run**

Start a new integration test run:

```bash
# Run all integration tests
curl -X POST http://localhost:8082/tests/run

# Run specific test file
curl -X POST "http://localhost:8082/tests/run?test_path=tests/integration/test_voice_message_integration.py"

# Run specific test by name
curl -X POST "http://localhost:8082/tests/run?test_name=test_voice_processing"

# Run specific test in specific file
curl -X POST "http://localhost:8082/tests/run?test_path=tests/integration/test_voice_message_integration.py&test_name=test_voice_processing"
```

**Response:**
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "started_at": "2024-01-15T10:30:00"
}
```

**2. Check Test Run Status**

Get the current status of a test run:

```bash
curl http://localhost:8082/tests/status/550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "started_at": "2024-01-15T10:30:00",
  "completed_at": null,
  "exit_code": null,
  "test_path": "tests/integration/test_voice_message_integration.py",
  "test_name": null
}
```

**Status values:**
- `pending` - Test run queued but not started
- `running` - Test run in progress
- `completed` - Test run finished successfully
- `failed` - Test run failed
- `cancelled` - Test run was cancelled

**3. Get Test Results**

Get complete results of a test run (including output and logs):

```bash
curl http://localhost:8082/tests/results/550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "started_at": "2024-01-15T10:30:00",
  "completed_at": "2024-01-15T10:35:00",
  "exit_code": 0,
  "output": "=== test session starts ===\n...",
  "error": null,
  "logs": ["...", "..."],
  "test_path": "tests/integration/test_voice_message_integration.py",
  "test_name": null
}
```

**4. Get Test Logs**

Get logs for a test run (last N lines):

```bash
# Get last 100 lines (default)
curl http://localhost:8082/tests/logs/550e8400-e29b-41d4-a716-446655440000

# Get last 50 lines
curl "http://localhost:8082/tests/logs/550e8400-e29b-41d4-a716-446655440000?lines=50"

# Get all logs
curl "http://localhost:8082/tests/logs/550e8400-e29b-41d4-a716-446655440000?lines=0"
```

**Response:**
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "logs": ["[INFO] Starting test...", "[INFO] Test passed", "..."]
}
```

**5. List All Test Runs**

List all test runs (most recent first):

```bash
# List last 50 runs (default)
curl http://localhost:8082/tests/runs

# List last 10 runs
curl "http://localhost:8082/tests/runs?limit=10"
```

**Response:**
```json
{
  "runs": [
    {
      "run_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "started_at": "2024-01-15T10:30:00",
      "completed_at": "2024-01-15T10:35:00",
      "exit_code": 0,
      "test_path": "tests/integration/test_voice_message_integration.py",
      "test_name": null
    }
  ],
  "total": 1
}
```

**6. Cancel a Running Test**

Cancel a test run that is currently running:

```bash
curl -X DELETE http://localhost:8082/tests/runs/550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled",
  "message": "Test run cancelled"
}
```

**7. Health Check**

Check if the integration test service is healthy:

```bash
curl http://localhost:8082/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "integration-test"
}
```

**8. Prometheus Metrics**

Get Prometheus metrics:

```bash
curl http://localhost:8082/metrics
```

#### Using the Integration Test Service

**Example workflow:**

```bash
# 1. Start the integration test service (in one terminal)
poetry run python -m essence integration-test-service

# 2. Start a test run (in another terminal)
RUN_ID=$(curl -s -X POST http://localhost:8082/tests/run | jq -r '.run_id')
echo "Test run started: $RUN_ID"

# 3. Check status periodically
while true; do
  STATUS=$(curl -s http://localhost:8082/tests/status/$RUN_ID | jq -r '.status')
  echo "Status: $STATUS"
  if [ "$STATUS" != "running" ] && [ "$STATUS" != "pending" ]; then
    break
  fi
  sleep 5
done

# 4. Get results when complete
curl http://localhost:8082/tests/results/$RUN_ID | jq '.'

# 5. View logs
curl http://localhost:8082/tests/logs/$RUN_ID | jq '.logs[]'
```

**Using Python client:**

```python
import requests
import time

BASE_URL = "http://localhost:8082"

# Start test run
response = requests.post(f"{BASE_URL}/tests/run", params={
    "test_path": "tests/integration/test_voice_message_integration.py"
})
run_id = response.json()["run_id"]
print(f"Test run started: {run_id}")

# Poll for completion
while True:
    status_response = requests.get(f"{BASE_URL}/tests/status/{run_id}")
    status = status_response.json()["status"]
    print(f"Status: {status}")
    
    if status not in ["pending", "running"]:
        break
    time.sleep(5)

# Get results
results = requests.get(f"{BASE_URL}/tests/results/{run_id}").json()
print(f"Exit code: {results['exit_code']}")
print(f"Output:\n{results['output']}")
```

### Current Integration Tests

Integration tests are located in `tests/integration/`:

- `test_system_integration.py` - System-wide integration tests
- `test_voice_message_integration.py` - Voice message flow tests
- `test_llm_grpc_endpoints.py` - LLM gRPC endpoint tests
- `test_telegram_bot_qwen3_integration.py` - Telegram bot with Qwen3 tests

**Running integration tests directly (for development):**

```bash
# Run all integration tests (requires services running)
poetry run pytest tests/integration/ -v

# Run specific integration test
poetry run pytest tests/integration/test_voice_message_integration.py -v
```

**Running integration tests via service (recommended):**

```bash
# Start test service
poetry run python -m essence integration-test-service

# Start test run via API
curl -X POST http://localhost:8082/tests/run
```

#### Setting Up Periodic Test Runs

**Using cron (host system):**

Create a cron job to run tests periodically:

```bash
# Edit crontab
crontab -e

# Run all integration tests daily at 2 AM
0 2 * * * curl -X POST http://localhost:8082/tests/run > /tmp/integration-test-cron.log 2>&1

# Run specific test file every 6 hours
0 */6 * * * curl -X POST "http://localhost:8082/tests/run?test_path=tests/integration/test_voice_message_integration.py" > /tmp/integration-test-cron.log 2>&1

# Run tests and send results via email on failure
0 2 * * * RUN_ID=$(curl -s -X POST http://localhost:8082/tests/run | jq -r '.run_id') && sleep 300 && STATUS=$(curl -s http://localhost:8082/tests/status/$RUN_ID | jq -r '.status') && if [ "$STATUS" = "failed" ]; then curl -s http://localhost:8082/tests/results/$RUN_ID | mail -s "Integration Test Failed" admin@example.com; fi
```

**Using systemd timer (host system):**

Create a systemd service and timer:

```ini
# /etc/systemd/system/june-integration-test.service
[Unit]
Description=June Integration Test Run
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/curl -X POST http://localhost:8082/tests/run
StandardOutput=journal
StandardError=journal
```

```ini
# /etc/systemd/system/june-integration-test.timer
[Unit]
Description=Run June Integration Tests Daily
Requires=june-integration-test.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start the timer:

```bash
sudo systemctl enable june-integration-test.timer
sudo systemctl start june-integration-test.timer
sudo systemctl status june-integration-test.timer
```

**Using Docker container with cron:**

Create a simple cron container that triggers test runs:

```dockerfile
# Dockerfile for test scheduler
FROM curlimages/curl:latest

# Install cron
RUN apk add --no-cache dcron

# Copy cron script
COPY test-scheduler.sh /test-scheduler.sh
RUN chmod +x /test-scheduler.sh

# Add cron job
RUN echo "0 2 * * * /test-scheduler.sh" | crontab -

CMD ["crond", "-f"]
```

```bash
#!/bin/sh
# test-scheduler.sh
curl -X POST http://integration-test:8082/tests/run
```

**Using Python script with schedule library:**

Create a Python script for periodic test runs:

```python
#!/usr/bin/env python3
"""Periodic integration test runner."""
import schedule
import time
import requests
import logging

BASE_URL = "http://localhost:8082"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_integration_tests():
    """Trigger integration test run."""
    try:
        response = requests.post(f"{BASE_URL}/tests/run", timeout=10)
        response.raise_for_status()
        run_id = response.json()["run_id"]
        logger.info(f"Test run started: {run_id}")
        return run_id
    except Exception as e:
        logger.error(f"Failed to start test run: {e}")
        return None

# Schedule test runs
schedule.every().day.at("02:00").do(run_integration_tests)
schedule.every(6).hours.do(run_integration_tests)

# Run scheduler
logger.info("Test scheduler started")
while True:
    schedule.run_pending()
    time.sleep(60)
```

Run the scheduler:

```bash
# Install schedule library
poetry add schedule

# Run scheduler
poetry run python test-scheduler.py
```

**Using Docker Compose with healthcheck-based triggers:**

You can use external monitoring tools (like Prometheus Alertmanager) to trigger test runs based on service health or schedules.

**Best Practices for Periodic Test Runs:**

1. **Start with daily runs:** Run tests once per day during off-peak hours
2. **Monitor test results:** Set up alerts for test failures
3. **Log test runs:** Keep history of test runs and results
4. **Use test service API:** Always use the REST API, not direct pytest calls
5. **Check service availability:** Ensure integration test service is running before scheduling
6. **Handle failures gracefully:** Don't let test failures break the scheduler
7. **Review test history:** Regularly review test run history via `/tests/runs` endpoint

**Example: Complete periodic test setup script:**

```bash
#!/bin/bash
# run-periodic-tests.sh

INTEGRATION_TEST_URL="http://localhost:8082"

# Check if service is available
if ! curl -f -s "${INTEGRATION_TEST_URL}/health" > /dev/null; then
    echo "ERROR: Integration test service is not available"
    exit 1
fi

# Start test run
RUN_ID=$(curl -s -X POST "${INTEGRATION_TEST_URL}/tests/run" | jq -r '.run_id')

if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
    echo "ERROR: Failed to start test run"
    exit 1
fi

echo "Test run started: $RUN_ID"

# Wait for completion (with timeout)
TIMEOUT=3600  # 1 hour
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(curl -s "${INTEGRATION_TEST_URL}/tests/status/${RUN_ID}" | jq -r '.status')
    
    if [ "$STATUS" != "pending" ] && [ "$STATUS" != "running" ]; then
        break
    fi
    
    sleep 30
    ELAPSED=$((ELAPSED + 30))
done

# Get results
RESULTS=$(curl -s "${INTEGRATION_TEST_URL}/tests/results/${RUN_ID}")
EXIT_CODE=$(echo "$RESULTS" | jq -r '.exit_code')
STATUS=$(echo "$RESULTS" | jq -r '.status')

echo "Test run completed: status=$STATUS, exit_code=$EXIT_CODE"

# Exit with test exit code
exit $EXIT_CODE
```

Make it executable and add to cron:

```bash
chmod +x run-periodic-tests.sh

# Add to crontab
crontab -e
# Add: 0 2 * * * /path/to/run-periodic-tests.sh >> /var/log/june/periodic-tests.log 2>&1
```

## Test Structure

```
tests/
├── essence/              # Unit tests for essence package
│   └── chat/            # Chat/conversation utilities tests
├── integration/         # Integration tests (will use test service)
├── services/            # Service-specific unit tests
│   ├── telegram/       # Telegram service tests
│   ├── discord/        # Discord service tests
│   ├── stt/            # STT service tests
│   ├── tts/            # TTS service tests
│   └── inference-api/  # Inference API service tests
├── agentic/            # Agentic capabilities tests
├── scripts/            # Test utility scripts
└── data/               # Test data files (JSON fixtures)
```

## Test Markers

Use pytest markers to categorize tests:

```python
@pytest.mark.unit
def test_unit_function():
    """Unit test - fast, mocked."""
    pass

@pytest.mark.integration
def test_integration():
    """Integration test - requires services."""
    pass

@pytest.mark.slow
def test_slow_operation():
    """Slow test - may take > 1 second."""
    pass
```

**Running tests by marker:**

```bash
# Run only unit tests
poetry run pytest -m unit -v

# Run only integration tests
poetry run pytest -m integration -v

# Skip slow tests
poetry run pytest -m "not slow" -v
```

## Test Coverage

### Generate Coverage Report

```bash
# HTML report
poetry run pytest --cov=essence --cov-report=html
open htmlcov/index.html

# Terminal report
poetry run pytest --cov=essence --cov-report=term

# XML report (for CI)
poetry run pytest --cov=essence --cov-report=xml
```

### Coverage Goals

- **Target:** >80% code coverage
- **Critical paths:** 100% coverage
- **Error handling:** All error paths tested

## Common Patterns

### Mocking gRPC Clients

```python
from unittest.mock import AsyncMock

@pytest.fixture
def mock_stt_client():
    client = AsyncMock()
    client.transcribe = AsyncMock(return_value="transcribed text")
    return client

@pytest.mark.asyncio
async def test_with_mocked_grpc(mock_stt_client):
    result = await mock_stt_client.transcribe(audio_data)
    assert result == "transcribed text"
```

### Mocking HTTP Clients

```python
from unittest.mock import patch
import httpx

@patch('httpx.AsyncClient.post')
async def test_http_call(mock_post):
    mock_post.return_value = httpx.Response(200, json={"status": "ok"})
    # Test implementation
```

### Using Test Fixtures

```python
@pytest.fixture
def sample_audio_data():
    """Generate sample audio data for testing."""
    # Generate test audio
    return audio_bytes

def test_audio_processing(sample_audio_data):
    # Use fixture
    result = process_audio(sample_audio_data)
    assert result is not None
```

## Troubleshooting

### Common Issues

1. **Import Errors:**
   ```bash
   # Ensure essence package is installed
   poetry install
   ```

2. **Missing Dependencies:**
   ```bash
   # Install all dependencies
   poetry install
   ```

3. **Test Failures:**
   - Check that mocks are properly configured
   - Verify test data files exist
   - Ensure tests are isolated (no shared state)

4. **Slow Tests:**
   ```bash
   # Skip slow tests during development
   poetry run pytest -m "not slow" -v
   ```

### Debugging

```bash
# Run with verbose output and print statements
poetry run pytest -v -s tests/path/to/test.py

# Run specific test function
poetry run pytest tests/path/to/test.py::test_function_name -v

# Run with pdb debugger on failure
poetry run pytest --pdb tests/path/to/test.py
```

## Best Practices

1. **Test Isolation:** Each test should be independent
2. **Use Mocks:** Mock all external dependencies (gRPC, HTTP, databases, file system)
3. **Clear Assertions:** Use descriptive assertion messages
4. **Test Data:** Use fixtures and test data files, not hardcoded values
5. **Async Tests:** Use `@pytest.mark.asyncio` for async test functions
6. **Error Cases:** Test both success and error paths
7. **Performance:** Mark slow tests with `@pytest.mark.slow`
8. **Fast Execution:** Unit tests should complete in < 1 minute for full suite

## Related Documentation

- **Test Suite Details:** See `tests/README.md` for comprehensive test documentation
- **Agentic Tests:** See `tests/agentic/README.md` for agentic capabilities testing
- **Service Documentation:** See service-specific README files in `services/` directories
- **Development Guide:** See `docs/guides/AGENTS.md` for development practices
