"""Tests for TTS strategies with mocked dependencies."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import tempfile
import os

from inference_core.tts.espeak_strategy import EspeakTtsStrategy
from inference_core.strategies import InferenceRequest, InferenceResponse


@pytest.fixture
def tts_strategy():
    """Create EspeakTtsStrategy with mocked subprocess."""
    with patch('inference_core.tts.espeak_strategy.subprocess') as mock_subprocess:
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result
        strategy = EspeakTtsStrategy(sample_rate=16000)
        strategy.warmup()
        return strategy


def test_espeak_strategy_warmup_success():
    """Test EspeakTtsStrategy warmup succeeds."""
    with patch('inference_core.tts.espeak_strategy.subprocess') as mock_subprocess:
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result
        strategy = EspeakTtsStrategy()
        strategy.warmup()


def test_espeak_strategy_warmup_fails_on_check():
    """Test EspeakTtsStrategy warmup raises when espeak unavailable."""
    with patch('inference_core.tts.espeak_strategy.subprocess') as mock_subprocess:
        mock_result = Mock()
        mock_result.returncode = 1
        mock_subprocess.run.return_value = mock_result
        strategy = EspeakTtsStrategy()
        with pytest.raises(Exception):
            strategy.warmup()


def test_espeak_strategy_warmup_fails_on_subprocess_error():
    """Test EspeakTtsStrategy warmup raises on subprocess failure."""
    with patch('inference_core.tts.espeak_strategy.subprocess') as mock_subprocess:
        mock_subprocess.run.side_effect = FileNotFoundError("espeak not found")
        strategy = EspeakTtsStrategy()
        with pytest.raises(Exception):
            strategy.warmup()


def test_espeak_strategy_infer_with_string(tts_strategy):
    """Test EspeakTtsStrategy.infer accepts string directly."""
    with patch('inference_core.tts.espeak_strategy.tempfile') as mock_tempfile, \
         patch('inference_core.tts.espeak_strategy.subprocess') as mock_subprocess, \
         patch('inference_core.tts.espeak_strategy.sf') as mock_sf, \
         patch('inference_core.tts.espeak_strategy.os') as mock_os:
        
        # Setup mocks
        mock_file = Mock()
        mock_file.name = "/tmp/test.wav"
        mock_tempfile.NamedTemporaryFile.return_value.__enter__.return_value = mock_file
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result
        
        # Mock audio data
        audio_data = np.random.randn(16000).astype(np.float32)
        mock_sf.read.return_value = (audio_data, 16000)
        
        result = tts_strategy.infer("hello world")
        
        assert isinstance(result, InferenceResponse)
        assert isinstance(result.payload, bytes)
        assert len(result.payload) > 0
        assert result.metadata.get("sample_rate") == 16000
        assert result.metadata.get("duration_ms") > 0


def test_espeak_strategy_infer_with_request(tts_strategy):
    """Test EspeakTtsStrategy.infer accepts InferenceRequest."""
    with patch('inference_core.tts.espeak_strategy.tempfile') as mock_tempfile, \
         patch('inference_core.tts.espeak_strategy.subprocess') as mock_subprocess, \
         patch('inference_core.tts.espeak_strategy.sf') as mock_sf, \
         patch('inference_core.tts.espeak_strategy.os'):
        
        mock_file = Mock()
        mock_file.name = "/tmp/test.wav"
        mock_tempfile.NamedTemporaryFile.return_value.__enter__.return_value = mock_file
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result
        
        audio_data = np.random.randn(16000).astype(np.float32)
        mock_sf.read.return_value = (audio_data, 16000)
        
        request = InferenceRequest(payload="hello world", metadata={"voice_id": "default", "language": "en"})
        result = tts_strategy.infer(request)
        
        assert isinstance(result, InferenceResponse)
        assert isinstance(result.payload, bytes)


def test_espeak_strategy_infer_empty_text(tts_strategy):
    """Test EspeakTtsStrategy returns empty audio for empty text."""
    result = tts_strategy.infer("")
    
    assert isinstance(result, InferenceResponse)
    assert result.payload == b""
    assert result.metadata.get("duration_ms") == 0


def test_espeak_strategy_infer_resamples_audio(tts_strategy):
    """Test EspeakTtsStrategy handles sample rate mismatch."""
    with patch('inference_core.tts.espeak_strategy.tempfile') as mock_tempfile, \
         patch('inference_core.tts.espeak_strategy.subprocess') as mock_subprocess, \
         patch('inference_core.tts.espeak_strategy.sf') as mock_sf, \
         patch('inference_core.tts.espeak_strategy.os'):
        
        mock_file = Mock()
        mock_file.name = "/tmp/test.wav"
        mock_tempfile.NamedTemporaryFile.return_value.__enter__.return_value = mock_file
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.run.return_value = mock_result
        
        # Audio with different sample rate (22050)
        audio_data = np.random.randn(22050).astype(np.float32)
        mock_sf.read.return_value = (audio_data, 22050)
        
        result = tts_strategy.infer("test")
        
        assert isinstance(result, InferenceResponse)
        # Should have resampled


def test_espeak_strategy_infer_handles_espeak_failure(tts_strategy):
    """Test EspeakTtsStrategy handles espeak command failure gracefully."""
    with patch('inference_core.tts.espeak_strategy.tempfile') as mock_tempfile, \
         patch('inference_core.tts.espeak_strategy.subprocess') as mock_subprocess, \
         patch('inference_core.tts.espeak_strategy.os'):
        
        mock_file = Mock()
        mock_file.name = "/tmp/test.wav"
        mock_tempfile.NamedTemporaryFile.return_value.__enter__.return_value = mock_file
        
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "espeak error"
        mock_subprocess.run.return_value = mock_result
        
        result = tts_strategy.infer("test")
        
        # Should return empty response on error
        assert isinstance(result, InferenceResponse)
        assert result.payload == b""




