"""
Basic pipeline tests for Phase 16.

Tests the complete voice message pipeline flow with mocked services.
"""
import pytest
import asyncio
from .test_pipeline_framework import (
    PipelineTestFramework,
    MockSTTResponse,
    MockLLMResponse,
    MockTTSResponse
)


class TestPipelineBasic:
    """Basic pipeline flow tests."""
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_flow(self, pipeline_framework):
        """Test complete pipeline: STT → LLM → TTS."""
        # Generate test audio
        audio_data = pipeline_framework.generate_test_audio("Hello world", duration_seconds=1.0)
        
        # Run pipeline
        metrics = await pipeline_framework.run_pipeline(audio_data)
        
        # Assert success
        pipeline_framework.assert_pipeline_success(metrics)
        
        # Verify metrics
        assert metrics.stt_transcript == "Hello world"
        assert metrics.llm_response == "This is a test response."
        assert metrics.tts_audio_size > 0
        assert metrics.total_duration > 0
    
    @pytest.mark.asyncio
    async def test_pipeline_with_custom_responses(self, pipeline_framework):
        """Test pipeline with custom mock responses."""
        # Set up custom responses
        stt_response = MockSTTResponse(transcript="What is the weather?", confidence=0.95)
        llm_response = MockLLMResponse(text="The weather is sunny today.")
        tts_response = MockTTSResponse(audio=b"mock_audio_data")
        
        framework = PipelineTestFramework(
            mock_stt=pipeline_framework.mock_stt,
            mock_llm=pipeline_framework.mock_llm,
            mock_tts=pipeline_framework.mock_tts
        )
        framework.mock_stt.responses = [stt_response]
        framework.mock_llm.responses = [llm_response]
        framework.mock_tts.responses = [tts_response]
        
        # Generate test audio
        audio_data = framework.generate_test_audio("What is the weather?", duration_seconds=2.0)
        
        # Run pipeline
        metrics = await framework.run_pipeline(audio_data)
        
        # Assert success
        framework.assert_pipeline_success(metrics)
        
        # Verify custom responses
        assert metrics.stt_transcript == "What is the weather?"
        assert metrics.llm_response == "The weather is sunny today."
    
    @pytest.mark.asyncio
    async def test_pipeline_performance(self, pipeline_framework):
        """Test pipeline performance metrics."""
        # Generate test audio
        audio_data = pipeline_framework.generate_test_audio("Test performance", duration_seconds=1.0)
        
        # Run pipeline
        metrics = await pipeline_framework.run_pipeline(audio_data)
        
        # Assert success
        pipeline_framework.assert_pipeline_success(metrics)
        
        # Assert performance (should complete in < 30 seconds with mocks)
        pipeline_framework.assert_performance(metrics, max_total_duration=30.0)
        
        # Verify individual stage durations
        assert metrics.stt_duration > 0
        assert metrics.llm_duration > 0
        assert metrics.tts_duration > 0
    
    @pytest.mark.asyncio
    async def test_pipeline_error_handling_stt_failure(self, pipeline_framework):
        """Test pipeline error handling when STT fails."""
        # Set up STT to return empty transcript
        stt_response = MockSTTResponse(transcript="", confidence=0.0)
        framework = PipelineTestFramework(
            mock_stt=pipeline_framework.mock_stt,
            mock_llm=pipeline_framework.mock_llm,
            mock_tts=pipeline_framework.mock_tts
        )
        framework.mock_stt.responses = [stt_response]
        
        # Generate test audio
        audio_data = framework.generate_test_audio("Test", duration_seconds=1.0)
        
        # Run pipeline
        metrics = await framework.run_pipeline(audio_data)
        
        # Assert error was recorded
        assert len(metrics.errors) > 0
        assert "STT returned empty transcript" in metrics.errors
        assert metrics.stt_transcript == ""
    
    @pytest.mark.asyncio
    async def test_pipeline_error_handling_llm_failure(self, pipeline_framework):
        """Test pipeline error handling when LLM fails."""
        # Set up LLM to return empty response
        llm_response = MockLLMResponse(text="")
        framework = PipelineTestFramework(
            mock_stt=pipeline_framework.mock_stt,
            mock_llm=pipeline_framework.mock_llm,
            mock_tts=pipeline_framework.mock_tts
        )
        framework.mock_llm.responses = [llm_response]
        
        # Generate test audio
        audio_data = framework.generate_test_audio("Test", duration_seconds=1.0)
        
        # Run pipeline
        metrics = await framework.run_pipeline(audio_data)
        
        # Assert error was recorded
        assert len(metrics.errors) > 0
        assert "LLM returned empty response" in metrics.errors
        assert metrics.llm_response == ""
    
    @pytest.mark.asyncio
    async def test_pipeline_error_handling_tts_failure(self, pipeline_framework):
        """Test pipeline error handling when TTS fails."""
        # Set up TTS to return empty audio
        tts_response = MockTTSResponse(audio=b"")
        framework = PipelineTestFramework(
            mock_stt=pipeline_framework.mock_stt,
            mock_llm=pipeline_framework.mock_llm,
            mock_tts=pipeline_framework.mock_tts
        )
        framework.mock_tts.responses = [tts_response]
        
        # Generate test audio
        audio_data = framework.generate_test_audio("Test", duration_seconds=1.0)
        
        # Run pipeline
        metrics = await framework.run_pipeline(audio_data)
        
        # Assert error was recorded
        assert len(metrics.errors) > 0
        assert "TTS returned empty audio" in metrics.errors
        assert metrics.tts_audio_size == 0
    
    @pytest.mark.asyncio
    async def test_pipeline_with_different_languages(self, pipeline_framework):
        """Test pipeline with different language settings."""
        # Test with English
        audio_data = pipeline_framework.generate_test_audio("Hello", duration_seconds=1.0)
        metrics_en = await pipeline_framework.run_pipeline(audio_data, language="en")
        pipeline_framework.assert_pipeline_success(metrics_en)
        
        # Test with Spanish (mock should handle it)
        metrics_es = await pipeline_framework.run_pipeline(audio_data, language="es")
        pipeline_framework.assert_pipeline_success(metrics_es)
        
        # Both should succeed
        assert metrics_en.stt_transcript
        assert metrics_es.stt_transcript
    
    @pytest.mark.asyncio
    async def test_pipeline_concurrent_requests(self, pipeline_framework):
        """Test pipeline with concurrent requests."""
        # Generate multiple test audio samples
        audio_samples = [
            pipeline_framework.generate_test_audio(f"Request {i}", duration_seconds=1.0)
            for i in range(5)
        ]
        
        # Run pipeline concurrently
        tasks = [
            pipeline_framework.run_pipeline(audio_data)
            for audio_data in audio_samples
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Assert all succeeded
        for metrics in results:
            pipeline_framework.assert_pipeline_success(metrics)
        
        # Verify all have results
        assert len(results) == 5
        assert all(m.stt_transcript for m in results)
        assert all(m.llm_response for m in results)
        assert all(m.tts_audio_size > 0 for m in results)
