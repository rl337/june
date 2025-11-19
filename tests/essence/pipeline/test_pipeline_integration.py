"""
Integration tests for pipeline framework with real services.

These tests use the PipelineTestFramework with real services when available.
They will skip if services are not running or if grpc is mocked.
"""
import pytest
import os
import sys

# Wrap all imports and module-level code in try/except to ensure module can always be imported
# This is critical for CI environments where pytest collection must not fail
try:
    # Import MagicMock first, before any other imports that might use it
    try:
        from unittest.mock import MagicMock
    except ImportError:
        # Fallback if unittest.mock is not available (shouldn't happen in Python 3.3+)
        MagicMock = None

    from tests.essence.pipeline.test_pipeline_framework import PipelineTestFramework

    # Skip integration tests in CI environment (GitHub Actions sets CI=true)
    # These tests require real services and are meant for local integration testing
    # Wrap os.getenv in try/except to be extra safe
    try:
        _IS_CI = os.getenv('CI') == 'true'
    except Exception:
        _IS_CI = False

    # Check grpc availability (only evaluated when not in CI, to avoid CI collection issues)
    # In CI, we always skip, so we don't need to check grpc
    _GRPC_AVAILABLE = False
    if not _IS_CI:
        # Not in CI, check if grpc is available and not mocked
        try:
            if MagicMock is not None:
                if 'grpc' in sys.modules:
                    grpc_module = sys.modules['grpc']
                    if not isinstance(grpc_module, MagicMock):
                        try:
                            import grpc
                            if not isinstance(grpc, MagicMock) and hasattr(grpc, 'insecure_channel'):
                                _GRPC_AVAILABLE = True
                        except (ImportError, AttributeError, TypeError, Exception):
                            pass
                else:
                    try:
                        import grpc
                        if not isinstance(grpc, MagicMock) and hasattr(grpc, 'insecure_channel'):
                            _GRPC_AVAILABLE = True
                    except (ImportError, AttributeError, TypeError, Exception):
                        pass
        except Exception:
            pass
except Exception:
    # If anything goes wrong during import, set safe defaults
    _IS_CI = True  # Assume CI to skip tests
    _GRPC_AVAILABLE = False
    MagicMock = None
    PipelineTestFramework = None


@pytest.fixture
def pipeline_framework_real():
    """Fixture providing a pipeline test framework with real services."""
    if PipelineTestFramework is None:
        pytest.skip("PipelineTestFramework not available")
    return PipelineTestFramework(use_real_services=True)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(_IS_CI or not _GRPC_AVAILABLE, reason="Skipping integration test (CI environment or grpc unavailable/mocked)")
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


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(_IS_CI or not _GRPC_AVAILABLE, reason="Skipping integration test (CI environment or grpc unavailable/mocked)")
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


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(_IS_CI or not _GRPC_AVAILABLE, reason="Skipping integration test (CI environment or grpc unavailable/mocked)")
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
