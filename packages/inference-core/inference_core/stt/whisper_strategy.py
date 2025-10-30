from __future__ import annotations

import logging
from typing import Dict, Any

from ..strategies import SttStrategy, InferenceRequest, InferenceResponse

logger = logging.getLogger(__name__)


class WhisperSttStrategy(SttStrategy):
    def __init__(self, model_name: str = "tiny.en", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    def warmup(self) -> None:
        try:
            import whisper  # type: ignore
        except Exception as e:
            logger.error("Failed to import whisper: %s", e)
            raise
        self._model = whisper.load_model(self.model_name, device=self.device)

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


