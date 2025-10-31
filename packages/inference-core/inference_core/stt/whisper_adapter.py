"""Adapter for OpenAI Whisper model to enable easy mocking in tests."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any
import numpy as np


class WhisperModelAdapter(ABC):
    """Abstract interface for Whisper model operations."""
    
    @abstractmethod
    def transcribe(self, audio: np.ndarray, fp16: bool = False) -> Dict[str, Any]:
        """Transcribe audio to text.
        
        Args:
            audio: Audio data as numpy array (float32, mono)
            fp16: Whether to use fp16 precision
            
        Returns:
            Dict with 'text' key containing transcript
        """
        ...


class WhisperModelImpl(WhisperModelAdapter):
    """Concrete implementation using OpenAI Whisper library."""
    
    def __init__(self, model_name: str = "tiny.en", device: str = "cpu", download_root: str | None = None):
        """Load Whisper model.
        
        Args:
            model_name: Whisper model name (e.g., "tiny.en", "base", "small")
            device: Device to run on ("cpu", "cuda")
            download_root: Root directory for model cache (defaults to ~/.cache/whisper)
        """
        import whisper  # type: ignore
        import os
        
        # Use /models/whisper if MODEL_CACHE_DIR is set and download_root not specified
        if download_root is None:
            model_cache_dir = os.getenv("MODEL_CACHE_DIR", os.path.expanduser("~/.cache"))
            download_root = os.path.join(model_cache_dir, "whisper")
            os.makedirs(download_root, exist_ok=True)
        
        self._model = whisper.load_model(model_name, device=device, download_root=download_root)
    
    def transcribe(self, audio: np.ndarray, fp16: bool = False) -> Dict[str, Any]:
        """Transcribe audio using Whisper model."""
        return self._model.transcribe(audio, fp16=fp16)

