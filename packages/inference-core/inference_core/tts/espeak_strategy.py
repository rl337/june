from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import numpy as np
from typing import Dict, Any

import soundfile as sf

from ..strategies import TtsStrategy, InferenceRequest, InferenceResponse

logger = logging.getLogger(__name__)


class EspeakTtsStrategy(TtsStrategy):
    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    def warmup(self) -> None:
        try:
            result = subprocess.run(['espeak', '--version'], capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception("espeak not available")
            logger.info("espeak TTS initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize espeak: {e}")
            raise

    def infer(self, request: InferenceRequest | str) -> InferenceResponse:
        if isinstance(request, str):
            text = request
            voice_id = "default"
            language = "en"
        else:
            text = request.payload if isinstance(request.payload, str) else str(request.payload)
            voice_id = request.metadata.get("voice_id", "default")
            language = request.metadata.get("language", "en")
        
        if not text.strip():
            return InferenceResponse(payload=b"", metadata={"sample_rate": self.sample_rate, "duration_ms": 0})
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            cmd = ['espeak', '-s', str(self.sample_rate), '-w', temp_path, text]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"espeak failed: {result.stderr}")
            
            audio_data, sr = sf.read(temp_path)
            os.unlink(temp_path)
            
            if sr != self.sample_rate:
                target_samples = int(len(audio_data) * self.sample_rate / sr)
                if len(audio_data) > target_samples:
                    audio_data = audio_data[:target_samples]
                else:
                    audio_data = np.pad(audio_data, (0, target_samples - len(audio_data)))
            
            audio_data = audio_data.astype(np.float32)
            if np.max(np.abs(audio_data)) > 0:
                audio_data = audio_data / np.max(np.abs(audio_data))
            
            audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
            duration_ms = int(len(audio_data) / self.sample_rate * 1000)
            
            return InferenceResponse(
                payload=audio_bytes,
                metadata={"sample_rate": self.sample_rate, "duration_ms": duration_ms}
            )
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return InferenceResponse(payload=b"", metadata={"sample_rate": self.sample_rate, "duration_ms": 0})


