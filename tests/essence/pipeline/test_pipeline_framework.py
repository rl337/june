"""
Test framework for Phase 16: End-to-End Pipeline Testing.

This framework provides utilities for testing the complete voice message pipeline:
- Voice → STT → LLM → TTS → Voice Response

Supports both mocked services (for CI/CD) and real services (for integration testing).
"""
import pytest
import asyncio
import time
import io
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
import logging

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    """Metrics collected during pipeline execution."""
    stt_duration: float = 0.0
    llm_duration: float = 0.0
    tts_duration: float = 0.0
    total_duration: float = 0.0
    stt_transcript: str = ""
    llm_response: str = ""
    tts_audio_size: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class MockSTTResponse:
    """Mock STT service response."""
    transcript: str
    confidence: float = 0.9
    is_final: bool = True
    detected_language: Optional[str] = None


@dataclass
class MockLLMResponse:
    """Mock LLM service response."""
    text: str
    finish_reason: str = "stop"


@dataclass
class MockTTSResponse:
    """Mock TTS service response."""
    audio: bytes
    sample_rate: int = 16000


class MockSTTService:
    """Mock STT service for testing."""
    
    def __init__(self, responses: Optional[List[MockSTTResponse]] = None):
        self.responses = responses or []
        self.call_count = 0
    
    async def recognize(self, audio_data: bytes, sample_rate: int = 16000, encoding: str = "wav", config=None) -> MockSTTResponse:
        """Mock STT recognition."""
        self.call_count += 1
        if self.responses:
            return self.responses[(self.call_count - 1) % len(self.responses)]
        # Default response
        return MockSTTResponse(transcript="Hello world", confidence=0.9)
    
    async def recognize_stream(self, audio_chunks, sample_rate: int = 16000, encoding: str = "wav", config=None):
        """Mock STT streaming recognition."""
        self.call_count += 1
        if self.responses:
            response = self.responses[(self.call_count - 1) % len(self.responses)]
            yield response
        else:
            # Default response
            yield MockSTTResponse(transcript="Hello world", confidence=0.9)


class MockLLMService:
    """Mock LLM service for testing."""
    
    def __init__(self, responses: Optional[List[MockLLMResponse]] = None):
        self.responses = responses or []
        self.call_count = 0
    
    async def chat_stream(self, messages: List[Dict[str, str]]):
        """Mock LLM streaming chat."""
        self.call_count += 1
        if self.responses:
            response = self.responses[(self.call_count - 1) % len(self.responses)]
        else:
            # Default response
            response = MockLLMResponse(text="This is a test response.")
        
        # Simulate streaming by yielding chunks
        text = response.text
        chunk_size = max(1, len(text) // 10)  # Split into ~10 chunks
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            yield chunk
            await asyncio.sleep(0.01)  # Simulate streaming delay


class MockTTSService:
    """Mock TTS service for testing."""
    
    def __init__(self, responses: Optional[List[MockTTSResponse]] = None):
        self.responses = responses or []
        self.call_count = 0
    
    async def synthesize(self, text: str, voice_id: str = "default", language: str = "en", config=None) -> bytes:
        """Mock TTS synthesis."""
        self.call_count += 1
        if self.responses:
            response = self.responses[(self.call_count - 1) % len(self.responses)]
            return response.audio
        
        # Generate mock audio (simple sine wave)
        import numpy as np
        sample_rate = 16000
        duration = max(0.5, len(text) * 0.1)  # Rough estimate: 0.1s per character
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        frequency = 440.0
        audio_samples = np.sin(2 * np.pi * frequency * t)
        audio_samples = (audio_samples * 32767).astype(np.int16)
        return audio_samples.tobytes()


class PipelineTestFramework:
    """Framework for testing the voice message pipeline."""
    
    def __init__(
        self,
        mock_stt: Optional[MockSTTService] = None,
        mock_llm: Optional[MockLLMService] = None,
        mock_tts: Optional[MockTTSService] = None,
        use_real_services: bool = False
    ):
        self.mock_stt = mock_stt or MockSTTService()
        self.mock_llm = mock_llm or MockLLMService()
        self.mock_tts = mock_tts or MockTTSService()
        self.use_real_services = use_real_services
        self.metrics = PipelineMetrics()
    
    async def run_pipeline(
        self,
        audio_data: bytes,
        user_id: str = "test_user",
        chat_id: str = "test_chat",
        language: Optional[str] = None
    ) -> PipelineMetrics:
        """Run the complete pipeline: STT → LLM → TTS."""
        start_time = time.time()
        self.metrics = PipelineMetrics()
        
        try:
            # Step 1: STT
            stt_start = time.time()
            if self.use_real_services:
                # Use real STT service (requires gRPC connection)
                transcript = await self._real_stt_recognize(audio_data, language)
            else:
                # Use mock STT
                stt_response = await self.mock_stt.recognize(audio_data)
                transcript = stt_response.transcript
            self.metrics.stt_duration = time.time() - stt_start
            self.metrics.stt_transcript = transcript
            
            if not transcript:
                self.metrics.errors.append("STT returned empty transcript")
                return self.metrics
            
            # Step 2: LLM
            llm_start = time.time()
            messages = [{"role": "user", "content": transcript}]
            if self.use_real_services:
                # Use real LLM service (requires gRPC connection)
                llm_response = await self._real_llm_chat(messages)
            else:
                # Use mock LLM
                llm_response = ""
                async for chunk in self.mock_llm.chat_stream(messages):
                    llm_response += chunk
            self.metrics.llm_duration = time.time() - llm_start
            self.metrics.llm_response = llm_response
            
            if not llm_response:
                self.metrics.errors.append("LLM returned empty response")
                return self.metrics
            
            # Step 3: TTS
            tts_start = time.time()
            if self.use_real_services:
                # Use real TTS service (requires gRPC connection)
                tts_audio = await self._real_tts_synthesize(llm_response, language or "en")
            else:
                # Use mock TTS
                tts_audio = await self.mock_tts.synthesize(llm_response, language=language or "en")
            self.metrics.tts_duration = time.time() - tts_start
            self.metrics.tts_audio_size = len(tts_audio)
            
            if not tts_audio:
                self.metrics.errors.append("TTS returned empty audio")
                return self.metrics
            
            self.metrics.total_duration = time.time() - start_time
            return self.metrics
        
        except Exception as e:
            self.metrics.errors.append(f"Pipeline error: {str(e)}")
            self.metrics.total_duration = time.time() - start_time
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            return self.metrics
    
    async def _real_stt_recognize(self, audio_data: bytes, language: Optional[str] = None) -> str:
        """Use real STT service (requires gRPC)."""
        # This would connect to real STT service
        # For now, raise NotImplementedError
        raise NotImplementedError("Real STT service not implemented in test framework")
    
    async def _real_llm_chat(self, messages: List[Dict[str, str]]) -> str:
        """Use real LLM service (requires gRPC)."""
        # This would connect to real LLM service
        # For now, raise NotImplementedError
        raise NotImplementedError("Real LLM service not implemented in test framework")
    
    async def _real_tts_synthesize(self, text: str, language: str = "en") -> bytes:
        """Use real TTS service (requires gRPC)."""
        # This would connect to real TTS service
        # For now, raise NotImplementedError
        raise NotImplementedError("Real TTS service not implemented in test framework")
    
    def assert_pipeline_success(self, metrics: PipelineMetrics):
        """Assert that pipeline executed successfully."""
        assert len(metrics.errors) == 0, f"Pipeline had errors: {metrics.errors}"
        assert metrics.stt_transcript, "STT transcript should not be empty"
        assert metrics.llm_response, "LLM response should not be empty"
        assert metrics.tts_audio_size > 0, "TTS audio should not be empty"
    
    def assert_performance(self, metrics: PipelineMetrics, max_total_duration: float = 30.0):
        """Assert that pipeline meets performance requirements."""
        assert metrics.total_duration < max_total_duration, \
            f"Pipeline took {metrics.total_duration}s, expected < {max_total_duration}s"
    
    def generate_test_audio(self, text: str = "Hello world", duration_seconds: float = 1.0) -> bytes:
        """Generate test audio data."""
        import numpy as np
        sample_rate = 16000
        sample_count = int(sample_rate * duration_seconds)
        t = np.linspace(0, duration_seconds, sample_count, False)
        frequency = 440.0
        audio_samples = np.sin(2 * np.pi * frequency * t)
        audio_samples = (audio_samples * 32767).astype(np.int16)
        return audio_samples.tobytes()


# Pytest fixtures are defined in conftest.py
