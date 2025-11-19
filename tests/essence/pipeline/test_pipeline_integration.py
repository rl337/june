"""
Integration tests for pipeline framework with real services.

These tests use the PipelineTestFramework with real services when available.
They will skip if services are not running.
"""
import pytest
import os
from tests.essence.pipeline.test_pipeline_framework import PipelineTestFramework


@pytest.fixture
def pipeline_framework_real():
    """Fixture providing a pipeline test framework with real services."""
    return PipelineTestFramework(use_real_services=True)


@pytest.mark.asyncio
async def test_pipeline_with_real_services(pipeline_framework_real):
    """Test complete pipeline with real services (if available)."""
    # Generate test audio
    audio_data = pipeline_framework_real.generate_test_audio("Hello world", duration_seconds=1.0)
    
    # Run pipeline (will check service availability)
    metrics = await pipeline_framework_real.run_pipeline(
        audio_data,
        check_services=True
    )
    
    # If services are not available, skip the test
    if metrics.errors and "not available" in str(metrics.errors):
        pytest.skip("Real services not available - skipping integration test")
    
    # Assert success
    pipeline_framework_real.assert_pipeline_success(metrics)
    
    # Verify metrics
    assert metrics.stt_transcript
    assert metrics.llm_response
    assert metrics.tts_audio_size > 0
    assert metrics.total_duration > 0


@pytest.mark.asyncio
async def test_pipeline_performance_with_real_services(pipeline_framework_real):
    """Test pipeline performance with real services."""
    # Generate test audio
    audio_data = pipeline_framework_real.generate_test_audio("Test performance", duration_seconds=1.0)
    
    # Run pipeline
    metrics = await pipeline_framework_real.run_pipeline(audio_data)
    
    # If services are not available, skip the test
    if metrics.errors and "not available" in str(metrics.errors):
        pytest.skip("Real services not available - skipping integration test")
    
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
