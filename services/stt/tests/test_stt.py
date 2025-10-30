"""
Comprehensive test suite for STT service.
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
from asr_pb2 import (
    AudioChunk, RecognitionRequest, RecognitionResponse, RecognitionResult,
    RecognitionConfig, WordInfo, HealthRequest, HealthResponse
)
import asr_pb2_grpc

from main import STTService, stt_service

@pytest.fixture
def mock_whisper_model():
    """Mock Whisper model."""
    mock_model = MagicMock()
    mock_model.transcribe = MagicMock(return_value={
        "text": "Hello world",
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 0.95},
                    {"word": "world", "start": 0.5, "end": 1.0, "probability": 0.90}
                ]
            }
        ]
    })
    return mock_model

@pytest.fixture
def mock_vad():
    """Mock WebRTC VAD."""
    mock_vad = MagicMock()
    mock_vad.is_speech = MagicMock(return_value=True)
    return mock_vad

@pytest.fixture
def mock_nats_client():
    """Mock NATS client."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    return mock_nats

@pytest.fixture
def service_instance(mock_whisper_model, mock_vad, mock_nats_client):
    """Create service instance with mocked dependencies."""
    service = STTService()
    service.whisper_model = mock_whisper_model
    service.vad = mock_vad
    service.nats_client = mock_nats_client
    return service

@pytest.fixture
def sample_audio_data():
    """Sample audio data for testing."""
    # Generate 1 second of sine wave at 440Hz
    sample_rate = 16000
    duration = 1.0
    frequency = 440.0
    
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio_data = np.sin(2 * np.pi * frequency * t)
    return (audio_data * 32767).astype(np.int16).tobytes()

class TestRecognitionStream:
    """Test streaming recognition functionality."""
    
    @pytest.mark.asyncio
    async def test_recognize_stream_success(self, service_instance, sample_audio_data):
        """Test successful streaming recognition."""
        # Create audio chunks
        chunks = [
            AudioChunk(
                audio_data=sample_audio_data[:len(sample_audio_data)//2],
                sample_rate=16000,
                channels=1,
                encoding="pcm",
                timestamp_us=0
            ),
            AudioChunk(
                audio_data=sample_audio_data[len(sample_audio_data)//2:],
                sample_rate=16000,
                channels=1,
                encoding="pcm",
                timestamp_us=500000  # 0.5 seconds
            )
        ]
        
        async def chunk_generator():
            for chunk in chunks:
                yield chunk
        
        results = []
        async for result in service_instance.RecognizeStream(chunk_generator(), None):
            results.append(result)
        
        assert len(results) > 0
        assert results[-1].is_final is True
        assert results[-1].transcript == "Hello world"
        assert results[-1].confidence > 0
    
    @pytest.mark.asyncio
    async def test_recognize_stream_empty_audio(self, service_instance):
        """Test streaming recognition with empty audio."""
        chunks = [
            AudioChunk(
                audio_data=b"",
                sample_rate=16000,
                channels=1,
                encoding="pcm",
                timestamp_us=0
            )
        ]
        
        async def chunk_generator():
            for chunk in chunks:
                yield chunk
        
        results = []
        async for result in service_instance.RecognizeStream(chunk_generator(), None):
            results.append(result)
        
        # Should return empty result for empty audio
        assert len(results) == 0 or (len(results) == 1 and results[0].transcript == "")
    
    @pytest.mark.asyncio
    async def test_recognize_stream_error(self, service_instance):
        """Test streaming recognition with error."""
        # Mock Whisper error
        service_instance.whisper_model.transcribe.side_effect = Exception("Whisper error")
        
        chunks = [
            AudioChunk(
                audio_data=b"test audio data",
                sample_rate=16000,
                channels=1,
                encoding="pcm",
                timestamp_us=0
            )
        ]
        
        async def chunk_generator():
            for chunk in chunks:
                yield chunk
        
        results = []
        async for result in service_instance.RecognizeStream(chunk_generator(), None):
            results.append(result)
        
        assert len(results) == 1
        assert results[0].is_final is True
        assert results[0].transcript == ""

class TestRecognitionOneShot:
    """Test one-shot recognition functionality."""
    
    @pytest.mark.asyncio
    async def test_recognize_success(self, service_instance, sample_audio_data):
        """Test successful one-shot recognition."""
        request = RecognitionRequest(
            audio_data=sample_audio_data,
            sample_rate=16000,
            encoding="pcm",
            config=RecognitionConfig(
                language="en",
                interim_results=False,
                enable_vad=True,
                enable_diarization=False,
                enable_timestamps=True
            )
        )
        
        response = await service_instance.Recognize(request, None)
        
        assert len(response.results) == 1
        assert response.results[0].transcript == "Hello world"
        assert response.results[0].is_final is True
        assert response.results[0].confidence > 0
        assert response.processing_time_ms >= 0
    
    @pytest.mark.asyncio
    async def test_recognize_empty_audio(self, service_instance):
        """Test one-shot recognition with empty audio."""
        request = RecognitionRequest(
            audio_data=b"",
            sample_rate=16000,
            encoding="pcm",
            config=RecognitionConfig()
        )
        
        response = await service_instance.Recognize(request, None)
        
        assert len(response.results) == 0
        assert response.processing_time_ms == 0
    
    @pytest.mark.asyncio
    async def test_recognize_error(self, service_instance):
        """Test one-shot recognition with error."""
        # Mock Whisper error
        service_instance.whisper_model.transcribe.side_effect = Exception("Whisper error")
        
        request = RecognitionRequest(
            audio_data=b"test audio data",
            sample_rate=16000,
            encoding="pcm",
            config=RecognitionConfig()
        )
        
        context = MagicMock()
        response = await service_instance.Recognize(request, context)
        
        assert len(response.results) == 0
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
            assert response.model_name is not None
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, service_instance):
        """Test health check when services are unhealthy."""
        with patch.object(service_instance, '_check_model_health', return_value=False), \
             patch.object(service_instance, '_check_nats_health', return_value=True):
            
            request = HealthRequest()
            response = await service_instance.HealthCheck(request, None)
            
            assert response.healthy is False

class TestAudioProcessing:
    """Test audio processing functionality."""
    
    @pytest.mark.asyncio
    async def test_process_audio_chunk_pcm(self, service_instance):
        """Test processing PCM audio chunk."""
        # Create PCM audio data
        audio_data = np.array([1000, 2000, 3000, 4000], dtype=np.int16)
        chunk = AudioChunk(
            audio_data=audio_data.tobytes(),
            sample_rate=16000,
            channels=1,
            encoding="pcm",
            timestamp_us=0
        )
        
        processed = await service_instance._process_audio_chunk(chunk)
        
        assert len(processed) == 4
        assert all(-1.0 <= sample <= 1.0 for sample in processed)
    
    @pytest.mark.asyncio
    async def test_process_audio_chunk_float32(self, service_instance):
        """Test processing float32 audio chunk."""
        # Create float32 audio data
        audio_data = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        chunk = AudioChunk(
            audio_data=audio_data.tobytes(),
            sample_rate=16000,
            channels=1,
            encoding="float32",
            timestamp_us=0
        )
        
        processed = await service_instance._process_audio_chunk(chunk)
        
        assert len(processed) == 4
        assert processed == audio_data.tolist()
    
    @pytest.mark.asyncio
    async def test_process_audio_chunk_resampling(self, service_instance):
        """Test audio chunk processing with resampling."""
        # Create audio data at different sample rate
        audio_data = np.array([1000, 2000, 3000, 4000], dtype=np.int16)
        chunk = AudioChunk(
            audio_data=audio_data.tobytes(),
            sample_rate=8000,  # Different from default 16000
            channels=1,
            encoding="pcm",
            timestamp_us=0
        )
        
        with patch('main.librosa.resample') as mock_resample:
            mock_resample.return_value = np.array([0.1, 0.2, 0.3, 0.4])
            
            processed = await service_instance._process_audio_chunk(chunk)
            
            assert len(processed) == 4
            mock_resample.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_audio_data_success(self, service_instance):
        """Test processing audio data for one-shot recognition."""
        # Create PCM audio data
        audio_data = np.array([1000, 2000, 3000, 4000], dtype=np.int16)
        
        processed = await service_instance._process_audio_data(
            audio_data.tobytes(), 16000
        )
        
        assert len(processed) == 4
        assert all(-1.0 <= sample <= 1.0 for sample in processed)
    
    @pytest.mark.asyncio
    async def test_process_audio_data_error(self, service_instance):
        """Test processing audio data with error."""
        processed = await service_instance._process_audio_data(b"invalid data", 16000)
        
        assert len(processed) == 0

class TestTranscription:
    """Test transcription functionality."""
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_success(self, service_instance):
        """Test successful audio transcription."""
        audio_data = [0.1, 0.2, 0.3, 0.4] * 4000  # 1 second at 16kHz
        
        result = await service_instance._transcribe_audio(audio_data, is_final=True)
        
        assert result is not None
        assert result.transcript == "Hello world"
        assert result.is_final is True
        assert result.confidence > 0
        assert len(result.words) == 2
        assert result.words[0].word == "Hello"
        assert result.words[1].word == "world"
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_empty(self, service_instance):
        """Test transcription with empty audio."""
        result = await service_instance._transcribe_audio([], is_final=True)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_short(self, service_instance):
        """Test transcription with very short audio."""
        audio_data = [0.1, 0.2]  # Less than 100ms
        
        result = await service_instance._transcribe_audio(audio_data, is_final=True)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_no_text(self, service_instance):
        """Test transcription with no text output."""
        service_instance.whisper_model.transcribe.return_value = {
            "text": "",
            "segments": []
        }
        
        audio_data = [0.1, 0.2, 0.3, 0.4] * 4000
        
        result = await service_instance._transcribe_audio(audio_data, is_final=True)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_error(self, service_instance):
        """Test transcription with error."""
        service_instance.whisper_model.transcribe.side_effect = Exception("Transcription error")
        
        audio_data = [0.1, 0.2, 0.3, 0.4] * 4000
        
        result = await service_instance._transcribe_audio(audio_data, is_final=True)
        
        assert result is None

class TestVoiceActivityDetection:
    """Test voice activity detection functionality."""
    
    @pytest.mark.asyncio
    async def test_detect_voice_activity_speech(self, service_instance):
        """Test VAD detection of speech."""
        audio_data = [0.1, 0.2, 0.3, 0.4] * 800  # 20ms at 16kHz
        
        result = await service_instance._detect_voice_activity(audio_data)
        
        assert result is True
        service_instance.vad.is_speech.assert_called()
    
    @pytest.mark.asyncio
    async def test_detect_voice_activity_no_vad(self, service_instance):
        """Test VAD detection without VAD initialized."""
        service_instance.vad = None
        audio_data = [0.1, 0.2, 0.3, 0.4] * 800
        
        result = await service_instance._detect_voice_activity(audio_data)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_detect_voice_activity_short_audio(self, service_instance):
        """Test VAD detection with very short audio."""
        audio_data = [0.1, 0.2]  # Less than 20ms
        
        result = await service_instance._detect_voice_activity(audio_data)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_detect_voice_activity_error(self, service_instance):
        """Test VAD detection with error."""
        service_instance.vad.is_speech.side_effect = Exception("VAD error")
        audio_data = [0.1, 0.2, 0.3, 0.4] * 800
        
        result = await service_instance._detect_voice_activity(audio_data)
        
        assert result is False

class TestModelLoading:
    """Test model loading functionality."""
    
    @pytest.mark.asyncio
    async def test_load_models_success(self, service_instance):
        """Test successful model loading."""
        with patch('main.whisper.load_model') as mock_load_model, \
             patch('main.webrtcvad.Vad') as mock_vad_class:
            
            mock_load_model.return_value = mock_whisper_model
            mock_vad_class.return_value = mock_vad
            
            await service_instance._load_models()
            
            assert service_instance.whisper_model is not None
            assert service_instance.vad is not None
    
    @pytest.mark.asyncio
    async def test_load_models_error(self, service_instance):
        """Test model loading with error."""
        with patch('main.whisper.load_model') as mock_load_model:
            mock_load_model.side_effect = Exception("Model loading error")
            
            with pytest.raises(Exception):
                await service_instance._load_models()

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
        service_instance.whisper_model = mock_whisper_model
        
        is_healthy = await service_instance._check_model_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_model_health_unhealthy(self, service_instance):
        """Test model health check when unhealthy."""
        service_instance.whisper_model = None
        
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

# Integration tests
class TestSTTIntegration:
    """Integration tests for STT service."""
    
    @pytest.mark.asyncio
    async def test_full_streaming_flow(self, service_instance, sample_audio_data):
        """Test complete streaming recognition flow."""
        # Create multiple audio chunks
        chunk_size = len(sample_audio_data) // 4
        chunks = []
        
        for i in range(4):
            chunk = AudioChunk(
                audio_data=sample_audio_data[i*chunk_size:(i+1)*chunk_size],
                sample_rate=16000,
                channels=1,
                encoding="pcm",
                timestamp_us=i * 250000  # 0.25 seconds apart
            )
            chunks.append(chunk)
        
        async def chunk_generator():
            for chunk in chunks:
                yield chunk
        
        results = []
        async for result in service_instance.RecognizeStream(chunk_generator(), None):
            results.append(result)
        
        assert len(results) > 0
        assert results[-1].is_final is True
        assert results[-1].transcript == "Hello world"
    
    @pytest.mark.asyncio
    async def test_full_one_shot_flow(self, service_instance, sample_audio_data):
        """Test complete one-shot recognition flow."""
        request = RecognitionRequest(
            audio_data=sample_audio_data,
            sample_rate=16000,
            encoding="pcm",
            config=RecognitionConfig(
                language="en",
                interim_results=False,
                enable_vad=True,
                enable_diarization=False,
                enable_timestamps=True
            )
        )
        
        response = await service_instance.Recognize(request, None)
        
        assert len(response.results) == 1
        result = response.results[0]
        assert result.transcript == "Hello world"
        assert result.is_final is True
        assert result.confidence > 0
        assert len(result.words) == 2
        assert result.start_time_us >= 0
        assert result.end_time_us > result.start_time_us
    
    @pytest.mark.asyncio
    async def test_vad_integration(self, service_instance, sample_audio_data):
        """Test VAD integration with streaming."""
        # Mock VAD to detect speech in first chunk, silence in second
        def vad_side_effect(data, sample_rate):
            # Simple heuristic: return True for first call, False for second
            if not hasattr(vad_side_effect, 'call_count'):
                vad_side_effect.call_count = 0
            vad_side_effect.call_count += 1
            return vad_side_effect.call_count == 1
        
        service_instance.vad.is_speech.side_effect = vad_side_effect
        
        # Create chunks
        chunk_size = len(sample_audio_data) // 2
        chunks = [
            AudioChunk(
                audio_data=sample_audio_data[:chunk_size],
                sample_rate=16000,
                channels=1,
                encoding="pcm",
                timestamp_us=0
            ),
            AudioChunk(
                audio_data=sample_audio_data[chunk_size:],
                sample_rate=16000,
                channels=1,
                encoding="pcm",
                timestamp_us=500000
            )
        ]
        
        async def chunk_generator():
            for chunk in chunks:
                yield chunk
        
        results = []
        async for result in service_instance.RecognizeStream(chunk_generator(), None):
            results.append(result)
        
        # Should have processed both chunks
        assert len(results) > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])





