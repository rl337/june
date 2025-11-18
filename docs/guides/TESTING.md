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

**Status:** ⏳ TODO (Phase 12)

The integration test service will provide:
- REST API for starting test runs
- Status checking endpoint
- Results retrieval
- Log viewing
- Test run history

**Once implemented, usage will be:**

```bash
# Start integration test run
curl -X POST http://localhost:8082/tests/run

# Check test status
curl http://localhost:8082/tests/status

# Get test results
curl http://localhost:8082/tests/results
```

### Current Integration Tests

Integration tests are located in `tests/integration/`:

- `test_system_integration.py` - System-wide integration tests
- `test_voice_message_integration.py` - Voice message flow tests
- `test_llm_grpc_endpoints.py` - LLM gRPC endpoint tests
- `test_telegram_bot_qwen3_integration.py` - Telegram bot with Qwen3 tests

**Running current integration tests:**

```bash
# Run all integration tests (requires services running)
poetry run pytest tests/integration/ -v

# Run specific integration test
poetry run pytest tests/integration/test_voice_message_integration.py -v
```

**Note:** Current integration tests run synchronously. They will be migrated to use the integration test service (Phase 12 task 2).

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
