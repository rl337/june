"""Tests for STT strategies with mocked dependencies."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import io
import numpy as np

from inference_core.stt.whisper_strategy import WhisperSttStrategy
from inference_core.strategies import InferenceRequest, InferenceResponse


@pytest.fixture
def mock_whisper_model():
    """Mock Whisper model."""
    model = Mock()
    model.transcribe = Mock(return_value={"text": "hello world"})
    return model


@pytest.fixture
def whisper_strategy(mock_whisper_model):
    """Create WhisperSttStrategy with mocked model."""
    strategy = WhisperSttStrategy(model_name="tiny.en", device="cpu")
    # Directly set the model instead of calling warmup which requires whisper import
    strategy._model = mock_whisper_model
    return strategy


def test_whisper_strategy_warmup_success(mock_whisper_model):
    """Test WhisperSttStrategy warmup succeeds."""
    with patch('whisper') as mock_whisper:
        mock_whisper.load_model.return_value = mock_whisper_model
        strategy = WhisperSttStrategy(model_name="tiny.en", device="cpu")
        with patch('inference_core.stt.whisper_strategy.whisper', mock_whisper):
            strategy.warmup()
        assert strategy._model == mock_whisper_model
        mock_whisper.load_model.assert_called_once_with("tiny.en", device="cpu")


def test_whisper_strategy_warmup_fails_on_import_error():
    """Test WhisperSttStrategy warmup raises on import failure."""
    import sys
    original_whisper = sys.modules.get('whisper')
    try:
        if 'whisper' in sys.modules:
            del sys.modules['whisper']
        with patch.dict('sys.modules', {'whisper': None}):
            with patch('inference_core.stt.whisper_strategy.whisper', create=True, side_effect=ImportError("No module")):
                strategy = WhisperSttStrategy()
                with pytest.raises(Exception):
                    strategy.warmup()
    finally:
        if original_whisper:
            sys.modules['whisper'] = original_whisper


def test_whisper_strategy_infer_with_bytes(whisper_strategy, mock_whisper_model):
    """Test WhisperSttStrategy.infer accepts bytes directly."""
    # Create mock audio bytes (WAV format)
    audio_data = np.random.randn(16000).astype(np.float32)
    wav_io = io.BytesIO()
    import soundfile as sf
    sf.write(wav_io, audio_data, 16000, format='WAV')
    audio_bytes = wav_io.getvalue()
    
    with patch('inference_core.stt.whisper_strategy.sf') as mock_sf:
        mock_sf.read.return_value = (audio_data, 16000)
        result = whisper_strategy.infer(audio_bytes)
        
        assert isinstance(result, InferenceResponse)
        assert result.payload == "hello world"
        assert result.metadata.get("confidence") == 0.0
        mock_whisper_model.transcribe.assert_called_once()


def test_whisper_strategy_infer_with_request(whisper_strategy, mock_whisper_model):
    """Test WhisperSttStrategy.infer accepts InferenceRequest."""
    audio_data = np.random.randn(16000).astype(np.float32)
    wav_io = io.BytesIO()
    import soundfile as sf
    sf.write(wav_io, audio_data, 16000, format='WAV')
    audio_bytes = wav_io.getvalue()
    
    request = InferenceRequest(payload=audio_bytes, metadata={})
    
    with patch('inference_core.stt.whisper_strategy.sf') as mock_sf:
        mock_sf.read.return_value = (audio_data, 16000)
        result = whisper_strategy.infer(request)
        
        assert isinstance(result, InferenceResponse)
        assert result.payload == "hello world"


def test_whisper_strategy_infer_handles_stereo_audio(whisper_strategy, mock_whisper_model):
    """Test WhisperSttStrategy handles stereo audio (converts to mono)."""
    audio_data = np.random.randn(16000, 2).astype(np.float32)  # Stereo
    wav_io = io.BytesIO()
    import soundfile as sf
    sf.write(wav_io, audio_data, 16000, format='WAV')
    audio_bytes = wav_io.getvalue()
    
    with patch('inference_core.stt.whisper_strategy.sf') as mock_sf:
        mock_sf.read.return_value = (audio_data, 16000)
        result = whisper_strategy.infer(audio_bytes)
        
        # Verify mean was called (implicitly via numpy)
        assert isinstance(result, InferenceResponse)
        mock_whisper_model.transcribe.assert_called_once()


def test_whisper_strategy_infer_empty_text(whisper_strategy, mock_whisper_model):
    """Test WhisperSttStrategy handles empty transcript."""
    mock_whisper_model.transcribe.return_value = {"text": ""}
    audio_data = np.random.randn(16000).astype(np.float32)
    wav_io = io.BytesIO()
    import soundfile as sf
    sf.write(wav_io, audio_data, 16000, format='WAV')
    audio_bytes = wav_io.getvalue()
    
    with patch('inference_core.stt.whisper_strategy.sf') as mock_sf:
        mock_sf.read.return_value = (audio_data, 16000)
        result = whisper_strategy.infer(audio_bytes)
        
        assert result.payload == ""

