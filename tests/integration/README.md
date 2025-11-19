# Integration Tests

This directory contains integration tests for the June project. These tests verify end-to-end functionality with real services.

## Test Files

### Active Tests

1. **`test_llm_grpc_endpoints.py`**
   - Tests LLM gRPC endpoints (Generate and Chat) with Qwen3-30B-A3B
   - **Dependencies:** TensorRT-LLM (gRPC on port 8000, default) or inference-api service (gRPC on port 50051, legacy)
   - **Status:** ✅ Active - No gateway dependency
   - **Can run in background:** Yes (pytest-based)

2. **`test_voice_message_integration.py`**
   - Tests complete voice message flow: Audio → STT → LLM → TTS → Audio
   - **Dependencies:** STT, TTS, TensorRT-LLM (gRPC on port 8000, default) or Inference API (gRPC on port 50051, legacy), Gateway (optional - tests will skip if unavailable)
   - **Status:** ✅ Active - Gateway tests will skip if gateway not available
   - **Can run in background:** Yes (pytest-based)
   - **Note:** Some tests use gateway endpoints, but these will be skipped if gateway is not available

3. **`test_telegram_bot_qwen3_integration.py`**
   - Tests Telegram bot with Qwen3-30B-A3B: Voice → STT → LLM (Qwen3) → TTS → Voice
   - **Dependencies:** STT, TTS, TensorRT-LLM (gRPC on port 8000, default) or Inference API (gRPC on port 50051, legacy), Gateway (optional - tests will skip if unavailable)
   - **Status:** ✅ Active - Gateway tests will skip if gateway not available
   - **Can run in background:** Yes (pytest-based)
   - **Note:** Some tests use gateway endpoints, but these will be skipped if gateway is not available

### Obsolete Tests

4. **`test_system_integration.py`**
   - Tests Gateway service integration
   - **Dependencies:** Gateway service (removed)
   - **Status:** ❌ Obsolete - Gateway service has been removed
   - **Action:** Should be removed or updated to test services directly

## Running Integration Tests

### Via Integration Test Service (Recommended)

The integration test service runs tests in the background and provides a REST API for managing test runs.

```bash
# Start the integration test service
poetry run python -m essence integration-test-service

# In another terminal, start a test run
curl -X POST http://localhost:8082/tests/run

# Check status
curl http://localhost:8082/tests/status/<run_id>

# Get results
curl http://localhost:8082/tests/results/<run_id>
```

See `docs/guides/TESTING.md` for complete documentation.

### Direct Execution (Development)

For development and debugging, you can run tests directly:

```bash
# Run all integration tests
poetry run pytest tests/integration/ -v

# Run specific test file
poetry run pytest tests/integration/test_llm_grpc_endpoints.py -v

# Run specific test
poetry run pytest tests/integration/test_llm_grpc_endpoints.py::test_generate_simple -v
```

## Service Requirements

Integration tests require running services:

- **STT service** - gRPC on port 50052 (default)
- **TTS service** - gRPC on port 50053 (default)
- **TensorRT-LLM** - gRPC on port 8000 (default, in home_infra/shared-network)
- **Inference API** - gRPC on port 50051 (legacy, available via `--profile legacy`)
- **Gateway service** - HTTP on port 8000 (optional, tests will skip if unavailable)

Service addresses can be overridden via environment variables:
- `STT_SERVICE_ADDRESS` - STT service address
- `TTS_SERVICE_ADDRESS` - TTS service address
- `INFERENCE_API_URL` or `LLM_URL` - LLM service address (default: tensorrt-llm:8000 for TensorRT-LLM, can use inference-api:50051 for legacy)
- `GATEWAY_URL` - Gateway service URL (optional)

## Test Structure

All integration tests:
- Use pytest framework
- Can run in background (not blocking)
- Check service availability before running
- Skip tests if required services are unavailable
- Use real services (not mocks) for end-to-end testing

## Background Execution

All integration tests are designed to run in the background:
- Tests use pytest which supports background execution
- The integration test service runs tests via subprocess
- Tests can be started and checked periodically via REST API
- Test results are stored and retrievable via API

## Migration Status

✅ **Phase 12 Task 2: Migrate existing integration tests**

- ✅ **Identified current integration tests:**
  - 4 test files identified
  - 1 obsolete (test_system_integration.py - gateway tests)
  - 3 active (test_llm_grpc_endpoints.py, test_voice_message_integration.py, test_telegram_bot_qwen3_integration.py)

- ✅ **Ensured they can run in background:**
  - All tests are pytest-based and can run in background
  - Integration test service runs them via subprocess
  - Tests check service availability and skip if services unavailable

- ✅ **Updated to use test service API:**
  - Tests don't need changes - they work as-is via pytest
  - Integration test service runs them via `poetry run pytest`
  - Test service API provides management interface (start, status, results, logs)

## Next Steps

1. **Remove or update obsolete tests:**
   - `test_system_integration.py` should be removed or updated to test services directly (without gateway)

2. **Optional: Remove gateway dependencies:**
   - `test_voice_message_integration.py` and `test_telegram_bot_qwen3_integration.py` have gateway tests
   - These tests already skip if gateway is unavailable, so they're safe to keep
   - Could be updated to test services directly via gRPC instead of gateway
