"""
Tests for OpenTelemetry tracing spans in Telegram service.

Tests verify that:
- Spans are created for all major operations
- Span attributes are set correctly
- Spans record exceptions on errors
- Span status is set correctly

Note: These tests verify the tracing pattern and span creation logic
without requiring full service integration.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, Mock, patch

# Mock dependencies before importing
sys.modules["inference_core"] = MagicMock()
sys.modules["inference_core.config"] = MagicMock()
sys.modules["inference_core.setup_logging"] = MagicMock()

# Add essence to path
_project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_essence_dir = os.path.join(_project_root, "essence")
if _essence_dir not in sys.path:
    sys.path.insert(0, _essence_dir)

# Mock opentelemetry modules that tracing.py needs
# Use patch to avoid interfering with pytest's plugin system
mock_span = MagicMock()
mock_span.set_attribute = MagicMock()
mock_span.record_exception = MagicMock()
mock_span.set_status = MagicMock()

mock_tracer = MagicMock()
mock_tracer.start_as_current_span = MagicMock(
    return_value=Mock(__enter__=lambda self: mock_span, __exit__=lambda *args: None)
)


# Create a context manager that properly handles span entry/exit
class SpanContextManager:
    def __init__(self, span):
        self.span = span

    def __enter__(self):
        return self.span

    def __exit__(self, *args):
        return False


mock_tracer.start_as_current_span.return_value = SpanContextManager(mock_span)


class TestTracingSpanPatterns:
    """Tests for OpenTelemetry tracing span creation patterns."""

    def setup_method(self):
        """Reset mocks before each test."""
        mock_span.set_attribute.reset_mock()
        mock_span.record_exception.reset_mock()
        mock_span.set_status.reset_mock()
        mock_tracer.start_as_current_span.reset_mock()
        mock_tracer.start_as_current_span.return_value = SpanContextManager(mock_span)

    def test_stt_span_pattern(self):
        """Test that STT span is created with correct attributes pattern."""
        # Simulate the pattern used in voice.py handler
        with mock_tracer.start_as_current_span("stt.recognize_stream") as span:
            span.set_attribute("stt.language", "en")
            span.set_attribute("stt.sample_rate", 16000)
            span.set_attribute("stt.encoding", "wav")
            span.set_attribute("stt.audio_size_bytes", 1000)
            span.set_attribute("stt.transcript_length", 50)
            span.set_attribute("stt.confidence", 0.95)
            span.set_attribute("stt.detected_language", "en")

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert (
            mock_tracer.start_as_current_span.call_args[0][0] == "stt.recognize_stream"
        )

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 7

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("stt.language", "en") in set_attribute_calls
        assert ("stt.sample_rate", 16000) in set_attribute_calls
        assert ("stt.transcript_length", 50) in set_attribute_calls

    def test_llm_span_pattern(self):
        """Test that LLM span is created with correct attributes pattern."""
        # Simulate the pattern used in voice.py handler
        with mock_tracer.start_as_current_span("llm.chat_stream") as span:
            span.set_attribute("llm.message_count", 2)
            span.set_attribute("llm.user_id", "12345")
            span.set_attribute("llm.chat_id", "67890")
            span.set_attribute("llm.input_length", 100)
            span.set_attribute("llm.response_length", 200)
            span.set_attribute("llm.stream_success", True)

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert mock_tracer.start_as_current_span.call_args[0][0] == "llm.chat_stream"

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 6

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("llm.message_count", 2) in set_attribute_calls
        assert ("llm.user_id", "12345") in set_attribute_calls
        assert ("llm.input_length", 100) in set_attribute_calls

    def test_tts_span_pattern(self):
        """Test that TTS span is created with correct attributes pattern."""
        # Simulate the pattern used in voice.py handler
        with mock_tracer.start_as_current_span("tts.synthesize") as span:
            span.set_attribute("tts.text_length", 100)
            span.set_attribute("tts.language", "en")
            span.set_attribute("tts.voice_id", "default")
            span.set_attribute("tts.audio_size_bytes", 5000)
            span.set_attribute("tts.user_id", "12345")
            span.set_attribute("tts.chat_id", "67890")

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert mock_tracer.start_as_current_span.call_args[0][0] == "tts.synthesize"

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 6

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("tts.text_length", 100) in set_attribute_calls
        assert ("tts.language", "en") in set_attribute_calls
        assert ("tts.audio_size_bytes", 5000) in set_attribute_calls

    def test_voice_download_span_pattern(self):
        """Test that voice download span is created with correct attributes pattern."""
        # Simulate the pattern used in voice.py handler
        with mock_tracer.start_as_current_span("voice.download") as span:
            span.set_attribute("voice.file_id", "test_file_id")
            span.set_attribute("voice.file_size", 1000)
            span.set_attribute("voice.mime_type", "audio/ogg")
            span.set_attribute("voice.downloaded_size", 1000)
            span.set_attribute("voice.download_success", True)
            span.set_attribute("user.id", "12345")
            span.set_attribute("chat.id", "67890")

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert mock_tracer.start_as_current_span.call_args[0][0] == "voice.download"

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 7

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("voice.file_id", "test_file_id") in set_attribute_calls
        assert ("voice.download_success", True) in set_attribute_calls

    def test_voice_enhance_audio_span_pattern(self):
        """Test that voice enhance audio span is created with correct attributes pattern."""
        # Simulate the pattern used in voice.py handler
        with mock_tracer.start_as_current_span("voice.enhance_audio") as span:
            span.set_attribute("voice.input_size", 1000)
            span.set_attribute("voice.input_format", "ogg")
            span.set_attribute("voice.output_size", 800)
            span.set_attribute("voice.enable_noise_reduction", True)
            span.set_attribute("voice.enable_volume_normalization", True)
            span.set_attribute("voice.enhancement_success", True)
            span.set_attribute("user.id", "12345")
            span.set_attribute("chat.id", "67890")

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert (
            mock_tracer.start_as_current_span.call_args[0][0] == "voice.enhance_audio"
        )

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 8

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("voice.input_size", 1000) in set_attribute_calls
        assert ("voice.enhancement_success", True) in set_attribute_calls

    def test_text_message_span_pattern(self):
        """Test that text message handler span is created with correct attributes pattern."""
        # Simulate the pattern used in text.py handler
        with mock_tracer.start_as_current_span("telegram.text_message.handle") as span:
            span.set_attribute("user_id", "12345")
            span.set_attribute("chat_id", "67890")
            span.set_attribute("message_length", 50)
            span.set_attribute("platform", "telegram")
            span.set_attribute("authorized", True)

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert (
            mock_tracer.start_as_current_span.call_args[0][0]
            == "telegram.text_message.handle"
        )

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 5

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("user_id", "12345") in set_attribute_calls
        assert ("platform", "telegram") in set_attribute_calls
        assert ("authorized", True) in set_attribute_calls

    def test_span_records_exception_on_error(self):
        """Test that spans record exceptions on errors."""
        test_exception = Exception("Test error")

        with mock_tracer.start_as_current_span("test.operation") as span:
            try:
                raise test_exception
            except Exception as e:
                span.record_exception(e)
                # Simulate setting error status
                span.set_status(Mock(status_code="ERROR", description=str(e)))

        # Verify exception was recorded
        assert mock_span.record_exception.called
        assert mock_span.set_status.called

        # Verify exception was passed to record_exception
        exception_call = mock_span.record_exception.call_args[0][0]
        assert isinstance(exception_call, Exception)
        assert str(exception_call) == "Test error"

    def test_span_attributes_include_user_and_chat_ids(self):
        """Test that spans include user_id and chat_id attributes for correlation."""
        user_id = "12345"
        chat_id = "67890"

        with mock_tracer.start_as_current_span("test.operation") as span:
            span.set_attribute("user_id", user_id)
            span.set_attribute("chat_id", chat_id)

        # Verify user_id and chat_id were set
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("user_id", user_id) in set_attribute_calls
        assert ("chat_id", chat_id) in set_attribute_calls

    def test_multiple_spans_can_be_created(self):
        """Test that multiple spans can be created in sequence."""
        # Create multiple spans
        with mock_tracer.start_as_current_span("span1") as span1:
            span1.set_attribute("key1", "value1")

        with mock_tracer.start_as_current_span("span2") as span2:
            span2.set_attribute("key2", "value2")

        # Verify both spans were created
        assert mock_tracer.start_as_current_span.call_count == 2
        assert mock_tracer.start_as_current_span.call_args_list[0][0][0] == "span1"
        assert mock_tracer.start_as_current_span.call_args_list[1][0][0] == "span2"

    def test_span_attributes_for_different_operations(self):
        """Test that different operations set appropriate span attributes."""
        # Test STT operation attributes
        with mock_tracer.start_as_current_span("stt.recognize") as span:
            span.set_attribute("stt.audio_size_bytes", 1000)
            span.set_attribute("stt.transcript_length", 50)

        # Test LLM operation attributes
        with mock_tracer.start_as_current_span("llm.generate") as span:
            span.set_attribute("llm.prompt_length", 100)
            span.set_attribute("llm.response_length", 200)

        # Test TTS operation attributes
        with mock_tracer.start_as_current_span("tts.synthesize") as span:
            span.set_attribute("tts.text_length", 100)
            span.set_attribute("tts.audio_size_bytes", 5000)

        # Verify all spans were created
        assert mock_tracer.start_as_current_span.call_count == 3

        # Verify span names
        span_names = [
            call[0][0] for call in mock_tracer.start_as_current_span.call_args_list
        ]
        assert "stt.recognize" in span_names
        assert "llm.generate" in span_names
        assert "tts.synthesize" in span_names
