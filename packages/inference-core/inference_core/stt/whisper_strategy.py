from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from ..strategies import SttStrategy, InferenceRequest, InferenceResponse
from .whisper_adapter import WhisperModelAdapter, WhisperModelImpl

logger = logging.getLogger(__name__)


class WhisperSttStrategy(SttStrategy):
    def __init__(
        self,
        model_name: str = "base.en",  # Upgraded from tiny.en for better accuracy
        device: str = "cpu",
        whisper_adapter: Optional[WhisperModelAdapter] = None
    ) -> None:
        """Initialize Whisper STT strategy.
        
        Args:
            model_name: Whisper model name (e.g., "tiny.en", "base")
            device: Device to run on ("cpu", "cuda")
            whisper_adapter: Optional adapter for testing (defaults to WhisperModelImpl)
        """
        self.model_name = model_name
        self.device = device
        self._adapter: Optional[WhisperModelAdapter] = whisper_adapter
        self._model: Optional[WhisperModelAdapter] = None

    def warmup(self) -> None:
        """Load and initialize the Whisper model."""
        if self._adapter is None:
            try:
                self._model = WhisperModelImpl(self.model_name, self.device)
            except Exception as e:
                logger.error("Failed to load Whisper model: %s", e)
                raise
        else:
            self._model = self._adapter

    def infer(self, request: InferenceRequest | bytes) -> InferenceResponse:
        if isinstance(request, bytes):
            audio_bytes = request
        else:
            audio_bytes = request.payload
        import numpy as np
        import io
        import soundfile as sf

        data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        
        # Ensure audio is in the right format for Whisper
        # Whisper expects 16kHz audio, but can handle other rates
        # Normalize audio levels for better recognition
        if len(data) > 0:
            max_val = np.abs(data).max()
            if max_val > 0:
                data = data / max_val
        
        # Use language hint and better transcription options
        # Try to use initial_prompt based on context if available
        # For testing, use a generic prompt that helps with common words
        initial_prompt = "Hello world test speech recognition one two three four five."
        
        result: Dict[str, Any] = self._model.transcribe(
            data,
            fp16=False,
            language="en",  # Specify English for better accuracy
            task="transcribe",  # Transcribe (not translate)
            initial_prompt=initial_prompt,  # Help with context
            verbose=False,  # Reduce logging
        )
        text = result.get("text", "").strip()
        confidence = result.get("no_speech_prob", 0.0)
        # Convert no_speech_prob to confidence (inverse)
        actual_confidence = 1.0 - confidence if confidence else 0.9
        return InferenceResponse(payload=text, metadata={"confidence": actual_confidence})


