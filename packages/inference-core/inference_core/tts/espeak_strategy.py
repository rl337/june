from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Any, Dict

import numpy as np
import soundfile as sf

from ..strategies import InferenceRequest, InferenceResponse, TtsStrategy

logger = logging.getLogger(__name__)


class EspeakTtsStrategy(TtsStrategy):
    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    def warmup(self) -> None:
        try:
            result = subprocess.run(
                ["espeak", "--version"], capture_output=True, text=True
            )
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
            text = (
                request.payload
                if isinstance(request.payload, str)
                else str(request.payload)
            )
            voice_id = request.metadata.get("voice_id", "default")
            language = request.metadata.get("language", "en")

        if not text.strip():
            return InferenceResponse(
                payload=b"",
                metadata={"sample_rate": self.sample_rate, "duration_ms": 0},
            )

        text = text.strip()
        word_count = len(text.split())

        # For single words, use slower speed and higher amplitude for better STT recognition
        # Single words need more clarity without context
        if word_count == 1:
            speed = "100"  # Slower for single words (was 120)
            amplitude = "170"  # Higher amplitude for clarity (was 160)
            gap = "15"  # Slightly larger gap (was 10)
        else:
            speed = "120"
            amplitude = "160"
            gap = "10"

        try:
            # Create temp file path (don't create file, espeak will create it)
            fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)  # Close file descriptor, espeak will create the file

            # espeak syntax: espeak [options] text
            # -s: speed in words per minute (slower = clearer for STT)
            # -w: output WAV file
            # -v: voice (en+f3 = English female voice 3, clearer)
            # -a: amplitude (150-180, higher = clearer but may distort)
            # -g: gap between words (10-15ms, helps STT separation)
            # -p: pitch (50 = base, lower = clearer but robotic)
            # Sample rate is typically fixed by espeak, we'll resample if needed
            # Use slower speed and clearer settings for better STT recognition
            cmd = [
                "espeak",
                "-s",
                speed,
                "-a",
                amplitude,
                "-g",
                gap,
                "-p",
                "50",
                "-v",
                "en+f3",
                "-w",
                temp_path,
                text,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL
            )
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
                logger.warning(
                    f"espeak produced empty audio for text: '{text[:50]}...'"
                )
                return InferenceResponse(
                    payload=b"",
                    metadata={"sample_rate": self.sample_rate, "duration_ms": 0},
                )

            # Convert to mono if stereo
            if len(audio_data.shape) > 1:
                audio_data = np.mean(audio_data, axis=1)

            # Better resampling using scipy if available, otherwise linear interpolation
            if sr != self.sample_rate:
                try:
                    from scipy import signal

                    # Use scipy's high-quality resampling
                    num_samples = int(len(audio_data) * self.sample_rate / sr)
                    audio_data = signal.resample(audio_data, num_samples)
                except ImportError:
                    # Fallback to linear interpolation
                    target_samples = int(len(audio_data) * self.sample_rate / sr)
                    if len(audio_data) > target_samples:
                        # Downsample by taking every Nth sample (crude but works)
                        step = len(audio_data) / target_samples
                        indices = np.round(np.arange(0, len(audio_data), step)).astype(
                            int
                        )
                        audio_data = audio_data[
                            np.clip(indices, 0, len(audio_data) - 1)
                        ]
                    else:
                        # Upsample by linear interpolation
                        indices = np.linspace(0, len(audio_data) - 1, target_samples)
                        audio_data = np.interp(
                            indices, np.arange(len(audio_data)), audio_data
                        )

            audio_data = audio_data.astype(np.float32)

            # Normalize audio with better dynamic range
            # Use RMS normalization for more consistent levels
            max_val = np.max(np.abs(audio_data))
            if max_val > 0:
                # Normalize to 0.95 peak to avoid clipping
                audio_data = audio_data / max_val * 0.95
            else:
                logger.warning(f"Audio has zero amplitude for text: '{text[:50]}...'")
                return InferenceResponse(
                    payload=b"",
                    metadata={"sample_rate": self.sample_rate, "duration_ms": 0},
                )

            # Convert to int16 PCM with proper scaling
            # Clamp values to prevent overflow
            audio_data_clamped = np.clip(audio_data, -1.0, 1.0)
            audio_bytes = (audio_data_clamped * 32767).astype(np.int16).tobytes()
            duration_ms = int(len(audio_data) / self.sample_rate * 1000)

            return InferenceResponse(
                payload=audio_bytes,
                metadata={"sample_rate": self.sample_rate, "duration_ms": duration_ms},
            )
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return InferenceResponse(
                payload=b"",
                metadata={"sample_rate": self.sample_rate, "duration_ms": 0},
            )
