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
            # Create temp file path (don't create file, espeak will create it)
            fd, temp_path = tempfile.mkstemp(suffix='.wav')
            os.close(fd)  # Close file descriptor, espeak will create the file
            
            # espeak syntax: espeak [options] text
            # -s: speed in words per minute (not sample rate!)
            # -w: output WAV file
            # Sample rate is typically fixed by espeak, we'll resample if needed
            cmd = ['espeak', '-s', '150', '-w', temp_path, text]
            result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
            if result.returncode != 0:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise Exception(f"espeak failed: {result.stderr}")
            
            # Wait a moment for file to be written
            import time
            time.sleep(0.1)
            
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise Exception("espeak did not create output file or file is empty")
            
            audio_data, sr = sf.read(temp_path)
            os.unlink(temp_path)
            
            # Check if audio data is empty
            if len(audio_data) == 0:
                logger.warning(f"espeak produced empty audio for text: '{text[:50]}...'")
                return InferenceResponse(payload=b"", metadata={"sample_rate": self.sample_rate, "duration_ms": 0})
            
            # Convert to mono if stereo
            if len(audio_data.shape) > 1:
                audio_data = np.mean(audio_data, axis=1)
            
            if sr != self.sample_rate:
                target_samples = int(len(audio_data) * self.sample_rate / sr)
                if len(audio_data) > target_samples:
                    audio_data = audio_data[:target_samples]
                else:
                    audio_data = np.pad(audio_data, (0, target_samples - len(audio_data)))
            
            audio_data = audio_data.astype(np.float32)
            
            # Normalize audio (avoid division by zero)
            max_val = np.max(np.abs(audio_data))
            if max_val > 0:
                audio_data = audio_data / max_val
            else:
                logger.warning(f"Audio has zero amplitude for text: '{text[:50]}...'")
                return InferenceResponse(payload=b"", metadata={"sample_rate": self.sample_rate, "duration_ms": 0})
            
            audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
            duration_ms = int(len(audio_data) / self.sample_rate * 1000)
            
            return InferenceResponse(
                payload=audio_bytes,
                metadata={"sample_rate": self.sample_rate, "duration_ms": duration_ms}
            )
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return InferenceResponse(payload=b"", metadata={"sample_rate": self.sample_rate, "duration_ms": 0})


