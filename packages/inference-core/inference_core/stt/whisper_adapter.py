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
    
    def __init__(self, model_name: str = "tiny.en", device: str = "cpu"):
        """Load Whisper model.
        
        Args:
            model_name: Whisper model name (e.g., "tiny.en", "base", "small")
            device: Device to run on ("cpu", "cuda")
        """
        import whisper  # type: ignore
        self._model = whisper.load_model(model_name, device=device)
    
    def transcribe(self, audio: np.ndarray, fp16: bool = False) -> Dict[str, Any]:
        """Transcribe audio using Whisper model."""
        return self._model.transcribe(audio, fp16=fp16)

