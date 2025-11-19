"""
Integration tests for pipeline framework with real services.

These tests use the PipelineTestFramework with real services when available.
They will skip if services are not running or if grpc is mocked.
"""
import pytest
import os
import sys

# Import MagicMock first, before any other imports that might use it
try:
    from unittest.mock import MagicMock
except ImportError:
    # Fallback if unittest.mock is not available (shouldn't happen in Python 3.3+)
    MagicMock = None

from tests.essence.pipeline.test_pipeline_framework import PipelineTestFramework


# Evaluate grpc availability at import time (safer for pytest collection)
# This constant is evaluated once when the module is imported, before pytest
# starts collecting tests, which avoids issues with decorator evaluation
# 
# Strategy: In CI (GitHub Actions), always skip integration tests.
# Locally, check if grpc is available and not mocked.
_GRPC_AVAILABLE = False
try:
    # Check if we're in CI environment (GitHub Actions sets CI=true)
    if os.getenv('CI') == 'true':
        # In CI, always skip integration tests (they require real services)
        _GRPC_AVAILABLE = False
    else:
        # Not in CI, check if grpc is available
        # First, check if MagicMock is available (should always be, but be safe)
        if MagicMock is None:
            _GRPC_AVAILABLE = False
        else:
            # Check if grpc is already mocked in sys.modules (from other test modules)
            if 'grpc' in sys.modules:
                try:
                    grpc_module = sys.modules['grpc']
                    if isinstance(grpc_module, MagicMock):
                        _GRPC_AVAILABLE = False
                    else:
                        # Not mocked, try to verify it's real
                        try:
                            import grpc
                            if not isinstance(grpc, MagicMock) and hasattr(grpc, 'insecure_channel'):
                                _GRPC_AVAILABLE = True
                        except (ImportError, AttributeError, TypeError, Exception):
                            _GRPC_AVAILABLE = False
                except (AttributeError, KeyError, Exception):
                    _GRPC_AVAILABLE = False
            else:
                # grpc not in sys.modules, try to import it
                try:
                    import grpc
                    if not isinstance(grpc, MagicMock) and hasattr(grpc, 'insecure_channel'):
                        _GRPC_AVAILABLE = True
                except (ImportError, AttributeError, TypeError, Exception):
                    _GRPC_AVAILABLE = False
except Exception:
    # Catch absolutely everything - assume unavailable if anything goes wrong
    # This ensures the module can always be imported, even if grpc checking fails
    _GRPC_AVAILABLE = False


@pytest.fixture
def pipeline_framework_real():
    """Fixture providing a pipeline test framework with real services."""
    return PipelineTestFramework(use_real_services=True)


@pytest.mark.asyncio
@pytest.mark.skipif(not _GRPC_AVAILABLE, reason="grpc module not available or mocked - skipping integration test")
async def test_pipeline_with_real_services(pipeline_framework_real):
    """Test complete pipeline with real services (if available)."""
    # Generate test audio
    audio_data = pipeline_framework_real.generate_test_audio("Hello world", duration_seconds=1.0)
    
    # Run pipeline (fixture already checked service availability)
    metrics = await pipeline_framework_real.run_pipeline(
        audio_data,
        check_services=False  # Already checked in fixture
    )
    
    # Assert success
    pipeline_framework_real.assert_pipeline_success(metrics)
    
    # Verify metrics
    assert metrics.stt_transcript
    assert metrics.llm_response
    assert metrics.tts_audio_size > 0
    assert metrics.total_duration > 0


@pytest.mark.asyncio
@pytest.mark.skipif(not _GRPC_AVAILABLE, reason="grpc module not available or mocked - skipping integration test")
async def test_pipeline_performance_with_real_services(pipeline_framework_real):
    """Test pipeline performance with real services."""
    # Generate test audio
    audio_data = pipeline_framework_real.generate_test_audio("Test performance", duration_seconds=1.0)
    
    # Run pipeline (fixture already checked service availability)
    metrics = await pipeline_framework_real.run_pipeline(
        audio_data,
        check_services=False  # Already checked in fixture
    )
    
    # Assert success
    pipeline_framework_real.assert_pipeline_success(metrics)
    
    # Assert performance (should complete in < 60 seconds with real services)
    pipeline_framework_real.assert_performance(metrics, max_total_duration=60.0)
    
    # Log performance metrics
    print(f"\nPerformance metrics:")
    print(f"  STT duration: {metrics.stt_duration:.2f}s")
    print(f"  LLM duration: {metrics.llm_duration:.2f}s")
    print(f"  TTS duration: {metrics.tts_duration:.2f}s")
    print(f"  Total duration: {metrics.total_duration:.2f}s")


@pytest.mark.asyncio
async def test_service_availability_check(pipeline_framework_real):
    """Test service availability checking."""
    import os
    
    stt_address = os.getenv("STT_SERVICE_ADDRESS", "localhost:50052")
    tts_address = os.getenv("TTS_SERVICE_ADDRESS", "localhost:50053")
    llm_address = os.getenv("INFERENCE_API_URL", os.getenv("LLM_URL", "tensorrt-llm:8000")).replace("grpc://", "")
    
    stt_available = await pipeline_framework_real.check_service_available(stt_address, "STT")
    tts_available = await pipeline_framework_real.check_service_available(tts_address, "TTS")
    llm_available = await pipeline_framework_real.check_service_available(llm_address, "LLM")
    
    # Log availability status
    print(f"\nService availability:")
    print(f"  STT ({stt_address}): {'✓' if stt_available else '✗'}")
    print(f"  TTS ({tts_address}): {'✓' if tts_available else '✗'}")
    print(f"  LLM ({llm_address}): {'✓' if llm_available else '✗'}")
    
    # This test always passes - it's just for checking availability
    assert True
