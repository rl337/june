from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from ..strategies import SttStrategy, InferenceRequest, InferenceResponse
from .whisper_adapter import WhisperModelAdapter, WhisperModelImpl

logger = logging.getLogger(__name__)


class WhisperSttStrategy(SttStrategy):
    def __init__(
        self,
        model_name: str = "tiny.en",
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
        result: Dict[str, Any] = self._model.transcribe(data, fp16=False)
        text = result.get("text", "").strip()
        return InferenceResponse(payload=text, metadata={"confidence": 0.0})


