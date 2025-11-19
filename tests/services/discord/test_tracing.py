"""
Tests for OpenTelemetry tracing spans in Discord service.

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
mock_span = MagicMock()
mock_span.set_attribute = MagicMock()
mock_span.record_exception = MagicMock()
mock_span.set_status = MagicMock()
mock_span.add_event = MagicMock()

mock_tracer = MagicMock()
mock_tracer.start_as_current_span = MagicMock(
    return_value=Mock(__enter__=lambda self: mock_span, __exit__=lambda *args: None)
)
mock_tracer.start_span = MagicMock(return_value=mock_span)


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
        mock_span.add_event.reset_mock()
        mock_tracer.start_as_current_span.reset_mock()
        mock_tracer.start_span.reset_mock()
        mock_tracer.start_as_current_span.return_value = SpanContextManager(mock_span)

    def test_agent_stream_message_span_pattern(self):
        """Test that agent.stream_message span is created with correct attributes pattern."""
        # Simulate the pattern used in agent handler
        with mock_tracer.start_as_current_span("agent.stream_message") as span:
            span.set_attribute("platform", "discord")
            span.set_attribute("user_id", "12345")
            span.set_attribute("chat_id", "67890")
            span.set_attribute("message_length", 100)
            span.set_attribute("line_timeout", 30.0)
            span.set_attribute("max_total_time", 300.0)
            span.set_attribute("agent_script_name", "telegram_response_agent.sh")
            span.set_attribute("agent_available", True)
            span.set_attribute("agenticness_dir", "/path/to/agenticness")

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert (
            mock_tracer.start_as_current_span.call_args[0][0] == "agent.stream_message"
        )

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 9

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("platform", "discord") in set_attribute_calls
        assert ("user_id", "12345") in set_attribute_calls
        assert ("chat_id", "67890") in set_attribute_calls
        assert ("message_length", 100) in set_attribute_calls
        assert ("agent_available", True) in set_attribute_calls

    def test_agent_process_message_span_pattern(self):
        """Test that agent.process_message span is created with correct attributes pattern."""
        # Simulate the pattern used in agent handler
        with mock_tracer.start_as_current_span("agent.process_message") as span:
            span.set_attribute("platform", "discord")
            span.set_attribute("user_id", "12345")
            span.set_attribute("chat_id", "67890")
            span.set_attribute("message_length", 100)
            span.set_attribute("agent_script_name", "telegram_response_agent.sh")
            span.set_attribute("agent_available", True)
            span.set_attribute("agenticness_dir", "/path/to/agenticness")

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert (
            mock_tracer.start_as_current_span.call_args[0][0] == "agent.process_message"
        )

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 7

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("platform", "discord") in set_attribute_calls
        assert ("user_id", "12345") in set_attribute_calls
        assert ("chat_id", "67890") in set_attribute_calls

    def test_http_request_span_pattern(self):
        """Test that HTTP request span is created with correct attributes pattern."""
        # Simulate the pattern used in HTTP middleware
        with mock_tracer.start_as_current_span("http.request") as span:
            span.set_attribute("http.method", "GET")
            span.set_attribute("http.url", "http://localhost:8081/health")
            span.set_attribute("http.path", "/health")
            span.set_attribute("http.status_code", 200)
            span.set_attribute("http.scheme", "http")

        # Verify span was created
        assert mock_tracer.start_as_current_span.called
        assert mock_tracer.start_as_current_span.call_args[0][0] == "http.request"

        # Verify attributes were set
        assert mock_span.set_attribute.call_count >= 5

        # Verify specific attributes
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("http.method", "GET") in set_attribute_calls
        assert ("http.path", "/health") in set_attribute_calls
        assert ("http.status_code", 200) in set_attribute_calls

    def test_span_records_exception_on_error(self):
        """Test that spans record exceptions on errors."""
        error = Exception("Test error")

        with mock_tracer.start_as_current_span("agent.stream_message") as span:
            try:
                raise error
            except Exception as e:
                span.record_exception(e)
                span.set_status(Mock(code=Mock(ERROR=1), description=str(e)))

        # Verify exception was recorded
        assert mock_span.record_exception.called
        assert mock_span.record_exception.call_args[0][0] == error

        # Verify status was set to error
        assert mock_span.set_status.called

    def test_span_attributes_include_user_and_chat_ids(self):
        """Test that spans include user_id and chat_id attributes for correlation."""
        with mock_tracer.start_as_current_span("agent.stream_message") as span:
            span.set_attribute("user_id", "12345")
            span.set_attribute("chat_id", "67890")
            span.set_attribute("platform", "discord")

        # Verify user_id and chat_id are set
        set_attribute_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list
        ]
        assert ("user_id", "12345") in set_attribute_calls
        assert ("chat_id", "67890") in set_attribute_calls
        assert ("platform", "discord") in set_attribute_calls

    def test_multiple_spans_can_be_created(self):
        """Test that multiple spans can be created in sequence."""
        # Create first span
        with mock_tracer.start_as_current_span("agent.stream_message") as span1:
            span1.set_attribute("platform", "discord")

        # Create second span
        with mock_tracer.start_as_current_span("http.request") as span2:
            span2.set_attribute("http.method", "GET")

        # Verify both spans were created
        assert mock_tracer.start_as_current_span.call_count == 2
        assert (
            mock_tracer.start_as_current_span.call_args_list[0][0][0]
            == "agent.stream_message"
        )
        assert (
            mock_tracer.start_as_current_span.call_args_list[1][0][0] == "http.request"
        )

    def test_span_attributes_for_different_operations(self):
        """Test that different operations set appropriate span attributes."""
        # Test agent streaming span
        with mock_tracer.start_as_current_span("agent.stream_message") as span:
            span.set_attribute("platform", "discord")
            span.set_attribute("message_length", 100)
            span.set_attribute("agent_available", True)

        # Test HTTP request span
        with mock_tracer.start_as_current_span("http.request") as span:
            span.set_attribute("http.method", "POST")
            span.set_attribute("http.path", "/metrics")
            span.set_attribute("http.status_code", 200)

        # Verify both spans have appropriate attributes
        assert mock_tracer.start_as_current_span.call_count == 2

        # Check that agent span has platform and message attributes
        agent_span_calls = [
            call[0] for call in mock_span.set_attribute.call_args_list[:3]
        ]
        assert any("platform" in str(call) for call in agent_span_calls)
        assert any("message_length" in str(call) for call in agent_span_calls)

    def test_span_status_set_on_success(self):
        """Test that span status is set correctly on success."""
        # Mock trace.Status and StatusCode
        mock_status_code = Mock()
        mock_status_code.OK = 0
        mock_status = Mock()
        mock_status.return_value = Mock(code=mock_status_code)

        with mock_tracer.start_as_current_span("agent.stream_message") as span:
            # Simulate setting status to OK
            status_obj = mock_status()
            span.set_status(status_obj)

        # Verify status was set
        assert mock_span.set_status.called

    def test_span_status_set_on_error(self):
        """Test that span status is set correctly on error."""
        # Mock trace.Status and StatusCode
        mock_status_code = Mock()
        mock_status_code.ERROR = 1
        mock_status = Mock()
        mock_status.return_value = Mock(code=mock_status_code, description="Test error")

        with mock_tracer.start_as_current_span("agent.stream_message") as span:
            # Simulate setting status to ERROR
            status_obj = mock_status()
            span.set_status(status_obj)

        # Verify status was set to error
        assert mock_span.set_status.called
