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
        language: Optional[str] = None,
        check_services: bool = True
    ) -> PipelineMetrics:
        """Run the complete pipeline: STT → LLM → TTS.
        
        Args:
            audio_data: Raw PCM audio data (will be converted to WAV for real STT)
            user_id: User ID for context
            chat_id: Chat ID for context
            language: Language code (e.g., 'en', 'es')
            check_services: If True and use_real_services, check service availability first
        
        Returns:
            PipelineMetrics with execution results and metrics
        """
        start_time = time.time()
        self.metrics = PipelineMetrics()
        
        # Check service availability if using real services
        if self.use_real_services and check_services:
            import os
            stt_address = os.getenv("STT_SERVICE_ADDRESS", "localhost:50052")
            tts_address = os.getenv("TTS_SERVICE_ADDRESS", "localhost:50053")
            llm_address = os.getenv("INFERENCE_API_URL", os.getenv("LLM_URL", "tensorrt-llm:8000")).replace("grpc://", "")
            
            stt_available = await self.check_service_available(stt_address, "STT")
            tts_available = await self.check_service_available(tts_address, "TTS")
            llm_available = await self.check_service_available(llm_address, "LLM")
            
            if not (stt_available and tts_available and llm_available):
                self.metrics.errors.append("One or more services are not available")
                self.metrics.warnings.append(f"STT: {stt_available}, TTS: {tts_available}, LLM: {llm_available}")
                return self.metrics
        
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
        
        except ImportError as e:
            # Handle missing dependencies gracefully
            self.metrics.errors.append(f"Missing dependencies for real services: {str(e)}")
            self.metrics.warnings.append("Install grpc and june_grpc_api packages to use real services")
            self.metrics.total_duration = time.time() - start_time
            return self.metrics
        except Exception as e:
            self.metrics.errors.append(f"Pipeline error: {str(e)}")
            self.metrics.total_duration = time.time() - start_time
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            return self.metrics
    
    def create_wav_file(self, audio_data: bytes, sample_rate: int = 16000) -> bytes:
        """Create a WAV file from raw PCM audio data."""
        import struct
        num_samples = len(audio_data) // 2  # 16-bit = 2 bytes per sample
        data_size = len(audio_data)
        file_size = 36 + data_size
        
        wav = b'RIFF'
        wav += struct.pack('<I', file_size)
        wav += b'WAVE'
        wav += b'fmt '
        wav += struct.pack('<I', 16)  # fmt chunk size
        wav += struct.pack('<HHIIHH', 1, 1, sample_rate, sample_rate * 2, 2, 16)  # PCM, mono, sample_rate
        wav += b'data'
        wav += struct.pack('<I', data_size)
        wav += audio_data
        
        return wav
    
    async def check_service_available(self, address: str, service_type: str) -> bool:
        """Check if a gRPC service is available."""
        try:
            import grpc
        except ImportError:
            logger.warning(f"grpc module not available - cannot check {service_type} service")
            return False
        
        try:
            async with grpc.aio.insecure_channel(address) as channel:
                # Try to connect
                await asyncio.wait_for(
                    grpc.channel_ready_future(channel),
                    timeout=2.0
                )
                logger.info(f"✓ {service_type} service reachable at {address}")
                return True
        except Exception as e:
            logger.warning(f"✗ {service_type} service not reachable at {address}: {e}")
            return False
    
    async def _real_stt_recognize(self, audio_data: bytes, language: Optional[str] = None) -> str:
        """Use real STT service (requires gRPC)."""
        import os
        try:
            import grpc
            from june_grpc_api import asr as asr_shim
        except ImportError as e:
            raise ImportError(f"Required modules not available for real STT service: {e}")
        
        stt_address = os.getenv("STT_SERVICE_ADDRESS", "localhost:50052")
        sample_rate = 16000
        
        # Convert raw audio to WAV format if needed
        if not audio_data.startswith(b'RIFF'):
            audio_data = self.create_wav_file(audio_data, sample_rate)
        
        try:
            async with grpc.aio.insecure_channel(stt_address) as channel:
                client = asr_shim.SpeechToTextClient(channel)
                cfg = asr_shim.RecognitionConfig(
                    language=language,
                    interim_results=False
                )
                result = await client.recognize(
                    audio_data,
                    sample_rate=sample_rate,
                    encoding="wav",
                    config=cfg
                )
                return result.transcript or ""
        except Exception as e:
            logger.error(f"STT service error: {e}", exc_info=True)
            raise
    
    async def _real_llm_chat(self, messages: List[Dict[str, str]]) -> str:
        """Use real LLM service (requires gRPC)."""
        import os
        try:
            import grpc
            from june_grpc_api import llm as llm_shim
        except ImportError as e:
            raise ImportError(f"Required modules not available for real LLM service: {e}")
        
        # Default: TensorRT-LLM (tensorrt-llm:8000), Legacy: inference-api (inference-api:50051)
        llm_address = os.getenv("INFERENCE_API_URL", os.getenv("LLM_URL", "tensorrt-llm:8000")).replace("grpc://", "")
        
        try:
            async with grpc.aio.insecure_channel(llm_address) as channel:
                client = llm_shim.LLMClient(channel)
                llm_response = ""
                async for chunk in client.chat_stream(messages):
                    llm_response += chunk
                return llm_response
        except Exception as e:
            logger.error(f"LLM service error: {e}", exc_info=True)
            raise
    
    async def _real_tts_synthesize(self, text: str, language: str = "en") -> bytes:
        """Use real TTS service (requires gRPC)."""
        import os
        try:
            import grpc
            from june_grpc_api import tts as tts_shim
        except ImportError as e:
            raise ImportError(f"Required modules not available for real TTS service: {e}")
        
        tts_address = os.getenv("TTS_SERVICE_ADDRESS", "localhost:50053")
        
        try:
            async with grpc.aio.insecure_channel(tts_address) as channel:
                client = tts_shim.TextToSpeechClient(channel)
                cfg = tts_shim.SynthesisConfig(
                    sample_rate=16000,
                    speed=1.0,
                    pitch=0.0
                )
                audio = await client.synthesize(
                    text=text,
                    voice_id="default",
                    language=language,
                    config=cfg
                )
                return audio
        except Exception as e:
            logger.error(f"TTS service error: {e}", exc_info=True)
            raise
    
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
