"""Adapter for OpenAI Whisper model to enable easy mocking in tests."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

import numpy as np


class WhisperModelAdapter(ABC):
    """Abstract interface for Whisper model operations."""

    @abstractmethod
    def transcribe(
        self,
        audio: np.ndarray,
        fp16: bool = False,
        language: str = "en",
        task: str = "transcribe",
        initial_prompt: str | None = None,
    ) -> Dict[str, Any]:
        """Transcribe audio to text.

        Args:
            audio: Audio data as numpy array (float32, mono)
            fp16: Whether to use fp16 precision
            language: Language code (e.g., "en")
            task: "transcribe" or "translate"
            initial_prompt: Optional prompt to guide transcription

        Returns:
            Dict with 'text' key containing transcript
        """
        ...


class WhisperModelImpl(WhisperModelAdapter):
    """Concrete implementation using OpenAI Whisper library."""

    def __init__(
        self,
        model_name: str = "tiny.en",
        device: str = "cpu",
        download_root: str | None = None,
    ):
        """Load Whisper model.

        Args:
            model_name: Whisper model name (e.g., "tiny.en", "base", "small")
            device: Device to run on ("cpu", "cuda")
            download_root: Root directory for model cache (defaults to ~/.cache/whisper)
        """
        import os

        import whisper  # type: ignore

        # Use /models/whisper if MODEL_CACHE_DIR is set and download_root not specified
        if download_root is None:
            model_cache_dir = os.getenv(
                "MODEL_CACHE_DIR", os.path.expanduser("~/.cache")
            )
            download_root = os.path.join(model_cache_dir, "whisper")
            os.makedirs(download_root, exist_ok=True)

        self._model = whisper.load_model(
            model_name, device=device, download_root=download_root
        )

    def transcribe(
        self,
        audio: np.ndarray,
        fp16: bool = False,
        language: str = "en",
        task: str = "transcribe",
        initial_prompt: str | None = None,
    ) -> Dict[str, Any]:
        """Transcribe audio using Whisper model."""
        kwargs = {"fp16": fp16, "language": language, "task": task}
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        return self._model.transcribe(audio, **kwargs)
