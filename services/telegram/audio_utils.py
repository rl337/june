"""
Audio format conversion utilities for STT (Speech-to-Text) input requirements.

Provides functions for:
- OGG to WAV conversion (using pydub/ffmpeg)
- Sample rate conversion (16kHz for Whisper)
- Mono channel conversion
- Audio validation (duration, size checks)
"""
import io
import logging
from typing import Optional

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

logger = logging.getLogger(__name__)

# Constants for audio validation
MAX_AUDIO_DURATION_SECONDS = 60.0  # Maximum audio duration in seconds (Telegram ~1 minute)
MAX_AUDIO_SIZE_BYTES = 20 * 1024 * 1024  # Maximum audio size: 20 MB


class AudioValidationError(Exception):
    """Raised when audio validation fails."""
    pass


def convert_ogg_to_wav(ogg_data: bytes) -> bytes:
    """
    Convert OGG audio data to WAV format.
    
    Args:
        ogg_data: OGG audio data as bytes
        
    Returns:
        WAV audio data as bytes
        
    Raises:
        ValueError: If the input data cannot be decoded as OGG audio
    """
    try:
        # Load OGG audio from bytes
        audio = AudioSegment.from_ogg(io.BytesIO(ogg_data))
        
        # Export to WAV format
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        buffer.seek(0)
        
        wav_data = buffer.read()
        logger.debug(f"Converted OGG to WAV: {len(ogg_data)} bytes -> {len(wav_data)} bytes")
        
        return wav_data
        
    except CouldntDecodeError as e:
        logger.error(f"Failed to decode OGG audio: {e}")
        raise ValueError(f"Invalid OGG audio data: {e}")
    except Exception as e:
        logger.error(f"Error converting OGG to WAV: {e}")
        raise ValueError(f"Failed to convert OGG to WAV: {e}")


def convert_to_16khz_mono(audio_data: bytes) -> bytes:
    """
    Convert audio data to 16kHz mono WAV format (required for Whisper STT).
    
    Args:
        audio_data: Audio data as bytes (WAV, OGG, or other format supported by pydub)
        
    Returns:
        WAV audio data as bytes at 16kHz sample rate, mono channel
        
    Raises:
        ValueError: If the input data cannot be decoded as audio
    """
    try:
        # Try to load audio from bytes (pydub can auto-detect format)
        # Try WAV first (most common), then try generic format
        audio = None
        try:
            audio = AudioSegment.from_wav(io.BytesIO(audio_data))
        except (CouldntDecodeError, Exception):
            # Try auto-detection (pydub will try multiple formats)
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_data))
            except CouldntDecodeError:
                # Last attempt: try as OGG
                try:
                    audio = AudioSegment.from_ogg(io.BytesIO(audio_data))
                except CouldntDecodeError as e:
                    raise ValueError(f"Could not decode audio data (tried WAV, auto-detect, and OGG): {e}")
        
        # Convert to 16kHz sample rate
        audio = audio.set_frame_rate(16000)
        
        # Convert to mono channel
        audio = audio.set_channels(1)
        
        # Export to WAV format
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        buffer.seek(0)
        
        wav_data = buffer.read()
        logger.debug(
            f"Converted to 16kHz mono: {len(audio_data)} bytes -> {len(wav_data)} bytes, "
            f"duration: {len(audio) / 1000.0:.2f}s"
        )
        
        return wav_data
        
    except ValueError:
        # Re-raise ValueError as-is
        raise
    except CouldntDecodeError as e:
        logger.error(f"Failed to decode audio: {e}")
        raise ValueError(f"Invalid audio data: {e}")
    except Exception as e:
        logger.error(f"Error converting to 16kHz mono: {e}")
        raise ValueError(f"Failed to convert to 16kHz mono: {e}")


def validate_audio(
    audio_data: bytes,
    require_16khz: bool = False,
    require_mono: bool = False
) -> None:
    """
    Validate audio data for STT input requirements.
    
    Checks:
    - Audio format is valid
    - Duration is within limits (MAX_AUDIO_DURATION_SECONDS)
    - Size is within limits (MAX_AUDIO_SIZE_BYTES)
    - Optionally: Sample rate is 16kHz (if require_16khz=True)
    - Optionally: Channels is mono (if require_mono=True)
    
    Args:
        audio_data: Audio data as bytes
        require_16khz: If True, require 16kHz sample rate
        require_mono: If True, require mono channel
        
    Raises:
        AudioValidationError: If validation fails
    """
    # Check file size
    if len(audio_data) > MAX_AUDIO_SIZE_BYTES:
        raise AudioValidationError(
            f"Audio file too large: {len(audio_data)} bytes "
            f"(maximum: {MAX_AUDIO_SIZE_BYTES} bytes)"
        )
    
    # Check if data is too small to be valid audio
    if len(audio_data) < 100:  # WAV header is at least 44 bytes, but allow some margin
        raise AudioValidationError(
            f"Audio data too small: {len(audio_data)} bytes (minimum expected: 100 bytes)"
        )
    
    try:
        # Load and parse audio (try multiple formats)
        audio = None
        try:
            audio = AudioSegment.from_wav(io.BytesIO(audio_data))
        except (CouldntDecodeError, Exception):
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_data))
            except CouldntDecodeError as e:
                raise AudioValidationError(f"Invalid audio format: {e}")
        
        # Check duration
        duration_seconds = len(audio) / 1000.0  # pydub returns duration in milliseconds
        if duration_seconds > MAX_AUDIO_DURATION_SECONDS:
            raise AudioValidationError(
                f"Audio duration too long: {duration_seconds:.2f}s "
                f"(maximum: {MAX_AUDIO_DURATION_SECONDS}s)"
            )
        
        # Check minimum duration (audio should be at least 0.1 seconds)
        if duration_seconds < 0.1:
            raise AudioValidationError(
                f"Audio duration too short: {duration_seconds:.2f}s (minimum: 0.1s)"
            )
        
        # Optional: Check sample rate
        if require_16khz and audio.frame_rate != 16000:
            raise AudioValidationError(
                f"Audio sample rate must be 16kHz, got {audio.frame_rate}Hz"
            )
        
        # Optional: Check channels
        if require_mono and audio.channels != 1:
            raise AudioValidationError(
                f"Audio must be mono (1 channel), got {audio.channels} channels"
            )
        
        logger.debug(
            f"Audio validation passed: {len(audio_data)} bytes, "
            f"{duration_seconds:.2f}s, {audio.frame_rate}Hz, {audio.channels} channels"
        )
        
    except CouldntDecodeError as e:
        logger.error(f"Failed to decode audio for validation: {e}")
        raise AudioValidationError(f"Invalid audio format: {e}")
    except AudioValidationError:
        # Re-raise validation errors
        raise
    except Exception as e:
        logger.error(f"Error validating audio: {e}")
        raise AudioValidationError(f"Failed to validate audio: {e}")


def prepare_audio_for_stt(audio_data: bytes, is_ogg: bool = False) -> bytes:
    """
    Prepare audio data for STT service (convenience function).
    
    If audio is OGG, converts to WAV first.
    Then converts to 16kHz mono format.
    Finally validates the audio.
    
    Args:
        audio_data: Audio data as bytes (OGG or WAV)
        is_ogg: If True, treat input as OGG format
        
    Returns:
        WAV audio data at 16kHz, mono, validated
        
    Raises:
        ValueError: If conversion fails
        AudioValidationError: If validation fails
    """
    # Convert OGG to WAV if needed
    if is_ogg:
        audio_data = convert_ogg_to_wav(audio_data)
    
    # Convert to 16kHz mono
    audio_data = convert_to_16khz_mono(audio_data)
    
    # Validate
    validate_audio(audio_data, require_16khz=True, require_mono=True)
    
    return audio_data
