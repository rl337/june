"""
Comprehensive test suite for TTS service.
"""
import pytest
import asyncio
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import torch
import grpc
from grpc import aio

# Import generated protobuf classes
import sys
sys.path.append('../../proto')
from tts_pb2 import (
    SynthesisRequest, SynthesisConfig, AudioChunk, AudioResponse,
    HealthRequest, HealthResponse
)
import tts_pb2_grpc

from main import TTSService, tts_service

@pytest.fixture
def mock_tts_model():
    """Mock TTS model."""
    mock_model = MagicMock()
    mock_model.tts = MagicMock(return_value=np.array([0.1, 0.2, 0.3, 0.4, 0.5]))
    mock_model.to = MagicMock(return_value=mock_model)
    return mock_model

@pytest.fixture
def mock_nats_client():
    """Mock NATS client."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    return mock_nats

@pytest.fixture
def service_instance(mock_tts_model, mock_nats_client):
    """Create service instance with mocked dependencies."""
    service = TTSService()
    service.tts_model = mock_tts_model
    service.nats_client = mock_nats_client
    return service

class TestSynthesisStream:
    """Test streaming synthesis functionality."""
    
    @pytest.mark.asyncio
    async def test_synthesize_stream_success(self, service_instance):
        """Test successful streaming synthesis."""
        requests = [
            SynthesisRequest(
                text="Hello world",
                voice_id="default",
                language="en",
                config=SynthesisConfig(
                    speed=1.0,
                    pitch=0.0,
                    energy=1.0,
                    prosody="neutral"
                ),
                stream=True
            ),
            SynthesisRequest(
                text="How are you?",
                voice_id="default",
                language="en",
                config=SynthesisConfig(
                    speed=1.0,
                    pitch=0.0,
                    energy=1.0,
                    prosody="neutral"
                ),
                stream=True
            )
        ]
        
        async def request_generator():
            for request in requests:
                yield request
        
        chunks = []
        async for chunk in service_instance.SynthesizeStream(request_generator(), None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        assert chunks[-1].sample_rate == service_instance.sample_rate
        assert chunks[-1].encoding == "pcm16"
    
    @pytest.mark.asyncio
    async def test_synthesize_stream_empty_text(self, service_instance):
        """Test streaming synthesis with empty text."""
        requests = [
            SynthesisRequest(
                text="",
                voice_id="default",
                language="en",
                config=SynthesisConfig(),
                stream=True
            )
        ]
        
        async def request_generator():
            for request in requests:
                yield request
        
        chunks = []
        async for chunk in service_instance.SynthesizeStream(request_generator(), None):
            chunks.append(chunk)
        
        # Should return empty chunk for empty text
        assert len(chunks) == 1
        assert chunks[0].audio_data == b""
    
    @pytest.mark.asyncio
    async def test_synthesize_stream_error(self, service_instance):
        """Test streaming synthesis with error."""
        # Mock TTS error
        service_instance.tts_model.tts.side_effect = Exception("TTS error")
        
        requests = [
            SynthesisRequest(
                text="Hello world",
                voice_id="default",
                language="en",
                config=SynthesisConfig(),
                stream=True
            )
        ]
        
        async def request_generator():
            for request in requests:
                yield request
        
        chunks = []
        async for chunk in service_instance.SynthesizeStream(request_generator(), None):
            chunks.append(chunk)
        
        assert len(chunks) == 1
        assert chunks[0].is_final is True
        assert chunks[0].audio_data == b""

class TestSynthesisOneShot:
    """Test one-shot synthesis functionality."""
    
    @pytest.mark.asyncio
    async def test_synthesize_success(self, service_instance):
        """Test successful one-shot synthesis."""
        request = SynthesisRequest(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig(
                speed=1.0,
                pitch=0.0,
                energy=1.0,
                prosody="neutral"
            ),
            stream=False
        )
        
        response = await service_instance.Synthesize(request, None)
        
        assert len(response.audio_data) > 0
        assert response.sample_rate == service_instance.sample_rate
        assert response.encoding == "pcm16"
        assert response.duration_ms > 0
    
    @pytest.mark.asyncio
    async def test_synthesize_empty_text(self, service_instance):
        """Test one-shot synthesis with empty text."""
        request = SynthesisRequest(
            text="",
            voice_id="default",
            language="en",
            config=SynthesisConfig(),
            stream=False
        )
        
        response = await service_instance.Synthesize(request, None)
        
        assert len(response.audio_data) == 0
        assert response.duration_ms == 0
    
    @pytest.mark.asyncio
    async def test_synthesize_error(self, service_instance):
        """Test one-shot synthesis with error."""
        # Mock TTS error
        service_instance.tts_model.tts.side_effect = Exception("TTS error")
        
        request = SynthesisRequest(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig(),
            stream=False
        )
        
        context = MagicMock()
        response = await service_instance.Synthesize(request, context)
        
        assert len(response.audio_data) == 0
        context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)

class TestHealthCheck:
    """Test health check functionality."""
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, service_instance):
        """Test health check when all services are healthy."""
        with patch.object(service_instance, '_check_model_health', return_value=True), \
             patch.object(service_instance, '_check_nats_health', return_value=True):
            
            request = HealthRequest()
            response = await service_instance.HealthCheck(request, None)
            
            assert response.healthy is True
            assert response.version == "0.2.0"
            assert len(response.available_voices) > 0
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, service_instance):
        """Test health check when services are unhealthy."""
        with patch.object(service_instance, '_check_model_health', return_value=False), \
             patch.object(service_instance, '_check_nats_health', return_value=True):
            
            request = HealthRequest()
            response = await service_instance.HealthCheck(request, None)
            
            assert response.healthy is False

class TestTextSynthesis:
    """Test text synthesis functionality."""
    
    @pytest.mark.asyncio
    async def test_synthesize_text_success(self, service_instance):
        """Test successful text synthesis."""
        audio_data = await service_instance._synthesize_text(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig()
        )
        
        assert audio_data is not None
        assert len(audio_data) > 0
        assert isinstance(audio_data, np.ndarray)
        assert np.max(np.abs(audio_data)) <= 1.0  # Normalized audio
    
    @pytest.mark.asyncio
    async def test_synthesize_text_empty(self, service_instance):
        """Test text synthesis with empty text."""
        audio_data = await service_instance._synthesize_text(
            text="",
            voice_id="default",
            language="en",
            config=SynthesisConfig()
        )
        
        assert audio_data is None
    
    @pytest.mark.asyncio
    async def test_synthesize_text_whitespace(self, service_instance):
        """Test text synthesis with whitespace-only text."""
        audio_data = await service_instance._synthesize_text(
            text="   \n\t   ",
            voice_id="default",
            language="en",
            config=SynthesisConfig()
        )
        
        assert audio_data is None
    
    @pytest.mark.asyncio
    async def test_synthesize_text_error(self, service_instance):
        """Test text synthesis with error."""
        service_instance.tts_model.tts.side_effect = Exception("Synthesis error")
        
        audio_data = await service_instance._synthesize_text(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig()
        )
        
        assert audio_data is None
    
    @pytest.mark.asyncio
    async def test_synthesize_text_tensor_output(self, service_instance):
        """Test text synthesis with tensor output."""
        # Mock tensor output
        tensor_output = torch.tensor([0.1, 0.2, 0.3, 0.4, 0.5])
        service_instance.tts_model.tts.return_value = tensor_output
        
        audio_data = await service_instance._synthesize_text(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig()
        )
        
        assert audio_data is not None
        assert isinstance(audio_data, np.ndarray)
        assert len(audio_data) == 5
    
    @pytest.mark.asyncio
    async def test_synthesize_text_multidimensional(self, service_instance):
        """Test text synthesis with multidimensional output."""
        # Mock multidimensional output
        multidimensional_output = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        service_instance.tts_model.tts.return_value = multidimensional_output
        
        audio_data = await service_instance._synthesize_text(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig()
        )
        
        assert audio_data is not None
        assert len(audio_data) == 6  # Flattened
        assert audio_data.shape == (6,)

class TestBasicSynthesis:
    """Test basic synthesis fallback functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_synthesis_success(self, service_instance):
        """Test successful basic synthesis."""
        # Remove TTS model to trigger fallback
        service_instance.tts_model = None
        
        audio_data = await service_instance._basic_synthesis(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig(speed=1.0, pitch=0.0)
        )
        
        assert audio_data is not None
        assert len(audio_data) > 0
        assert isinstance(audio_data, np.ndarray)
        assert audio_data.dtype == np.float32
    
    @pytest.mark.asyncio
    async def test_basic_synthesis_speed_factor(self, service_instance):
        """Test basic synthesis with speed factor."""
        service_instance.tts_model = None
        
        # Test different speed factors
        configs = [
            SynthesisConfig(speed=0.5),  # Slower
            SynthesisConfig(speed=1.0),  # Normal
            SynthesisConfig(speed=2.0),  # Faster
        ]
        
        durations = []
        for config in configs:
            audio_data = await service_instance._basic_synthesis(
                text="Hello world",
                voice_id="default",
                language="en",
                config=config
            )
            duration = len(audio_data) / service_instance.sample_rate
            durations.append(duration)
        
        # Faster speed should produce shorter audio
        assert durations[2] < durations[1] < durations[0]
    
    @pytest.mark.asyncio
    async def test_basic_synthesis_pitch_variation(self, service_instance):
        """Test basic synthesis with pitch variation."""
        service_instance.tts_model = None
        
        config = SynthesisConfig(pitch=0.5)
        
        audio_data = await service_instance._basic_synthesis(
            text="Hello world",
            voice_id="default",
            language="en",
            config=config
        )
        
        assert audio_data is not None
        assert len(audio_data) > 0
        # Should have some variation due to pitch
        assert np.std(audio_data) > 0

class TestModelLoading:
    """Test model loading functionality."""
    
    @pytest.mark.asyncio
    async def test_load_models_success(self, service_instance):
        """Test successful model loading."""
        with patch('main.TTS') as mock_tts_class:
            mock_tts_class.return_value = mock_tts_model
            
            await service_instance._load_models()
            
            assert service_instance.tts_model is not None
    
    @pytest.mark.asyncio
    async def test_load_models_error(self, service_instance):
        """Test model loading with error."""
        with patch('main.TTS') as mock_tts_class:
            mock_tts_class.side_effect = Exception("Model loading error")
            
            await service_instance._load_models()
            
            # Should fall back to None and log warning
            assert service_instance.tts_model is None
    
    @pytest.mark.asyncio
    async def test_load_models_cuda_device(self, service_instance):
        """Test model loading with CUDA device."""
        with patch('main.TTS') as mock_tts_class, \
             patch('main.torch.cuda.is_available', return_value=True):
            
            mock_model = MagicMock()
            mock_model.to = MagicMock(return_value=mock_model)
            mock_tts_class.return_value = mock_model
            
            await service_instance._load_models()
            
            assert service_instance.tts_model is not None
            mock_model.to.assert_called_once_with(service_instance.device)

class TestServiceConnections:
    """Test service connection functionality."""
    
    @pytest.mark.asyncio
    async def test_connect_services_success(self, service_instance):
        """Test successful service connections."""
        with patch('main.nats.connect') as mock_nats:
            mock_nats.return_value = mock_nats_client
            
            await service_instance._connect_services()
            
            assert service_instance.nats_client is not None
    
    @pytest.mark.asyncio
    async def test_connect_services_error(self, service_instance):
        """Test service connections with error."""
        with patch('main.nats.connect') as mock_nats:
            mock_nats.side_effect = Exception("Connection error")
            
            with pytest.raises(Exception):
                await service_instance._connect_services()

class TestHealthChecks:
    """Test individual health check methods."""
    
    @pytest.mark.asyncio
    async def test_check_model_health_healthy(self, service_instance):
        """Test model health check when healthy."""
        service_instance.tts_model = mock_tts_model
        
        is_healthy = await service_instance._check_model_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_model_health_unhealthy(self, service_instance):
        """Test model health check when unhealthy."""
        service_instance.tts_model = None
        
        is_healthy = await service_instance._check_model_health()
        assert is_healthy is False
    
    @pytest.mark.asyncio
    async def test_check_nats_health_healthy(self, service_instance):
        """Test NATS health check when healthy."""
        is_healthy = await service_instance._check_nats_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_nats_health_unhealthy(self, service_instance):
        """Test NATS health check when unhealthy."""
        service_instance.nats_client = None
        
        is_healthy = await service_instance._check_nats_health()
        assert is_healthy is False

class TestAudioProcessing:
    """Test audio processing functionality."""
    
    @pytest.mark.asyncio
    async def test_audio_chunk_generation(self, service_instance):
        """Test audio chunk generation for streaming."""
        # Generate test audio data
        audio_data = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        
        # Mock the synthesis method
        service_instance._synthesize_text = AsyncMock(return_value=audio_data)
        
        request = SynthesisRequest(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig(),
            stream=True
        )
        
        async def request_generator():
            yield request
        
        chunks = []
        async for chunk in service_instance.SynthesizeStream(request_generator(), None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert all(chunk.sample_rate == service_instance.sample_rate for chunk in chunks)
        assert all(chunk.encoding == "pcm16" for chunk in chunks)
        assert chunks[-1].is_final is True
    
    @pytest.mark.asyncio
    async def test_audio_response_generation(self, service_instance):
        """Test audio response generation for one-shot."""
        # Generate test audio data
        audio_data = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        
        # Mock the synthesis method
        service_instance._synthesize_text = AsyncMock(return_value=audio_data)
        
        request = SynthesisRequest(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig(),
            stream=False
        )
        
        response = await service_instance.Synthesize(request, None)
        
        assert len(response.audio_data) > 0
        assert response.sample_rate == service_instance.sample_rate
        assert response.encoding == "pcm16"
        assert response.duration_ms > 0

# Integration tests
class TestTTSIntegration:
    """Integration tests for TTS service."""
    
    @pytest.mark.asyncio
    async def test_full_streaming_flow(self, service_instance):
        """Test complete streaming synthesis flow."""
        requests = [
            SynthesisRequest(
                text="Hello",
                voice_id="default",
                language="en",
                config=SynthesisConfig(speed=1.0, pitch=0.0),
                stream=True
            ),
            SynthesisRequest(
                text="world",
                voice_id="default",
                language="en",
                config=SynthesisConfig(speed=1.0, pitch=0.0),
                stream=True
            )
        ]
        
        async def request_generator():
            for request in requests:
                yield request
        
        chunks = []
        async for chunk in service_instance.SynthesizeStream(request_generator(), None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        assert chunks[-1].sample_rate == service_instance.sample_rate
    
    @pytest.mark.asyncio
    async def test_full_one_shot_flow(self, service_instance):
        """Test complete one-shot synthesis flow."""
        request = SynthesisRequest(
            text="Hello world, this is a test of the TTS system.",
            voice_id="default",
            language="en",
            config=SynthesisConfig(
                speed=1.0,
                pitch=0.0,
                energy=1.0,
                prosody="neutral",
                enable_ssml=False
            ),
            stream=False
        )
        
        response = await service_instance.Synthesize(request, None)
        
        assert len(response.audio_data) > 0
        assert response.sample_rate == service_instance.sample_rate
        assert response.encoding == "pcm16"
        assert response.duration_ms > 0
        
        # Verify audio data is valid PCM16
        audio_array = np.frombuffer(response.audio_data, dtype=np.int16)
        assert len(audio_array) > 0
        assert np.max(np.abs(audio_array)) <= 32767  # PCM16 range
    
    @pytest.mark.asyncio
    async def test_different_voices(self, service_instance):
        """Test synthesis with different voices."""
        voices = ["default", "female", "male"]
        
        for voice in voices:
            request = SynthesisRequest(
                text=f"Hello, this is the {voice} voice.",
                voice_id=voice,
                language="en",
                config=SynthesisConfig(),
                stream=False
            )
            
            response = await service_instance.Synthesize(request, None)
            
            assert len(response.audio_data) > 0
            assert response.sample_rate == service_instance.sample_rate
    
    @pytest.mark.asyncio
    async def test_different_languages(self, service_instance):
        """Test synthesis with different languages."""
        languages = ["en", "es", "fr", "de"]
        
        for lang in languages:
            request = SynthesisRequest(
                text="Hello world",
                voice_id="default",
                language=lang,
                config=SynthesisConfig(),
                stream=False
            )
            
            response = await service_instance.Synthesize(request, None)
            
            assert len(response.audio_data) > 0
            assert response.sample_rate == service_instance.sample_rate
    
    @pytest.mark.asyncio
    async def test_prosody_variations(self, service_instance):
        """Test synthesis with different prosody settings."""
        prosodies = ["neutral", "happy", "sad", "angry", "excited"]
        
        for prosody in prosodies:
            request = SynthesisRequest(
                text="Hello world",
                voice_id="default",
                language="en",
                config=SynthesisConfig(
                    speed=1.0,
                    pitch=0.0,
                    energy=1.0,
                    prosody=prosody
                ),
                stream=False
            )
            
            response = await service_instance.Synthesize(request, None)
            
            assert len(response.audio_data) > 0
            assert response.sample_rate == service_instance.sample_rate

if __name__ == "__main__":
    pytest.main([__file__, "-v"])


