"""
Audio format conversion utilities for STT (Speech-to-Text) input requirements.

Provides functions for:
- OGG to WAV conversion (using pydub/ffmpeg)
- Sample rate conversion (16kHz for Whisper)
- Mono channel conversion
- Audio validation (duration, size checks)
- Voice message compression optimization
- Noise reduction
- Volume normalization
"""
import io
import logging
import shutil
from typing import Optional, Tuple

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

# Optional imports for audio enhancement
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

logger = logging.getLogger(__name__)

# Check for FFmpeg/ffprobe availability
_FFPROBE_AVAILABLE = None


def _check_ffprobe_available() -> bool:
    """
    Check if ffprobe (part of FFmpeg) is available in the system PATH.

    Returns:
        True if ffprobe is available, False otherwise
    """
    global _FFPROBE_AVAILABLE
    if _FFPROBE_AVAILABLE is None:
        _FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None
        if not _FFPROBE_AVAILABLE:
            logger.warning(
                "ffprobe is not available in PATH. OGG audio conversion will fail. "
                "FFmpeg (which includes ffprobe) should be installed in the june-base Docker image. "
                "If this error persists, verify that FFmpeg is installed and available in PATH."
            )
    return _FFPROBE_AVAILABLE


def _raise_ffprobe_error(operation: str) -> None:
    """
    Raise a clear error message when ffprobe is not available.

    Args:
        operation: Description of the operation that failed (e.g., "OGG to WAV conversion")

    Raises:
        RuntimeError: Always raises with a clear error message
    """
    error_msg = (
        f"Failed to perform {operation}: ffprobe (part of FFmpeg) is not available. "
        "FFmpeg should be installed in the june-base Docker image. "
        "Please verify that FFmpeg is installed and available in PATH. "
        "Error: [Errno 2] No such file or directory: 'ffprobe'"
    )
    logger.error(error_msg)
    raise RuntimeError(error_msg)


# Constants for audio validation
MAX_AUDIO_DURATION_SECONDS = (
    60.0  # Maximum audio duration in seconds (Telegram ~1 minute)
)
MAX_AUDIO_SIZE_BYTES = 20 * 1024 * 1024  # Maximum audio size: 20 MB

# Constants for voice message compression
# Telegram voice message constraints
TELEGRAM_MAX_DURATION_SECONDS = 60  # ~1 minute maximum
TELEGRAM_RECOMMENDED_BITRATE = 64000  # 64 kbps (good quality)
TELEGRAM_MIN_BITRATE = 24000  # 24 kbps (minimum acceptable quality)
TELEGRAM_MAX_BITRATE = 128000  # 128 kbps (high quality)
TELEGRAM_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB (general Telegram limit)

# Compression presets for different quality/size tradeoffs
COMPRESSION_PRESETS = {
    "high_quality": {
        "bitrate": 96000,  # 96 kbps - high quality, larger files
        "description": "High quality, larger file size",
    },
    "balanced": {
        "bitrate": 64000,  # 64 kbps - balanced quality/size (recommended)
        "description": "Balanced quality and file size",
    },
    "optimized": {
        "bitrate": 48000,  # 48 kbps - optimized for size, good quality
        "description": "Optimized for file size, good quality",
    },
    "aggressive": {
        "bitrate": 32000,  # 32 kbps - aggressive compression, smaller files
        "description": "Aggressive compression, smaller files",
    },
}


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
        RuntimeError: If ffprobe is not available
    """
    # Check for ffprobe availability before attempting conversion
    if not _check_ffprobe_available():
        _raise_ffprobe_error("OGG to WAV conversion")

    try:
        # Load OGG audio from bytes
        audio = AudioSegment.from_ogg(io.BytesIO(ogg_data))

        # Export to WAV format
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        buffer.seek(0)

        wav_data = buffer.read()
        logger.debug(
            f"Converted OGG to WAV: {len(ogg_data)} bytes -> {len(wav_data)} bytes"
        )

        return wav_data

    except CouldntDecodeError as e:
        logger.error(f"Failed to decode OGG audio: {e}")
        raise ValueError(f"Invalid OGG audio data: {e}")
    except FileNotFoundError as e:
        # Check if this is the ffprobe error
        if "ffprobe" in str(e) or "No such file or directory" in str(e):
            _raise_ffprobe_error("OGG to WAV conversion")
        raise
    except Exception as e:
        # Check if this is the ffprobe error
        error_str = str(e)
        if "ffprobe" in error_str or (
            "No such file or directory" in error_str and "ffprobe" in error_str.lower()
        ):
            _raise_ffprobe_error("OGG to WAV conversion")
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
                    # Check for ffprobe before attempting OGG conversion
                    if not _check_ffprobe_available():
                        _raise_ffprobe_error("OGG audio decoding")
                    audio = AudioSegment.from_ogg(io.BytesIO(audio_data))
                except CouldntDecodeError as e:
                    raise ValueError(
                        f"Could not decode audio data (tried WAV, auto-detect, and OGG): {e}"
                    )
                except FileNotFoundError as e:
                    # Check if this is the ffprobe error
                    if "ffprobe" in str(e) or "No such file or directory" in str(e):
                        _raise_ffprobe_error("OGG audio decoding")
                    raise

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
    except FileNotFoundError as e:
        # Check if this is the ffprobe error
        if "ffprobe" in str(e) or "No such file or directory" in str(e):
            _raise_ffprobe_error("audio format conversion")
        raise
    except Exception as e:
        # Check if this is the ffprobe error
        error_str = str(e)
        if "ffprobe" in error_str or (
            "No such file or directory" in error_str and "ffprobe" in error_str.lower()
        ):
            _raise_ffprobe_error("audio format conversion")
        logger.error(f"Error converting to 16kHz mono: {e}")
        raise ValueError(f"Failed to convert to 16kHz mono: {e}")


def validate_audio(
    audio_data: bytes, require_16khz: bool = False, require_mono: bool = False
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


def reduce_noise(audio_data: bytes, reduction_strength: float = 0.5) -> bytes:
    """
    Reduce background noise in audio data using spectral gating.

    Uses librosa's noise reduction techniques to improve audio quality
    by suppressing background noise while preserving speech.

    Args:
        audio_data: WAV audio data as bytes (must be 16kHz mono)
        reduction_strength: Noise reduction strength (0.0-1.0, default: 0.5)
                           Higher values = more aggressive noise reduction

    Returns:
        Enhanced WAV audio data as bytes

    Raises:
        ValueError: If noise reduction fails or librosa is not available
    """
    if not LIBROSA_AVAILABLE or not NUMPY_AVAILABLE:
        logger.warning(
            "librosa/numpy not available for noise reduction. "
            "Install librosa and numpy for noise reduction: pip install librosa numpy"
        )
        # Return original audio if enhancement libraries not available
        return audio_data

    try:
        # Load audio with librosa
        audio_array, sample_rate = librosa.load(
            io.BytesIO(audio_data), sr=16000, mono=True
        )

        # Apply spectral gating noise reduction
        # This technique estimates noise from quiet parts and subtracts it
        # Calculate short-time Fourier transform (STFT)
        stft = librosa.stft(audio_array, hop_length=512, win_length=2048)
        magnitude = np.abs(stft)
        phase = np.angle(stft)

        # Estimate noise floor from first 0.5 seconds (assuming quiet start)
        noise_frames = int(0.5 * sample_rate / 512)  # 0.5 seconds in frames
        if noise_frames > 0 and noise_frames < magnitude.shape[1]:
            noise_floor = np.median(magnitude[:, :noise_frames], axis=1, keepdims=True)
        else:
            # Fallback: estimate from lowest 10% of energy
            noise_floor = np.percentile(magnitude, 10, axis=1, keepdims=True)

        # Apply spectral gating: subtract noise floor with strength factor
        # Use soft thresholding to avoid over-suppression
        threshold = noise_floor * (1.0 + reduction_strength * 2.0)  # Scale threshold
        magnitude_enhanced = np.maximum(
            magnitude - threshold * reduction_strength,
            magnitude * 0.1,  # Preserve at least 10% to avoid complete silence
        )

        # Reconstruct audio from enhanced magnitude and original phase
        stft_enhanced = magnitude_enhanced * np.exp(1j * phase)
        audio_enhanced = librosa.istft(stft_enhanced, hop_length=512, win_length=2048)

        # Normalize to prevent clipping
        max_val = np.max(np.abs(audio_enhanced))
        if max_val > 0:
            audio_enhanced = audio_enhanced / max_val * 0.95  # Leave 5% headroom

        # Convert back to WAV bytes
        # librosa expects float32 in range [-1, 1], convert to int16
        audio_int16 = (audio_enhanced * 32767).astype(np.int16)

        # Create WAV file in memory
        buffer = io.BytesIO()
        import wave

        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit = 2 bytes
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        buffer.seek(0)
        enhanced_audio = buffer.read()

        logger.debug(
            f"Noise reduction applied: {len(audio_data)} bytes -> {len(enhanced_audio)} bytes, "
            f"strength: {reduction_strength}"
        )

        return enhanced_audio

    except Exception as e:
        logger.error(f"Error applying noise reduction: {e}", exc_info=True)
        # Return original audio on error rather than failing completely
        logger.warning("Noise reduction failed, returning original audio")
        return audio_data


def normalize_volume(audio_data: bytes, target_db: float = -20.0) -> bytes:
    """
    Normalize audio volume to a target level.

    Adjusts audio volume to a consistent target level (in dBFS) to improve
    transcription accuracy by ensuring audio is neither too quiet nor too loud.

    Args:
        audio_data: WAV audio data as bytes
        target_db: Target volume level in dBFS (default: -20.0 dBFS)
                   Typical values: -12.0 (loud), -20.0 (normal), -30.0 (quiet)

    Returns:
        Normalized WAV audio data as bytes

    Raises:
        ValueError: If normalization fails
    """
    try:
        # Load audio with pydub
        audio = AudioSegment.from_wav(io.BytesIO(audio_data))

        # Get current volume level
        current_db = audio.dBFS

        # Calculate volume adjustment needed
        volume_change = target_db - current_db

        # Apply normalization
        # Limit adjustment to reasonable range (-30dB to +30dB) to avoid distortion
        volume_change = max(-30.0, min(30.0, volume_change))
        normalized_audio = audio.apply_gain(volume_change)

        # Export to WAV
        buffer = io.BytesIO()
        normalized_audio.export(buffer, format="wav")
        buffer.seek(0)
        normalized_data = buffer.read()

        logger.debug(
            f"Volume normalization: {current_db:.1f} dBFS -> {target_db:.1f} dBFS "
            f"(change: {volume_change:.1f} dB), "
            f"{len(audio_data)} bytes -> {len(normalized_data)} bytes"
        )

        return normalized_data

    except Exception as e:
        logger.error(f"Error normalizing volume: {e}", exc_info=True)
        raise ValueError(f"Failed to normalize volume: {e}")


def enhance_audio_for_stt(
    audio_data: bytes,
    is_ogg: bool = False,
    enable_noise_reduction: bool = True,
    enable_volume_normalization: bool = True,
    noise_reduction_strength: float = 0.5,
    target_volume_db: float = -20.0,
) -> bytes:
    """
    Enhance audio quality for STT processing.

    Applies comprehensive audio preprocessing to improve transcription accuracy:
    1. Format conversion (OGG to WAV, 16kHz, mono)
    2. Noise reduction (optional, using spectral gating)
    3. Volume normalization (optional, to target level)
    4. Validation

    Args:
        audio_data: Audio data as bytes (OGG or WAV)
        is_ogg: If True, treat input as OGG format
        enable_noise_reduction: If True, apply noise reduction (default: True)
        enable_volume_normalization: If True, normalize volume (default: True)
        noise_reduction_strength: Noise reduction strength 0.0-1.0 (default: 0.5)
        target_volume_db: Target volume in dBFS for normalization (default: -20.0)

    Returns:
        Enhanced WAV audio data at 16kHz, mono, validated

    Raises:
        ValueError: If conversion or enhancement fails
        AudioValidationError: If validation fails
    """
    # Step 1: Convert OGG to WAV if needed
    if is_ogg:
        audio_data = convert_ogg_to_wav(audio_data)

    # Step 2: Convert to 16kHz mono (required for noise reduction)
    audio_data = convert_to_16khz_mono(audio_data)

    # Step 3: Apply noise reduction (if enabled and libraries available)
    if enable_noise_reduction:
        audio_data = reduce_noise(
            audio_data, reduction_strength=noise_reduction_strength
        )

    # Step 4: Normalize volume (if enabled)
    if enable_volume_normalization:
        audio_data = normalize_volume(audio_data, target_db=target_volume_db)

    # Step 5: Validate final audio
    validate_audio(audio_data, require_16khz=True, require_mono=True)

    logger.info(
        f"Audio enhancement complete: noise_reduction={enable_noise_reduction}, "
        f"volume_normalization={enable_volume_normalization}, "
        f"final_size={len(audio_data)} bytes"
    )

    return audio_data


def prepare_audio_for_stt(audio_data: bytes, is_ogg: bool = False) -> bytes:
    """
    Prepare audio data for STT service (convenience function).

    Applies comprehensive audio preprocessing to improve transcription accuracy:
    1. Format conversion (OGG to WAV, 16kHz, mono)
    2. Noise reduction (using spectral gating)
    3. Volume normalization (to target level)
    4. Validation

    This function now includes noise reduction and volume normalization
    to improve STT transcription accuracy. For more control over enhancement
    settings, use enhance_audio_for_stt() directly.

    Args:
        audio_data: Audio data as bytes (OGG or WAV)
        is_ogg: If True, treat input as OGG format

    Returns:
        WAV audio data at 16kHz, mono, validated and enhanced

    Raises:
        ValueError: If conversion fails
        AudioValidationError: If validation fails
    """
    # Use enhance_audio_for_stt() with default settings to include
    # noise reduction and volume normalization
    return enhance_audio_for_stt(
        audio_data,
        is_ogg=is_ogg,
        enable_noise_reduction=True,
        enable_volume_normalization=True,
        noise_reduction_strength=0.5,  # Moderate noise reduction
        target_volume_db=-20.0,  # Normal volume level
    )


def compress_audio_for_telegram(
    audio: AudioSegment,
    bitrate: int = TELEGRAM_RECOMMENDED_BITRATE,
    preset: Optional[str] = None,
    max_file_size: int = TELEGRAM_MAX_FILE_SIZE,
) -> Tuple[AudioSegment, dict]:
    """
    Compress audio for Telegram voice messages with optimization.

    Optimizes audio compression to reduce file size while maintaining quality.
    Tests different compression settings and balances quality vs size.

    Args:
        audio: AudioSegment to compress
        bitrate: Target bitrate in bits per second (default: 64 kbps)
        preset: Compression preset name ("high_quality", "balanced", "optimized", "aggressive")
                If provided, overrides bitrate parameter
        max_file_size: Maximum file size in bytes (default: 20 MB)

    Returns:
        Tuple of (compressed_audio, compression_info)
        compression_info contains:
            - original_size: Original audio size estimate
            - compressed_size: Compressed audio size estimate
            - bitrate_used: Bitrate used for compression
            - compression_ratio: Size reduction ratio
            - preset_used: Preset name if used
    """
    # Use preset if provided
    if preset and preset in COMPRESSION_PRESETS:
        bitrate = COMPRESSION_PRESETS[preset]["bitrate"]
        logger.info(
            f"Using compression preset '{preset}': {bitrate} bps ({COMPRESSION_PRESETS[preset]['description']})"
        )

    # Clamp bitrate to valid range
    bitrate = max(TELEGRAM_MIN_BITRATE, min(bitrate, TELEGRAM_MAX_BITRATE))

    # Ensure audio is mono (voice messages are typically mono)
    if audio.channels > 1:
        audio = audio.set_channels(1)
        logger.debug("Converted audio to mono for compression")

    # Ensure sample rate is reasonable (Telegram recommends 48kHz, but 16kHz-48kHz works)
    # Don't upscale unnecessarily, but ensure it's not too low
    if audio.frame_rate < 16000:
        audio = audio.set_frame_rate(16000)
        logger.debug(f"Adjusted sample rate to 16kHz (was {audio.frame_rate}Hz)")
    elif audio.frame_rate > 48000:
        audio = audio.set_frame_rate(48000)
        logger.debug(f"Adjusted sample rate to 48kHz (was {audio.frame_rate}Hz)")

    # Estimate original size (WAV format, uncompressed)
    duration_seconds = len(audio) / 1000.0
    original_size_estimate = int(
        audio.frame_rate * audio.channels * 2 * duration_seconds
    )  # 16-bit = 2 bytes/sample

    # Estimate compressed size (OGG/OPUS at target bitrate)
    compressed_size_estimate = int(
        (bitrate / 8) * duration_seconds
    )  # bitrate in bits, convert to bytes

    # If compressed size exceeds max_file_size, reduce bitrate
    if compressed_size_estimate > max_file_size:
        # Calculate required bitrate to fit within max_file_size
        required_bitrate = int((max_file_size * 8) / duration_seconds)
        bitrate = max(TELEGRAM_MIN_BITRATE, min(required_bitrate, bitrate))
        # Recalculate compressed size estimate with new bitrate
        compressed_size_estimate = int((bitrate / 8) * duration_seconds)
        logger.warning(
            f"Compressed size estimate ({compressed_size_estimate} bytes) exceeds max_file_size "
            f"({max_file_size} bytes). Reducing bitrate to {bitrate} bps."
        )

    compression_info = {
        "original_size": original_size_estimate,
        "compressed_size": compressed_size_estimate,
        "bitrate_used": bitrate,
        "compression_ratio": original_size_estimate / max(compressed_size_estimate, 1),
        "preset_used": preset if preset and preset in COMPRESSION_PRESETS else None,
        "duration_seconds": duration_seconds,
    }

    logger.info(
        f"Audio compression: {duration_seconds:.2f}s, {bitrate} bps, "
        f"estimated size: {compressed_size_estimate / 1024:.1f} KB "
        f"(compression ratio: {compression_info['compression_ratio']:.2f}x)"
    )

    return audio, compression_info


def export_audio_to_ogg_optimized(
    audio: AudioSegment,
    output_path: str,
    bitrate: int = TELEGRAM_RECOMMENDED_BITRATE,
    preset: Optional[str] = None,
    max_file_size: int = TELEGRAM_MAX_FILE_SIZE,
) -> dict:
    """
    Export audio to OGG/OPUS format with compression optimization.

    Optimizes compression to reduce file size while maintaining quality.
    Tests different compression settings and balances quality vs size.

    Args:
        audio: AudioSegment to export
        output_path: Path to output OGG file
        bitrate: Target bitrate in bits per second (default: 64 kbps)
        preset: Compression preset name ("high_quality", "balanced", "optimized", "aggressive")
                If provided, overrides bitrate parameter
        max_file_size: Maximum file size in bytes (default: 20 MB)

    Returns:
        Dictionary with compression information:
            - original_size: Original audio size estimate
            - compressed_size: Actual compressed file size
            - bitrate_used: Bitrate used for compression
            - compression_ratio: Size reduction ratio
            - preset_used: Preset name if used
            - file_path: Path to output file

    Raises:
        ValueError: If export fails
    """
    import os

    # Compress audio
    compressed_audio, compression_info = compress_audio_for_telegram(
        audio, bitrate=bitrate, preset=preset, max_file_size=max_file_size
    )

    # Export to OGG/OPUS format
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Export with optimized settings
        compressed_audio.export(
            output_path,
            format="ogg",
            codec="libopus",
            bitrate=f"{compression_info['bitrate_used'] // 1000}k",  # Convert to kbps string
            parameters=[
                "-application",
                "voip",  # Optimize for voice
                "-ar",
                "48000",  # 48kHz sample rate (Telegram recommended)
            ],
        )

        # Get actual file size
        if os.path.exists(output_path):
            actual_size = os.path.getsize(output_path)
            compression_info["compressed_size"] = actual_size
            compression_info["compression_ratio"] = compression_info[
                "original_size"
            ] / max(actual_size, 1)
            compression_info["file_path"] = output_path

            logger.info(
                f"Exported audio to OGG: {output_path}, "
                f"size: {actual_size / 1024:.1f} KB, "
                f"bitrate: {compression_info['bitrate_used']} bps, "
                f"compression ratio: {compression_info['compression_ratio']:.2f}x"
            )
        else:
            raise ValueError(f"Output file was not created: {output_path}")

        return compression_info

    except Exception as e:
        logger.error(f"Failed to export audio to OGG: {e}", exc_info=True)
        raise ValueError(f"Failed to export audio to OGG: {e}")


def find_optimal_compression(
    audio: AudioSegment,
    max_file_size: int = TELEGRAM_MAX_FILE_SIZE,
    quality_threshold: float = 0.8,
) -> Tuple[str, dict]:
    """
    Find optimal compression preset for audio based on file size constraints.

    Tests different compression presets and selects the best one that:
    - Fits within max_file_size
    - Maintains acceptable quality (based on bitrate)

    Args:
        audio: AudioSegment to compress
        max_file_size: Maximum file size in bytes
        quality_threshold: Minimum quality threshold (0.0-1.0, based on bitrate ratio)

    Returns:
        Tuple of (best_preset_name, compression_info)
    """
    duration_seconds = len(audio) / 1000.0

    best_preset = None
    best_info = None
    best_score = -1

    # Test each preset
    for preset_name, preset_config in COMPRESSION_PRESETS.items():
        bitrate = preset_config["bitrate"]
        estimated_size = int((bitrate / 8) * duration_seconds)

        # Skip if estimated size exceeds max_file_size
        if estimated_size > max_file_size:
            logger.debug(
                f"Preset '{preset_name}' ({bitrate} bps) would exceed max_file_size, skipping"
            )
            continue

        # Calculate quality score (based on bitrate relative to max)
        quality_score = bitrate / TELEGRAM_MAX_BITRATE

        # Skip if quality is below threshold
        if quality_score < quality_threshold:
            logger.debug(
                f"Preset '{preset_name}' quality score {quality_score:.2f} below threshold {quality_threshold}, skipping"
            )
            continue

        # Calculate overall score (balance between quality and file size)
        # Higher bitrate = better quality, but larger file
        # We want the best quality that fits within size constraints
        size_efficiency = 1.0 - (
            estimated_size / max_file_size
        )  # How much room we have
        score = quality_score * 0.7 + size_efficiency * 0.3  # Weight quality more

        if score > best_score:
            best_score = score
            best_preset = preset_name
            best_info = {
                "preset": preset_name,
                "bitrate": bitrate,
                "estimated_size": estimated_size,
                "quality_score": quality_score,
                "size_efficiency": size_efficiency,
                "overall_score": score,
            }

    if best_preset is None:
        # Fall back to most aggressive compression
        logger.warning("No preset fits constraints, using most aggressive compression")
        best_preset = "aggressive"
        best_info = {
            "preset": "aggressive",
            "bitrate": COMPRESSION_PRESETS["aggressive"]["bitrate"],
            "estimated_size": int(
                (COMPRESSION_PRESETS["aggressive"]["bitrate"] / 8) * duration_seconds
            ),
            "quality_score": COMPRESSION_PRESETS["aggressive"]["bitrate"]
            / TELEGRAM_MAX_BITRATE,
            "size_efficiency": 1.0,
            "overall_score": 0.0,
        }

    logger.info(
        f"Selected optimal compression preset: '{best_preset}' (score: {best_score:.2f})"
    )
    return best_preset, best_info
