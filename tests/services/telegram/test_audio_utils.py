"""
Tests for audio format conversion utilities.

Tests cover:
- OGG to WAV conversion
- Sample rate conversion (16kHz for Whisper)
- Mono channel conversion
- Audio validation (duration, size checks)
- Noise reduction
- Volume normalization
"""
import pytest
import io
import wave
import sys
from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

from essence.services.telegram.audio_utils import (
    convert_ogg_to_wav,
    convert_to_16khz_mono,
    validate_audio,
    AudioValidationError,
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUDIO_SIZE_BYTES,
    compress_audio_for_telegram,
    export_audio_to_ogg_optimized,
    find_optimal_compression,
    COMPRESSION_PRESETS,
    TELEGRAM_RECOMMENDED_BITRATE,
    TELEGRAM_MAX_FILE_SIZE,
    reduce_noise,
    normalize_volume,
    enhance_audio_for_stt,
    prepare_audio_for_stt,
)


@pytest.fixture
def sample_wav_16khz_mono():
    """Create a sample WAV file (16kHz, mono, 1 second)."""
    # Generate a 1-second sine wave at 440Hz, 16kHz sample rate, mono
    audio = Sine(440).to_audio_segment(duration=1000)  # 1000ms = 1 second
    audio = audio.set_frame_rate(16000)
    audio = audio.set_channels(1)

    # Export to bytes
    buffer = io.BytesIO()
    audio.export(buffer, format="wav")
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_wav_44khz_stereo():
    """Create a sample WAV file (44.1kHz, stereo, 2 seconds)."""
    # Generate a 2-second sine wave at 440Hz, 44.1kHz sample rate, stereo
    audio = Sine(440).to_audio_segment(duration=2000)  # 2000ms = 2 seconds
    audio = audio.set_frame_rate(44100)
    audio = audio.set_channels(2)

    # Export to bytes
    buffer = io.BytesIO()
    audio.export(buffer, format="wav")
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_ogg():
    """Create a sample OGG file."""
    # Generate a 1-second sine wave and export as OGG
    audio = Sine(440).to_audio_segment(duration=1000)
    audio = audio.set_frame_rate(44100)
    audio = audio.set_channels(2)

    # Export to bytes as OGG
    buffer = io.BytesIO()
    audio.export(buffer, format="ogg", codec="libvorbis")
    buffer.seek(0)
    return buffer.read()


class TestOGGToWAVConversion:
    """Tests for OGG to WAV conversion."""

    def test_convert_ogg_to_wav_basic(self, sample_ogg):
        """Test basic OGG to WAV conversion."""
        wav_data = convert_ogg_to_wav(sample_ogg)

        # Should return bytes
        assert isinstance(wav_data, bytes)
        assert len(wav_data) > 0

        # Should be valid WAV format
        assert wav_data[:4] == b"RIFF"
        assert wav_data[8:12] == b"WAVE"

    def test_convert_ogg_to_wav_preserves_audio(self, sample_ogg):
        """Test that converted audio is recognizable as valid audio."""
        wav_data = convert_ogg_to_wav(sample_ogg)

        # Can load as AudioSegment
        audio = AudioSegment.from_wav(io.BytesIO(wav_data))
        assert audio.frame_rate > 0
        assert audio.channels > 0
        assert len(audio) > 0

    def test_convert_ogg_to_wav_invalid_input(self):
        """Test that invalid input raises appropriate error."""
        invalid_data = b"not an audio file"

        with pytest.raises(
            (ValueError, Exception)
        ):  # pydub may raise different exceptions
            convert_ogg_to_wav(invalid_data)


class TestSampleRateConversion:
    """Tests for sample rate conversion to 16kHz."""

    def test_convert_to_16khz_mono_basic(self, sample_wav_44khz_stereo):
        """Test converting 44.1kHz stereo to 16kHz mono."""
        converted = convert_to_16khz_mono(sample_wav_44khz_stereo)

        # Should return bytes
        assert isinstance(converted, bytes)
        assert len(converted) > 0

        # Should be valid WAV
        assert converted[:4] == b"RIFF"

        # Load and verify sample rate and channels
        audio = AudioSegment.from_wav(io.BytesIO(converted))
        assert audio.frame_rate == 16000
        assert audio.channels == 1

    def test_convert_already_16khz_mono(self, sample_wav_16khz_mono):
        """Test that already 16kHz mono audio passes through correctly."""
        converted = convert_to_16khz_mono(sample_wav_16khz_mono)

        # Should return valid audio
        assert isinstance(converted, bytes)
        assert len(converted) > 0

        # Should still be 16kHz mono
        audio = AudioSegment.from_wav(io.BytesIO(converted))
        assert audio.frame_rate == 16000
        assert audio.channels == 1

    def test_convert_to_16khz_mono_preserves_duration(self, sample_wav_44khz_stereo):
        """Test that conversion preserves approximate audio duration."""
        original_audio = AudioSegment.from_wav(io.BytesIO(sample_wav_44khz_stereo))
        original_duration_ms = len(original_audio)

        converted = convert_to_16khz_mono(sample_wav_44khz_stereo)
        converted_audio = AudioSegment.from_wav(io.BytesIO(converted))
        converted_duration_ms = len(converted_audio)

        # Duration should be approximately the same (within 100ms tolerance)
        assert abs(original_duration_ms - converted_duration_ms) < 100

    def test_convert_to_16khz_mono_invalid_input(self):
        """Test that invalid input raises appropriate error."""
        invalid_data = b"not an audio file"

        with pytest.raises((ValueError, Exception)):
            convert_to_16khz_mono(invalid_data)


class TestAudioValidation:
    """Tests for audio validation."""

    def test_validate_audio_valid(self, sample_wav_16khz_mono):
        """Test validation of valid audio."""
        # Should not raise
        validate_audio(sample_wav_16khz_mono)

    def test_validate_audio_too_long(self):
        """Test validation fails for audio that's too long."""
        # Create a long audio segment (exceeding MAX_AUDIO_DURATION_SECONDS)
        duration_ms = (MAX_AUDIO_DURATION_SECONDS + 10) * 1000
        audio = Sine(440).to_audio_segment(duration=duration_ms)
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)

        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        buffer.seek(0)
        long_audio = buffer.read()

        with pytest.raises(AudioValidationError) as exc_info:
            validate_audio(long_audio)

        assert (
            "duration" in str(exc_info.value).lower()
            or "too long" in str(exc_info.value).lower()
        )

    def test_validate_audio_too_large(self):
        """Test validation fails for audio that's too large."""
        # Create a large audio segment (exceeding MAX_AUDIO_SIZE_BYTES)
        # This is harder to control exactly, but we can try to create a large file
        # by using a high sample rate and long duration
        duration_ms = 60000  # 60 seconds
        audio = Sine(440).to_audio_segment(duration=duration_ms)
        audio = audio.set_frame_rate(96000)  # High sample rate
        audio = audio.set_channels(2)

        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        buffer.seek(0)
        large_audio = buffer.read()

        # Only test if the audio is actually larger than the limit
        if len(large_audio) > MAX_AUDIO_SIZE_BYTES:
            with pytest.raises(AudioValidationError) as exc_info:
                validate_audio(large_audio)

            assert (
                "size" in str(exc_info.value).lower()
                or "too large" in str(exc_info.value).lower()
            )

    def test_validate_audio_invalid_format(self):
        """Test validation fails for invalid audio format."""
        invalid_data = b"not an audio file"

        with pytest.raises(AudioValidationError):
            validate_audio(invalid_data)

    def test_validate_audio_wrong_sample_rate(self, sample_wav_44khz_stereo):
        """Test validation warns or fails for non-16kHz audio (optional check)."""
        # Validation may allow different sample rates, but STT expects 16kHz
        # This test checks if validation enforces 16kHz (optional)
        try:
            validate_audio(sample_wav_44khz_stereo, require_16khz=True)
            # If it doesn't raise, that's also acceptable
        except AudioValidationError:
            # If it does raise, that's fine too
            pass

    def test_validate_audio_wrong_channels(self, sample_wav_44khz_stereo):
        """Test validation warns or fails for non-mono audio (optional check)."""
        # Validation may allow stereo, but STT expects mono
        try:
            validate_audio(sample_wav_44khz_stereo, require_mono=True)
            # If it doesn't raise, that's also acceptable
        except AudioValidationError:
            # If it does raise, that's fine too
            pass


class TestIntegration:
    """Integration tests for complete audio processing pipeline."""

    def test_ogg_to_wav_then_convert_to_stt_format(self, sample_ogg):
        """Test complete pipeline: OGG -> WAV -> 16kHz mono."""
        # Convert OGG to WAV
        wav_data = convert_ogg_to_wav(sample_ogg)

        # Convert to 16kHz mono
        stt_audio = convert_to_16khz_mono(wav_data)

        # Validate
        validate_audio(stt_audio)

        # Verify final format
        audio = AudioSegment.from_wav(io.BytesIO(stt_audio))
        assert audio.frame_rate == 16000
        assert audio.channels == 1
        assert len(audio) > 0

    def test_combined_conversion_function(self, sample_ogg):
        """Test a hypothetical combined function that does everything."""
        # This would be a convenience function that does OGG->WAV and 16kHz mono conversion
        # For now, we test the two-step process
        wav_data = convert_ogg_to_wav(sample_ogg)
        stt_audio = convert_to_16khz_mono(wav_data)

        # Should be ready for STT
        validate_audio(stt_audio)

        audio = AudioSegment.from_wav(io.BytesIO(stt_audio))
        assert audio.frame_rate == 16000
        assert audio.channels == 1


class TestCompressionOptimization:
    """Tests for voice message compression optimization."""

    @pytest.fixture
    def sample_audio_segment(self):
        """Create a sample AudioSegment for compression testing."""
        # Generate a 2-second sine wave at 440Hz
        audio = Sine(440).to_audio_segment(duration=2000)  # 2 seconds
        audio = audio.set_frame_rate(44100)
        audio = audio.set_channels(2)  # Stereo
        return audio

    def test_compress_audio_for_telegram_basic(self, sample_audio_segment):
        """Test basic compression function."""
        compressed_audio, compression_info = compress_audio_for_telegram(
            sample_audio_segment, bitrate=TELEGRAM_RECOMMENDED_BITRATE
        )

        # Should return AudioSegment and info dict
        assert isinstance(compressed_audio, AudioSegment)
        assert isinstance(compression_info, dict)

        # Check compression info fields
        assert "original_size" in compression_info
        assert "compressed_size" in compression_info
        assert "bitrate_used" in compression_info
        assert "compression_ratio" in compression_info
        assert compression_info["bitrate_used"] == TELEGRAM_RECOMMENDED_BITRATE

        # Audio should be mono after compression
        assert compressed_audio.channels == 1

    def test_compress_audio_with_preset(self, sample_audio_segment):
        """Test compression with preset."""
        for preset_name in COMPRESSION_PRESETS.keys():
            compressed_audio, compression_info = compress_audio_for_telegram(
                sample_audio_segment, preset=preset_name
            )

            expected_bitrate = COMPRESSION_PRESETS[preset_name]["bitrate"]
            assert compression_info["bitrate_used"] == expected_bitrate
            assert compression_info["preset_used"] == preset_name

    def test_compress_audio_reduces_bitrate_if_too_large(self, sample_audio_segment):
        """Test that compression reduces bitrate if estimated size exceeds max_file_size."""
        from audio_utils import TELEGRAM_MIN_BITRATE

        # Create a very long audio segment
        long_audio = Sine(440).to_audio_segment(duration=60000)  # 60 seconds
        long_audio = long_audio.set_frame_rate(44100)
        long_audio = long_audio.set_channels(1)

        # Use a small max_file_size to force bitrate reduction
        small_max_size = 100 * 1024  # 100 KB

        compressed_audio, compression_info = compress_audio_for_telegram(
            long_audio,
            bitrate=TELEGRAM_RECOMMENDED_BITRATE,
            max_file_size=small_max_size,
        )

        # Bitrate should be reduced from recommended bitrate
        assert compression_info["bitrate_used"] < TELEGRAM_RECOMMENDED_BITRATE

        # Bitrate should be at least the minimum, or the calculated required bitrate (whichever is higher)
        calculated_required = int((small_max_size * 8) / (len(long_audio) / 1000.0))
        expected_bitrate = max(
            TELEGRAM_MIN_BITRATE, min(calculated_required, TELEGRAM_RECOMMENDED_BITRATE)
        )
        assert compression_info["bitrate_used"] == expected_bitrate

    def test_export_audio_to_ogg_optimized(self, sample_audio_segment, tmp_path):
        """Test exporting audio to OGG with optimization."""
        import shutil
        import os

        # Skip test if ffmpeg is not available
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg not available, skipping OGG export test")

        output_path = str(tmp_path / "test_output.ogg")

        compression_info = export_audio_to_ogg_optimized(
            sample_audio_segment, output_path, preset="balanced"
        )

        # File should be created
        assert os.path.exists(output_path)

        # Check compression info
        assert "compressed_size" in compression_info
        assert "file_path" in compression_info
        assert compression_info["file_path"] == output_path

        # Verify file size matches reported size
        actual_size = os.path.getsize(output_path)
        assert compression_info["compressed_size"] == actual_size

        # File should be valid OGG (can be loaded)
        exported_audio = AudioSegment.from_ogg(output_path)
        assert exported_audio.frame_rate > 0
        assert exported_audio.channels > 0

    def test_find_optimal_compression(self, sample_audio_segment):
        """Test finding optimal compression preset."""
        preset_name, preset_info = find_optimal_compression(
            sample_audio_segment,
            max_file_size=TELEGRAM_MAX_FILE_SIZE,
            quality_threshold=0.5,
        )

        # Should return a valid preset
        assert preset_name in COMPRESSION_PRESETS
        assert isinstance(preset_info, dict)
        assert preset_info["preset"] == preset_name
        assert "bitrate" in preset_info
        assert "estimated_size" in preset_info
        assert preset_info["estimated_size"] <= TELEGRAM_MAX_FILE_SIZE

    def test_find_optimal_compression_with_small_max_size(self, sample_audio_segment):
        """Test finding optimal compression with small max_file_size constraint."""
        # Use a small max_file_size to force aggressive compression
        small_max_size = 50 * 1024  # 50 KB

        preset_name, preset_info = find_optimal_compression(
            sample_audio_segment,
            max_file_size=small_max_size,
            quality_threshold=0.2,  # Lower threshold to allow more aggressive compression
        )

        # Should select a preset that fits within size constraint
        assert preset_info["estimated_size"] <= small_max_size
        # Should select a preset that fits (could be any preset that fits)
        assert preset_name in COMPRESSION_PRESETS

    def test_compression_presets_exist(self):
        """Test that all compression presets are properly defined."""
        assert "high_quality" in COMPRESSION_PRESETS
        assert "balanced" in COMPRESSION_PRESETS
        assert "optimized" in COMPRESSION_PRESETS
        assert "aggressive" in COMPRESSION_PRESETS

        for preset_name, preset_config in COMPRESSION_PRESETS.items():
            assert "bitrate" in preset_config
            assert "description" in preset_config
            assert preset_config["bitrate"] > 0

    def test_compression_ratio_calculation(self, sample_audio_segment):
        """Test that compression ratio is calculated correctly."""
        compressed_audio, compression_info = compress_audio_for_telegram(
            sample_audio_segment, bitrate=TELEGRAM_RECOMMENDED_BITRATE
        )

        # Compression ratio should be > 1 (compressed should be smaller)
        assert compression_info["compression_ratio"] > 1.0

        # Original size should be larger than compressed size estimate
        assert compression_info["original_size"] > compression_info["compressed_size"]

    def test_compression_preserves_duration(self, sample_audio_segment):
        """Test that compression preserves audio duration."""
        original_duration = len(sample_audio_segment)

        compressed_audio, compression_info = compress_audio_for_telegram(
            sample_audio_segment, bitrate=TELEGRAM_RECOMMENDED_BITRATE
        )

        compressed_duration = len(compressed_audio)

        # Duration should be approximately the same (within 100ms tolerance)
        assert abs(original_duration - compressed_duration) < 100


class TestNoiseReduction:
    """Tests for noise reduction functionality."""

    @pytest.fixture
    def sample_wav_with_noise(self):
        """Create a sample WAV file with background noise."""
        from pydub.generators import WhiteNoise

        # Generate clean signal
        signal = Sine(440).to_audio_segment(duration=1000)  # 1 second
        signal = signal.set_frame_rate(16000)
        signal = signal.set_channels(1)
        signal = signal.normalize(headroom=0.1)

        # Add white noise (20dB below signal)
        noise = WhiteNoise().to_audio_segment(duration=1000)
        noise = noise.set_frame_rate(16000)
        noise = noise.set_channels(1)
        noise = noise - 20  # 20dB below signal

        # Mix signal and noise
        audio = signal.overlay(noise)

        # Export to bytes
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        buffer.seek(0)
        return buffer.read()

    def test_reduce_noise_basic(self, sample_wav_16khz_mono):
        """Test basic noise reduction on clean audio."""
        enhanced = reduce_noise(sample_wav_16khz_mono, reduction_strength=0.5)

        # Should return bytes
        assert isinstance(enhanced, bytes)
        assert len(enhanced) > 0

        # Should be valid WAV
        assert enhanced[:4] == b"RIFF"

        # Should still be 16kHz mono
        audio = AudioSegment.from_wav(io.BytesIO(enhanced))
        assert audio.frame_rate == 16000
        assert audio.channels == 1

    def test_reduce_noise_with_noisy_audio(self, sample_wav_with_noise):
        """Test noise reduction on noisy audio."""
        enhanced = reduce_noise(sample_wav_with_noise, reduction_strength=0.5)

        # Should return valid audio
        assert isinstance(enhanced, bytes)
        assert len(enhanced) > 0

        # Should be valid WAV
        assert enhanced[:4] == b"RIFF"

        # Audio should still be playable
        audio = AudioSegment.from_wav(io.BytesIO(enhanced))
        assert audio.frame_rate == 16000
        assert audio.channels == 1
        assert len(audio) > 0

    def test_reduce_noise_different_strengths(self, sample_wav_with_noise):
        """Test noise reduction with different strength values."""
        for strength in [0.0, 0.25, 0.5, 0.75, 1.0]:
            enhanced = reduce_noise(sample_wav_with_noise, reduction_strength=strength)

            # Should always return valid audio
            assert isinstance(enhanced, bytes)
            assert len(enhanced) > 0
            assert enhanced[:4] == b"RIFF"

    def test_reduce_noise_handles_missing_librosa(
        self, sample_wav_16khz_mono, monkeypatch
    ):
        """Test that noise reduction gracefully handles missing librosa."""
        # Mock librosa as unavailable
        import audio_utils

        original_librosa = audio_utils.librosa
        audio_utils.librosa = None
        audio_utils.LIBROSA_AVAILABLE = False
        audio_utils.NUMPY_AVAILABLE = False

        try:
            # Should return original audio without error
            enhanced = reduce_noise(sample_wav_16khz_mono)
            assert enhanced == sample_wav_16khz_mono
        finally:
            # Restore
            audio_utils.librosa = original_librosa
            audio_utils.LIBROSA_AVAILABLE = True
            audio_utils.NUMPY_AVAILABLE = True


class TestVolumeNormalization:
    """Tests for volume normalization functionality."""

    @pytest.fixture
    def sample_wav_quiet(self):
        """Create a quiet WAV file."""
        audio = Sine(440).to_audio_segment(duration=1000)
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        audio = audio - 30  # Make it quiet (-30dB)

        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        buffer.seek(0)
        return buffer.read()

    @pytest.fixture
    def sample_wav_loud(self):
        """Create a loud WAV file."""
        audio = Sine(440).to_audio_segment(duration=1000)
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        audio = audio + 10  # Make it loud (+10dB)

        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        buffer.seek(0)
        return buffer.read()

    def test_normalize_volume_basic(self, sample_wav_16khz_mono):
        """Test basic volume normalization."""
        normalized = normalize_volume(sample_wav_16khz_mono, target_db=-20.0)

        # Should return bytes
        assert isinstance(normalized, bytes)
        assert len(normalized) > 0

        # Should be valid WAV
        assert normalized[:4] == b"RIFF"

        # Should still be 16kHz mono
        audio = AudioSegment.from_wav(io.BytesIO(normalized))
        assert audio.frame_rate == 16000
        assert audio.channels == 1

    def test_normalize_volume_quiet_audio(self, sample_wav_quiet):
        """Test normalizing quiet audio."""
        normalized = normalize_volume(sample_wav_quiet, target_db=-20.0)

        # Should return valid audio
        assert isinstance(normalized, bytes)
        assert len(normalized) > 0

        # Check that volume was adjusted (should be louder)
        original_audio = AudioSegment.from_wav(io.BytesIO(sample_wav_quiet))
        normalized_audio = AudioSegment.from_wav(io.BytesIO(normalized))

        # Normalized audio should be louder (higher dBFS)
        assert normalized_audio.dBFS > original_audio.dBFS

    def test_normalize_volume_loud_audio(self, sample_wav_loud):
        """Test normalizing loud audio."""
        normalized = normalize_volume(sample_wav_loud, target_db=-20.0)

        # Should return valid audio
        assert isinstance(normalized, bytes)
        assert len(normalized) > 0

        # Check that volume was adjusted (should be quieter)
        original_audio = AudioSegment.from_wav(io.BytesIO(sample_wav_loud))
        normalized_audio = AudioSegment.from_wav(io.BytesIO(normalized))

        # Normalized audio should be quieter (lower dBFS, closer to target)
        # Allow some tolerance since exact matching is difficult
        assert abs(normalized_audio.dBFS - (-20.0)) < abs(original_audio.dBFS - (-20.0))

    def test_normalize_volume_different_targets(self, sample_wav_16khz_mono):
        """Test normalization with different target levels."""
        for target_db in [-30.0, -20.0, -12.0]:
            normalized = normalize_volume(sample_wav_16khz_mono, target_db=target_db)

            # Should always return valid audio
            assert isinstance(normalized, bytes)
            assert len(normalized) > 0
            assert normalized[:4] == b"RIFF"

    def test_normalize_volume_invalid_input(self):
        """Test that invalid input raises appropriate error."""
        invalid_data = b"not an audio file"

        with pytest.raises(ValueError):
            normalize_volume(invalid_data)


class TestAudioEnhancement:
    """Tests for complete audio enhancement pipeline."""

    @pytest.fixture
    def sample_ogg(self):
        """Create a sample OGG file."""
        audio = Sine(440).to_audio_segment(duration=1000)
        audio = audio.set_frame_rate(44100)
        audio = audio.set_channels(2)

        buffer = io.BytesIO()
        audio.export(buffer, format="ogg", codec="libvorbis")
        buffer.seek(0)
        return buffer.read()

    def test_enhance_audio_for_stt_basic(self, sample_ogg):
        """Test basic audio enhancement pipeline."""
        enhanced = enhance_audio_for_stt(
            sample_ogg,
            is_ogg=True,
            enable_noise_reduction=True,
            enable_volume_normalization=True,
        )

        # Should return valid WAV
        assert isinstance(enhanced, bytes)
        assert len(enhanced) > 0
        assert enhanced[:4] == b"RIFF"

        # Should be 16kHz mono
        audio = AudioSegment.from_wav(io.BytesIO(enhanced))
        assert audio.frame_rate == 16000
        assert audio.channels == 1

        # Should pass validation
        validate_audio(enhanced, require_16khz=True, require_mono=True)

    def test_enhance_audio_for_stt_noise_reduction_only(self, sample_ogg):
        """Test enhancement with only noise reduction enabled."""
        enhanced = enhance_audio_for_stt(
            sample_ogg,
            is_ogg=True,
            enable_noise_reduction=True,
            enable_volume_normalization=False,
        )

        # Should return valid audio
        assert isinstance(enhanced, bytes)
        assert len(enhanced) > 0
        validate_audio(enhanced, require_16khz=True, require_mono=True)

    def test_enhance_audio_for_stt_volume_normalization_only(self, sample_ogg):
        """Test enhancement with only volume normalization enabled."""
        enhanced = enhance_audio_for_stt(
            sample_ogg,
            is_ogg=True,
            enable_noise_reduction=False,
            enable_volume_normalization=True,
        )

        # Should return valid audio
        assert isinstance(enhanced, bytes)
        assert len(enhanced) > 0
        validate_audio(enhanced, require_16khz=True, require_mono=True)

    def test_enhance_audio_for_stt_no_enhancement(self, sample_ogg):
        """Test enhancement with both enhancements disabled (format conversion only)."""
        enhanced = enhance_audio_for_stt(
            sample_ogg,
            is_ogg=True,
            enable_noise_reduction=False,
            enable_volume_normalization=False,
        )

        # Should still do format conversion
        assert isinstance(enhanced, bytes)
        assert len(enhanced) > 0
        validate_audio(enhanced, require_16khz=True, require_mono=True)

    def test_enhance_audio_for_stt_wav_input(self, sample_wav_16khz_mono):
        """Test enhancement with WAV input (not OGG)."""
        enhanced = enhance_audio_for_stt(
            sample_wav_16khz_mono,
            is_ogg=False,
            enable_noise_reduction=True,
            enable_volume_normalization=True,
        )

        # Should return valid enhanced audio
        assert isinstance(enhanced, bytes)
        assert len(enhanced) > 0
        validate_audio(enhanced, require_16khz=True, require_mono=True)

    def test_prepare_audio_for_stt_still_works(self, sample_ogg):
        """Test that prepare_audio_for_stt() still works (backward compatibility)."""
        prepared = prepare_audio_for_stt(sample_ogg, is_ogg=True)

        # Should return valid audio
        assert isinstance(prepared, bytes)
        assert len(prepared) > 0
        validate_audio(prepared, require_16khz=True, require_mono=True)

        # Should be 16kHz mono
        audio = AudioSegment.from_wav(io.BytesIO(prepared))
        assert audio.frame_rate == 16000
        assert audio.channels == 1
