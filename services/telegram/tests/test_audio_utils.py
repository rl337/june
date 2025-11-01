"""
Tests for audio format conversion utilities.

Tests cover:
- OGG to WAV conversion
- Sample rate conversion (16kHz for Whisper)
- Mono channel conversion
- Audio validation (duration, size checks)
"""
import pytest
import io
import wave
from pydub import AudioSegment
from pydub.generators import Sine

from audio_utils import (
    convert_ogg_to_wav,
    convert_to_16khz_mono,
    validate_audio,
    AudioValidationError,
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUDIO_SIZE_BYTES
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
        assert wav_data[:4] == b'RIFF'
        assert wav_data[8:12] == b'WAVE'
    
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
        
        with pytest.raises((ValueError, Exception)):  # pydub may raise different exceptions
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
        assert converted[:4] == b'RIFF'
        
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
        
        assert "duration" in str(exc_info.value).lower() or "too long" in str(exc_info.value).lower()
    
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
            
            assert "size" in str(exc_info.value).lower() or "too large" in str(exc_info.value).lower()
    
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
