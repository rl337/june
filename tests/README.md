# June Test Suite Documentation

This document provides comprehensive documentation for running and maintaining the June project test suite.

## Overview

The June test suite covers:
- **Unit Tests** - Individual component testing
- **Integration Tests** - Service interaction testing
- **Service Tests** - Platform-specific service tests (Telegram, Discord, STT, TTS, Inference API (legacy))
- **Agentic Tests** - Agent capabilities testing (see `tests/agentic/README.md` for details)

**Note:** Inference API service tests are for the legacy `inference-api` service, which is deprecated. The project now uses TensorRT-LLM (default) or NVIDIA NIM for LLM inference. See `docs/guides/TENSORRT_LLM_SETUP.md` for migration details.

## Test Structure

```
tests/
├── essence/              # Tests for essence package (shared code)
│   └── chat/            # Chat/conversation utilities tests
├── integration/         # End-to-end integration tests
├── services/            # Service-specific tests
│   ├── telegram/       # Telegram service tests
│   ├── discord/        # Discord service tests
│   ├── stt/            # STT service tests
│   ├── tts/            # TTS service tests
│   └── inference-api/  # Legacy Inference API service tests (deprecated)
├── agentic/            # Agentic capabilities tests (see tests/agentic/README.md)
└── data/               # Test data files (JSON fixtures)
```

## Running Tests

### Prerequisites

1. **Install dependencies:**
   ```bash
   poetry install
   ```

2. **Ensure test environment is set up:**
   - Services should be available for integration tests (or use mocks)
   - Test data files should be in place

### Running All Tests

```bash
# Run all tests
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run with coverage report
poetry run pytest --cov=essence --cov-report=html

# Run specific test paths
poetry run pytest tests/essence/
poetry run pytest tests/integration/
poetry run pytest tests/services/
```

### Running Individual Service Tests

```bash
# Telegram service tests
poetry run pytest tests/services/telegram/ -v

# Discord service tests
poetry run pytest tests/services/discord/ -v

# STT service tests
poetry run pytest tests/services/stt/ -v

# TTS service tests
poetry run pytest tests/services/tts/ -v

# Legacy Inference API service tests (deprecated - use TensorRT-LLM instead)
poetry run pytest tests/services/inference-api/ -v
```

### Running Integration Tests

```bash
# All integration tests
poetry run pytest tests/integration/ -v

# Specific integration test
poetry run pytest tests/integration/test_voice_message_integration.py -v
```

### Running Tests with Markers

```bash
# Run only unit tests
poetry run pytest -m unit -v

# Run only integration tests
poetry run pytest -m integration -v

# Skip slow tests
poetry run pytest -m "not slow" -v
```

## Test Fixtures and Utilities

### Common Test Fixtures

Tests use pytest fixtures for common setup:

- **Mock services** - Mocked gRPC clients, HTTP clients
- **Test data** - Pre-configured test data from `tests/data/`
- **Temporary directories** - Isolated test environments

### Test Utilities

Located in test helper modules:
- Mock gRPC clients
- Mock HTTP clients
- Test data loaders
- Service mocks

## Adding New Tests

### Unit Test Example

```python
import pytest
from essence.chat.message_builder import MessageBuilder

def test_message_builder():
    """Test message builder functionality."""
    builder = MessageBuilder(service_name="test")
    message = builder.create_text_message("Hello")
    assert message is not None
```

### Integration Test Example

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_voice_processing_integration():
    """Test voice message processing flow."""
    # Setup mocks
    mock_stt = AsyncMock()
    mock_llm = AsyncMock()
    mock_tts = AsyncMock()
    
    # Test flow
    # ...
```

### Service Test Example

```python
import pytest
from essence.services.telegram.handlers.voice import handle_voice_message

@pytest.mark.asyncio
async def test_voice_message_handler():
    """Test voice message handler."""
    # Setup
    update = MagicMock()
    context = MagicMock()
    
    # Test
    await handle_voice_message(update, context, config)
    
    # Assertions
    assert ...
```

## Test Data Requirements

### Test Data Files

Test data is stored in `tests/data/` as JSON files:
- `test_*.json` - Test fixtures for various scenarios
- Used by message processing, formatting, and validation tests

### Using Test Data

```python
import json
from pathlib import Path

def load_test_data(filename: str) -> dict:
    """Load test data from tests/data/ directory."""
    data_path = Path(__file__).parent.parent / "data" / filename
    with open(data_path) as f:
        return json.load(f)
```

## Test Coverage

### Running Coverage Reports

```bash
# Generate HTML coverage report
poetry run pytest --cov=essence --cov-report=html

# View report
open htmlcov/index.html
```

### Coverage Goals

- **Target:** >80% code coverage
- **Critical paths:** 100% coverage
- **Error handling:** All error paths tested

## Continuous Integration

Tests are designed to run in CI/CD pipelines:

```yaml
# Example CI configuration
test:
  script:
    - poetry run pytest -v --cov=essence --cov-report=xml
  coverage: '/TOTAL.*\s+(\d+%)$/'
```

## Best Practices

1. **Test Isolation:** Each test should be independent
2. **Use Mocks:** Mock external dependencies (gRPC, HTTP, databases)
3. **Clear Assertions:** Use descriptive assertion messages
4. **Test Data:** Use fixtures and test data files, not hardcoded values
5. **Async Tests:** Use `@pytest.mark.asyncio` for async test functions
6. **Error Cases:** Test both success and error paths
7. **Performance:** Mark slow tests with `@pytest.mark.slow`

## Troubleshooting

### Common Issues

1. **Import Errors:**
   - Ensure `essence` package is installed: `poetry install`
   - Check PYTHONPATH if running tests directly

2. **Missing Dependencies:**
   - Run `poetry install` to install all dependencies
   - Check `pyproject.toml` for required packages

3. **Test Failures:**
   - Check test isolation (tests shouldn't share state)
   - Verify mocks are properly configured
   - Check test data files exist

4. **Slow Tests:**
   - Use `-m "not slow"` to skip slow tests during development
   - Optimize test setup/teardown

### Debugging Tests

```bash
# Run with verbose output and print statements
poetry run pytest -v -s tests/path/to/test.py

# Run specific test function
poetry run pytest tests/path/to/test.py::test_function_name -v

# Run with pdb debugger on failure
poetry run pytest --pdb tests/path/to/test.py
```

## Test Categories

### Unit Tests
- Test individual functions and classes
- Mock external dependencies
- Fast execution (< 1 second per test)

### Integration Tests
- Test service interactions
- May require running services (or comprehensive mocks)
- Slower execution (may take several seconds)

### End-to-End Tests
- Test complete workflows
- Require full system setup
- Marked with `@pytest.mark.slow`

## Related Documentation

- **Agentic Tests:** See `tests/agentic/README.md` for agentic capabilities testing
- **Service Documentation:** See service-specific README files in `services/` directories
- **Development Guide:** See `docs/guides/AGENTS.md` for development practices
