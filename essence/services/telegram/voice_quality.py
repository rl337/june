"""
Voice message quality scoring and feedback.

Analyzes voice messages for:
- Volume level (too quiet or too loud)
- Background noise detection
- Speech clarity and intelligibility
- Overall quality assessment

Provides feedback and improvement suggestions to users.
"""
import io
import logging
import subprocess
import tempfile
import os
from typing import Dict, List, Any, Optional

try:
    import numpy as np
    import librosa

    NUMPY_AVAILABLE = True
    LIBROSA_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    LIBROSA_AVAILABLE = False
    np = None
    librosa = None

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

logger = logging.getLogger(__name__)


class VoiceQualityError(Exception):
    """Exception raised for voice quality analysis errors."""

    pass


class VoiceQualityScorer:
    """Scores voice message quality and provides feedback."""

    def __init__(self):
        """Initialize the voice quality scorer."""
        if not NUMPY_AVAILABLE:
            logger.warning(
                "numpy not installed. Voice quality scoring will have limited functionality. "
                "Install numpy for full features: pip install numpy"
            )
        if not LIBROSA_AVAILABLE:
            logger.warning(
                "librosa not installed. Voice quality scoring will have limited functionality. "
                "Install librosa for full features: pip install librosa"
            )

    def score_voice_message(
        self, audio_data: bytes, audio_format: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Score the quality of a voice message from audio data.

        Args:
            audio_data: Audio data as bytes (WAV, FLAC, OGG, etc.)
            audio_format: Optional format hint (e.g., 'wav', 'ogg', 'flac')

        Returns:
            Dictionary with:
                - overall_score: Overall quality score (0-100)
                - volume_score: Volume level score (0-100)
                - clarity_score: Speech clarity score (0-100)
                - noise_score: Noise level score (0-100, higher = less noise)
                - feedback: Textual feedback about quality
                - suggestions: List of improvement suggestions

        Raises:
            VoiceQualityError: If audio cannot be analyzed
        """
        if not audio_data or len(audio_data) < 100:
            raise VoiceQualityError("Audio data is too small or empty")

        # Convert to WAV if needed for analysis
        wav_data = self._ensure_wav_format(audio_data, audio_format)

        try:
            # Analyze audio using multiple methods
            if NUMPY_AVAILABLE and LIBROSA_AVAILABLE:
                analysis = self._analyze_with_librosa(wav_data)
            elif NUMPY_AVAILABLE:
                analysis = self._analyze_with_numpy(wav_data)
            else:
                # Try ffprobe, fall back to basic analysis if not available
                try:
                    analysis = self._analyze_with_ffprobe(wav_data)
                except (VoiceQualityError, FileNotFoundError, OSError):
                    # Last resort: basic analysis using pydub only
                    analysis = self._analyze_with_pydub(wav_data)

            # Calculate scores
            volume_score = self._calculate_volume_score(analysis)
            clarity_score = self._calculate_clarity_score(analysis)
            noise_score = self._calculate_noise_score(analysis)

            # Calculate overall score (weighted average)
            overall_score = volume_score * 0.3 + clarity_score * 0.4 + noise_score * 0.3

            # Generate feedback and suggestions
            feedback = self._generate_feedback(
                analysis, volume_score, clarity_score, noise_score
            )
            suggestions = self._generate_suggestions(
                analysis, volume_score, clarity_score, noise_score
            )

            return {
                "overall_score": round(overall_score, 1),
                "volume_score": round(volume_score, 1),
                "clarity_score": round(clarity_score, 1),
                "noise_score": round(noise_score, 1),
                "feedback": feedback,
                "suggestions": suggestions,
                "analysis_details": {
                    "rms_level": analysis.get("rms_level", 0),
                    "peak_level": analysis.get("peak_level", 0),
                    "snr_estimate": analysis.get("snr_estimate", 0),
                    "duration_seconds": analysis.get("duration_seconds", 0),
                },
            }

        except Exception as e:
            logger.error(f"Error analyzing voice quality: {e}", exc_info=True)
            raise VoiceQualityError(f"Failed to analyze audio: {str(e)}")

    def _ensure_wav_format(
        self, audio_data: bytes, audio_format: Optional[str] = None
    ) -> bytes:
        """
        Convert audio data to WAV format if needed.

        Args:
            audio_data: Audio data as bytes
            audio_format: Optional format hint

        Returns:
            WAV audio data as bytes
        """
        try:
            # Try to load audio from bytes
            audio = None
            if audio_format == "wav":
                audio = AudioSegment.from_wav(io.BytesIO(audio_data))
            elif audio_format == "ogg":
                audio = AudioSegment.from_ogg(io.BytesIO(audio_data))
            else:
                # Try auto-detection
                try:
                    audio = AudioSegment.from_file(io.BytesIO(audio_data))
                except CouldntDecodeError:
                    # Try OGG as fallback
                    try:
                        audio = AudioSegment.from_ogg(io.BytesIO(audio_data))
                    except CouldntDecodeError:
                        raise VoiceQualityError("Could not decode audio data")

            # Export to WAV
            buffer = io.BytesIO()
            audio.export(buffer, format="wav")
            buffer.seek(0)
            return buffer.read()

        except Exception as e:
            logger.error(f"Error converting audio to WAV: {e}")
            raise VoiceQualityError(f"Failed to convert audio to WAV: {str(e)}")

    def _analyze_with_librosa(self, wav_data: bytes) -> Dict[str, Any]:
        """
        Analyze audio using librosa for detailed metrics.

        Args:
            wav_data: WAV audio data as bytes

        Returns:
            Dictionary with analysis metrics
        """
        try:
            # Load audio with librosa
            audio_array, sample_rate = librosa.load(io.BytesIO(wav_data), sr=None)
            duration_seconds = len(audio_array) / sample_rate

            # Calculate RMS (Root Mean Square) - average volume level
            rms = np.sqrt(np.mean(audio_array**2))

            # Calculate peak level
            peak = np.max(np.abs(audio_array))

            # Estimate SNR (Signal-to-Noise Ratio)
            # Use spectral analysis to separate signal from noise
            # Simple approach: compare energy in speech frequencies vs all frequencies
            fft = np.fft.fft(audio_array)
            magnitude = np.abs(fft)

            # Speech frequencies are typically 300-3400 Hz
            speech_freq_min = int(300 * len(magnitude) / sample_rate)
            speech_freq_max = int(3400 * len(magnitude) / sample_rate)

            speech_energy = np.sum(magnitude[speech_freq_min:speech_freq_max])
            total_energy = np.sum(magnitude)

            # SNR estimate (ratio of speech energy to total energy)
            snr_estimate = 20 * np.log10(
                speech_energy / max(total_energy - speech_energy, 1e-10)
            )

            # Detect clipping (samples at maximum amplitude)
            clipping_ratio = np.sum(np.abs(audio_array) >= 0.99) / len(audio_array)

            # Frequency analysis for clarity
            # Calculate spectral centroid (brightness indicator)
            spectral_centroid = np.mean(
                librosa.feature.spectral_centroid(y=audio_array, sr=sample_rate)
            )

            return {
                "rms_level": float(rms),
                "peak_level": float(peak),
                "snr_estimate": float(snr_estimate),
                "duration_seconds": float(duration_seconds),
                "clipping_ratio": float(clipping_ratio),
                "spectral_centroid": float(spectral_centroid),
                "sample_rate": int(sample_rate),
            }

        except Exception as e:
            logger.error(f"Error analyzing with librosa: {e}", exc_info=True)
            raise VoiceQualityError(f"Librosa analysis failed: {str(e)}")

    def _analyze_with_numpy(self, wav_data: bytes) -> Dict[str, Any]:
        """
        Analyze audio using numpy for basic metrics.

        Args:
            wav_data: WAV audio data as bytes

        Returns:
            Dictionary with analysis metrics
        """
        try:
            import wave

            with wave.open(io.BytesIO(wav_data), "r") as wav_file:
                sample_rate = wav_file.getframerate()
                num_channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                num_frames = wav_file.getnframes()

                # Read audio data
                audio_bytes = wav_file.readframes(num_frames)

                # Convert to numpy array
                if sample_width == 1:
                    dtype = np.uint8
                    audio_data = np.frombuffer(audio_bytes, dtype=dtype).astype(
                        np.float32
                    )
                    audio_data = (audio_data - 128) / 128.0
                elif sample_width == 2:
                    dtype = np.int16
                    audio_data = np.frombuffer(audio_bytes, dtype=dtype).astype(
                        np.float32
                    )
                    audio_data = audio_data / 32768.0
                elif sample_width == 4:
                    dtype = np.int32
                    audio_data = np.frombuffer(audio_bytes, dtype=dtype).astype(
                        np.float32
                    )
                    audio_data = audio_data / 2147483648.0
                else:
                    raise VoiceQualityError(f"Unsupported sample width: {sample_width}")

                # Use first channel for mono analysis
                if num_channels > 1:
                    audio_data = audio_data.reshape(-1, num_channels)
                    audio_data = audio_data[:, 0]

                # Calculate metrics
                rms = np.sqrt(np.mean(audio_data**2))
                peak = np.max(np.abs(audio_data))
                duration_seconds = len(audio_data) / sample_rate

                # Simple SNR estimate using RMS
                # Assume noise floor is minimum RMS in small windows
                window_size = int(sample_rate * 0.1)  # 100ms windows
                if len(audio_data) > window_size:
                    num_windows = len(audio_data) // window_size
                    window_rms = []
                    for i in range(num_windows):
                        window = audio_data[i * window_size : (i + 1) * window_size]
                        window_rms.append(np.sqrt(np.mean(window**2)))
                    noise_floor = np.min(window_rms)
                    snr_estimate = 20 * np.log10(rms / max(noise_floor, 1e-10))
                else:
                    snr_estimate = 20.0  # Default if too short

                return {
                    "rms_level": float(rms),
                    "peak_level": float(peak),
                    "snr_estimate": float(snr_estimate),
                    "duration_seconds": float(duration_seconds),
                    "sample_rate": int(sample_rate),
                }

        except Exception as e:
            logger.error(f"Error analyzing with numpy: {e}", exc_info=True)
            raise VoiceQualityError(f"Numpy analysis failed: {str(e)}")

    def _analyze_with_pydub(self, wav_data: bytes) -> Dict[str, Any]:
        """
        Analyze audio using pydub only (basic fallback).

        Args:
            wav_data: WAV audio data as bytes

        Returns:
            Dictionary with basic analysis metrics
        """
        try:
            audio = AudioSegment.from_wav(io.BytesIO(wav_data))
            duration_seconds = len(audio) / 1000.0  # pydub returns milliseconds

            # Basic estimates using pydub
            # Normalize dBFS to RMS estimate
            # dBFS ranges from -infinity (silence) to 0 (full scale)
            # Typical speech is around -12 to -6 dBFS
            dbFS = audio.dBFS

            # Convert dBFS to normalized RMS (0-1 range)
            # dBFS = 20 * log10(rms_normalized)
            # rms_normalized = 10^(dBFS / 20)
            # For typical speech at -12 dBFS: rms = 10^(-12/20) ≈ 0.25
            if dbFS > -100 and dbFS <= 0:  # Valid dBFS range
                rms_estimate = 10 ** (dbFS / 20.0)
            elif dbFS <= -100:
                rms_estimate = 0.001  # Very quiet
            else:
                rms_estimate = 0.1  # Default for invalid values

            # Peak estimate: typically 3-6 dB above RMS
            # Peak ≈ RMS * 10^(6/20) ≈ RMS * 2
            peak_estimate = min(1.0, rms_estimate * 2.0)

            # SNR estimate: use loudness as proxy
            # Louder audio (higher dBFS) typically has better SNR
            if dbFS > -6:
                snr_estimate = 30.0  # Very loud, likely good SNR
            elif dbFS > -12:
                snr_estimate = 25.0  # Good level
            elif dbFS > -20:
                snr_estimate = 20.0  # Moderate
            elif dbFS > -30:
                snr_estimate = 15.0  # Quiet
            else:
                snr_estimate = 10.0  # Very quiet, likely poor SNR

            return {
                "rms_level": float(rms_estimate),
                "peak_level": float(peak_estimate),
                "snr_estimate": float(snr_estimate),
                "duration_seconds": float(duration_seconds),
                "sample_rate": int(audio.frame_rate),
            }

        except Exception as e:
            logger.error(f"Error analyzing with pydub: {e}", exc_info=True)
            raise VoiceQualityError(f"Pydub analysis failed: {str(e)}")

    def _analyze_with_ffprobe(self, wav_data: bytes) -> Dict[str, Any]:
        """
        Analyze audio using ffprobe as fallback.

        Args:
            wav_data: WAV audio data as bytes

        Returns:
            Dictionary with analysis metrics
        """
        try:
            # Write to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(wav_data)
                temp_path = temp_file.name

            try:
                # Use ffprobe to get audio info
                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "quiet",
                        "-print_format",
                        "json",
                        "-show_format",
                        "-show_streams",
                        temp_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode != 0:
                    raise VoiceQualityError(f"ffprobe failed: {result.stderr}")

                import json

                probe_data = json.loads(result.stdout)

                # Extract basic info
                stream = probe_data.get("streams", [{}])[0]
                format_info = probe_data.get("format", {})

                duration = float(format_info.get("duration", 0))
                sample_rate = int(stream.get("sample_rate", 16000))

                # Basic estimates (ffprobe doesn't give us RMS/SNR)
                return {
                    "rms_level": 0.1,  # Default estimate
                    "peak_level": 0.5,  # Default estimate
                    "snr_estimate": 20.0,  # Default estimate
                    "duration_seconds": duration,
                    "sample_rate": sample_rate,
                }

            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except Exception as e:
            logger.error(f"Error analyzing with ffprobe: {e}", exc_info=True)
            raise VoiceQualityError(f"ffprobe analysis failed: {str(e)}")

    def _calculate_volume_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate volume level score (0-100)."""
        rms = analysis.get("rms_level", 0)

        # Optimal RMS is around 0.1-0.3 for speech
        # Too quiet: < 0.05
        # Too loud: > 0.5
        # Clipping: > 0.95

        if rms < 0.01:
            return 0.0  # Too quiet
        elif rms < 0.05:
            return 30.0 + (rms - 0.01) / 0.04 * 20.0  # 30-50
        elif rms < 0.1:
            return 50.0 + (rms - 0.05) / 0.05 * 30.0  # 50-80
        elif rms < 0.3:
            return 80.0 + (rms - 0.1) / 0.2 * 15.0  # 80-95
        elif rms < 0.5:
            return 95.0 - (rms - 0.3) / 0.2 * 15.0  # 95-80
        elif rms < 0.95:
            return 80.0 - (rms - 0.5) / 0.45 * 30.0  # 80-50
        else:
            return max(0.0, 50.0 - (rms - 0.95) / 0.05 * 50.0)  # 50-0 (clipping)

    def _calculate_clarity_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate speech clarity score (0-100)."""
        clipping_ratio = analysis.get("clipping_ratio", 0)
        spectral_centroid = analysis.get("spectral_centroid", 0)
        peak = analysis.get("peak_level", 0)

        # Clipping reduces clarity
        clipping_penalty = min(100.0, clipping_ratio * 200.0)  # Up to 100 point penalty

        # Spectral centroid indicates brightness/clarity
        # Speech typically has centroid around 1000-3000 Hz
        # Lower = muffled, higher = clearer (but too high = harsh)
        if spectral_centroid > 0:
            if spectral_centroid < 500:
                centroid_score = 40.0  # Too muffled
            elif spectral_centroid < 1000:
                centroid_score = 60.0
            elif spectral_centroid < 3000:
                centroid_score = 90.0  # Optimal range
            elif spectral_centroid < 5000:
                centroid_score = 70.0
            else:
                centroid_score = 50.0  # Too harsh
        else:
            centroid_score = 70.0  # Default if not available

        # Peak level affects clarity (distortion)
        if peak > 0.99:
            peak_penalty = 30.0  # Severe clipping
        elif peak > 0.9:
            peak_penalty = 15.0  # Some clipping
        else:
            peak_penalty = 0.0

        clarity = centroid_score - clipping_penalty - peak_penalty
        return max(0.0, min(100.0, clarity))

    def _calculate_noise_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate noise level score (0-100, higher = less noise)."""
        snr = analysis.get("snr_estimate", 20.0)

        # SNR thresholds:
        # Excellent: > 30 dB
        # Good: 20-30 dB
        # Fair: 10-20 dB
        # Poor: < 10 dB

        if snr >= 30:
            return 90.0 + (snr - 30) / 20.0 * 10.0  # 90-100
        elif snr >= 20:
            return 70.0 + (snr - 20) / 10.0 * 20.0  # 70-90
        elif snr >= 10:
            return 40.0 + (snr - 10) / 10.0 * 30.0  # 40-70
        elif snr >= 0:
            return 10.0 + (snr - 0) / 10.0 * 30.0  # 10-40
        else:
            return max(0.0, 10.0 + snr / 10.0 * 10.0)  # 0-10

    def _generate_feedback(
        self,
        analysis: Dict[str, Any],
        volume_score: float,
        clarity_score: float,
        noise_score: float,
    ) -> str:
        """Generate textual feedback about quality."""
        feedback_parts = []

        # Volume feedback
        if volume_score < 30:
            feedback_parts.append(
                "Volume is too quiet - speak closer to the microphone"
            )
        elif volume_score < 50:
            feedback_parts.append("Volume is low - try speaking louder or closer")
        elif volume_score > 90:
            feedback_parts.append("Volume is excellent")

        # Clarity feedback
        if clarity_score < 40:
            feedback_parts.append(
                "Speech clarity is poor - check microphone quality or environment"
            )
        elif clarity_score < 60:
            feedback_parts.append("Speech clarity could be improved")
        elif clarity_score > 80:
            feedback_parts.append("Speech clarity is good")

        # Noise feedback
        if noise_score < 30:
            feedback_parts.append(
                "High background noise detected - record in a quieter environment"
            )
        elif noise_score < 50:
            feedback_parts.append("Some background noise present")
        elif noise_score > 80:
            feedback_parts.append("Low background noise - good recording environment")

        if not feedback_parts:
            return "Audio quality is acceptable"

        return ". ".join(feedback_parts) + "."

    def _generate_suggestions(
        self,
        analysis: Dict[str, Any],
        volume_score: float,
        clarity_score: float,
        noise_score: float,
    ) -> List[str]:
        """Generate improvement suggestions."""
        suggestions = []

        if volume_score < 50:
            suggestions.append("Speak closer to the microphone")
            suggestions.append("Increase microphone gain if available")

        if clarity_score < 60:
            suggestions.append("Check microphone positioning")
            suggestions.append("Ensure microphone is not covered or obstructed")
            suggestions.append("Try a different microphone if available")

        if noise_score < 50:
            suggestions.append("Record in a quieter environment")
            suggestions.append("Move away from noise sources (fans, traffic, etc.)")
            suggestions.append("Use a directional microphone if available")

        if not suggestions:
            suggestions.append(
                "Audio quality is good - no specific improvements needed"
            )

        return suggestions
