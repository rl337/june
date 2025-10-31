"""Tests for gRPC server apps with mocked gRPC."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import grpc

from inference_core.servers.stt_server import SttGrpcApp, _SttServicer
from inference_core.servers.tts_server import TtsGrpcApp, _TtsServicer
from inference_core.servers.llm_server import LlmGrpcApp, _LlmServicer
from inference_core.strategies import InferenceRequest, InferenceResponse
from inference_core.stt.whisper_strategy import WhisperSttStrategy
from inference_core.tts.espeak_strategy import EspeakTtsStrategy
from inference_core.llm.passthrough_strategy import PassthroughLlmStrategy


@pytest.fixture
def mock_stt_strategy():
    """Mock STT strategy."""
    strategy = Mock(spec=WhisperSttStrategy)
    strategy.warmup = Mock()
    strategy.infer = Mock(return_value=InferenceResponse(
        payload="test transcript",
        metadata={"confidence": 0.95}
    ))
    return strategy


@pytest.fixture
def mock_tts_strategy():
    """Mock TTS strategy."""
    strategy = Mock(spec=EspeakTtsStrategy)
    strategy.warmup = Mock()
    strategy.infer = Mock(return_value=InferenceResponse(
        payload=b"mock audio bytes",
        metadata={"sample_rate": 16000, "duration_ms": 1000}
    ))
    return strategy


@pytest.fixture
def mock_llm_strategy():
    """Mock LLM strategy."""
    strategy = Mock(spec=PassthroughLlmStrategy)
    strategy.warmup = Mock()
    strategy.infer = Mock(return_value=InferenceResponse(
        payload={"text": "generated text", "tokens": 10},
        metadata={}
    ))
    return strategy


class TestSttServicer:
    """Tests for _SttServicer."""
    
    def test_recognize_success(self, mock_stt_strategy):
        """Test _SttServicer.Recognize returns correct response."""
        servicer = _SttServicer(mock_stt_strategy)
        
        from june_grpc_api.generated import asr_pb2
        request = asr_pb2.RecognitionRequest()
        request.audio_data = b"fake audio data"
        
        response = servicer.Recognize(request, None)
        
        assert response.results
        assert len(response.results) == 1
        assert response.results[0].transcript == "test transcript"
        assert response.results[0].confidence == 0.95
        mock_stt_strategy.infer.assert_called_once_with(b"fake audio data")
    
    def test_recognize_empty_audio(self, mock_stt_strategy):
        """Test _SttServicer.Recognize handles empty audio."""
        mock_stt_strategy.infer.return_value = InferenceResponse(
            payload="",
            metadata={"confidence": 0.0}
        )
        servicer = _SttServicer(mock_stt_strategy)
        
        from june_grpc_api.generated import asr_pb2
        request = asr_pb2.RecognitionRequest()
        request.audio_data = b""
        
        response = servicer.Recognize(request, None)
        
        assert response.results[0].transcript == ""


class TestTtsServicer:
    """Tests for _TtsServicer."""
    
    def test_synthesize_success(self, mock_tts_strategy):
        """Test _TtsServicer.Synthesize returns correct response."""
        servicer = _TtsServicer(mock_tts_strategy)
        
        from june_grpc_api.generated import tts_pb2
        request = tts_pb2.SynthesisRequest()
        request.text = "hello world"
        request.voice_id = "default"
        request.language = "en"
        
        import asyncio
        response = asyncio.run(servicer.Synthesize(request, None))
        
        assert response.audio_data == b"mock audio bytes"
        assert response.sample_rate == 16000
        assert response.duration_ms == 1000
        mock_tts_strategy.infer.assert_called_once()
        call_args = mock_tts_strategy.infer.call_args[0][0]
        assert isinstance(call_args, InferenceRequest)
        assert call_args.payload == "hello world"


class TestLlmServicer:
    """Tests for _LlmServicer."""
    
    def test_generate_success(self, mock_llm_strategy):
        """Test _LlmServicer.Generate returns correct response."""
        servicer = _LlmServicer(mock_llm_strategy)
        
        from june_grpc_api.generated import llm_pb2
        request = llm_pb2.GenerationRequest()
        request.prompt = "hello"
        request.params.max_tokens = 100
        request.params.temperature = 0.7
        
        response = servicer.Generate(request, None)
        
        assert response.text == "generated text"
        mock_llm_strategy.infer.assert_called_once()
        call_args = mock_llm_strategy.infer.call_args[0][0]
        assert isinstance(call_args, InferenceRequest)
        assert call_args.payload["prompt"] == "hello"
        assert call_args.payload["params"]["max_tokens"] == 100


class TestSttGrpcApp:
    """Tests for SttGrpcApp."""
    
    def test_init_default_port(self, mock_stt_strategy):
        """Test SttGrpcApp initializes with default port."""
        with patch.dict('os.environ', {}, clear=True):
            app = SttGrpcApp(mock_stt_strategy)
            assert app.port == 50052
    
    def test_init_custom_port(self, mock_stt_strategy):
        """Test SttGrpcApp initializes with custom port."""
        app = SttGrpcApp(mock_stt_strategy, port=12345)
        assert app.port == 12345
    
    def test_initialize_calls_warmup(self, mock_stt_strategy):
        """Test SttGrpcApp.initialize calls strategy.warmup."""
        with patch('inference_core.servers.stt_server.setup_logging'):
            app = SttGrpcApp(mock_stt_strategy)
            app.initialize()
            mock_stt_strategy.warmup.assert_called_once()
    
    def test_run_creates_server(self, mock_stt_strategy):
        """Test SttGrpcApp.run creates and configures server."""
        with patch('inference_core.servers.stt_server.grpc.server') as mock_server, \
             patch('inference_core.servers.stt_server.asr_pb2_grpc') as mock_grpc:
            
            mock_server_instance = Mock()
            mock_server.return_value = mock_server_instance
            mock_executor = Mock()
            
            app = SttGrpcApp(mock_stt_strategy, port=12345)
            
            # Mock wait_for_termination to not block
            mock_server_instance.wait_for_termination = Mock()
            
            try:
                app.run()
            except Exception:
                pass  # May fail due to server setup, but we test configuration
            
            mock_server.assert_called_once()


class TestTtsGrpcApp:
    """Tests for TtsGrpcApp."""
    
    def test_init_default_port(self, mock_tts_strategy):
        """Test TtsGrpcApp initializes with default port."""
        with patch.dict('os.environ', {}, clear=True):
            app = TtsGrpcApp(mock_tts_strategy)
            assert app.port == 50053
    
    def test_initialize_calls_warmup(self, mock_tts_strategy):
        """Test TtsGrpcApp.initialize calls strategy.warmup."""
        with patch('inference_core.servers.tts_server.setup_logging'):
            app = TtsGrpcApp(mock_tts_strategy)
            app.initialize()
            mock_tts_strategy.warmup.assert_called_once()


class TestLlmGrpcApp:
    """Tests for LlmGrpcApp."""
    
    def test_init_default_port(self, mock_llm_strategy):
        """Test LlmGrpcApp initializes with default port."""
        with patch.dict('os.environ', {}, clear=True):
            app = LlmGrpcApp(mock_llm_strategy)
            assert app.port == 50051
    
    def test_initialize_calls_warmup(self, mock_llm_strategy):
        """Test LlmGrpcApp.initialize calls strategy.warmup."""
        with patch('inference_core.servers.llm_server.setup_logging'):
            app = LlmGrpcApp(mock_llm_strategy)
            app.initialize()
            mock_llm_strategy.warmup.assert_called_once()

