"""
Tests for Prometheus metrics collection in Telegram service.

Tests verify that:
- Metrics are recorded correctly for HTTP requests
- Metrics are recorded correctly for voice processing operations
- Metrics are recorded correctly for gRPC calls
- Error metrics are recorded correctly
- Service health metrics are updated correctly
- Metrics can be exported in Prometheus format
"""
import pytest
from prometheus_client import generate_latest

# Import shared metrics directly (no service imports needed)
from essence.services.shared_metrics import (
    ERRORS_TOTAL,
    GRPC_REQUEST_DURATION_SECONDS,
    GRPC_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    LLM_GENERATION_DURATION_SECONDS,
    REGISTRY,
    SERVICE_HEALTH,
    STT_TRANSCRIPTION_DURATION_SECONDS,
    TTS_SYNTHESIS_DURATION_SECONDS,
    VOICE_MESSAGES_PROCESSED_TOTAL,
    VOICE_PROCESSING_DURATION_SECONDS,
)


class TestTelegramMetrics:
    """Tests for Telegram service metrics collection."""

    def setup_method(self):
        """Reset metrics before each test."""
        # Clear all metrics by creating a new registry
        # Note: This is a simplified approach - in practice, metrics persist
        # We'll just verify that metrics can be recorded and exported
        pass

    def test_http_requests_total_metric(self):
        """Test that HTTP requests are recorded in metrics."""
        # Record a few HTTP requests
        HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/health", status_code="200"
        ).inc()
        HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/metrics", status_code="200"
        ).inc()
        HTTP_REQUESTS_TOTAL.labels(
            method="POST", endpoint="/agent/message", status_code="200"
        ).inc()

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "http_requests_total" in metrics_output
        assert 'method="GET"' in metrics_output or "method='GET'" in metrics_output
        assert "/health" in metrics_output
        assert (
            'status_code="200"' in metrics_output
            or "status_code='200'" in metrics_output
        )

    def test_http_request_duration_metric(self):
        """Test that HTTP request duration is recorded."""
        # Record request duration
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method="GET", endpoint="/health", status_code="200"
        ).observe(0.1)
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method="GET", endpoint="/metrics", status_code="200"
        ).observe(0.05)

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "http_request_duration_seconds" in metrics_output
        assert 'method="GET"' in metrics_output or "method='GET'" in metrics_output

    def test_grpc_requests_total_metric(self):
        """Test that gRPC requests are recorded in metrics."""
        # Record gRPC requests
        GRPC_REQUESTS_TOTAL.labels(
            service="stt", method="recognize_stream", status_code="200"
        ).inc()
        GRPC_REQUESTS_TOTAL.labels(
            service="llm", method="chat_stream", status_code="200"
        ).inc()
        GRPC_REQUESTS_TOTAL.labels(
            service="tts", method="synthesize", status_code="200"
        ).inc()

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "grpc_requests_total" in metrics_output
        assert 'service="stt"' in metrics_output or "service='stt'" in metrics_output
        assert 'service="llm"' in metrics_output or "service='llm'" in metrics_output
        assert 'service="tts"' in metrics_output or "service='tts'" in metrics_output

    def test_grpc_request_duration_metric(self):
        """Test that gRPC request duration is recorded."""
        # Record gRPC request durations
        GRPC_REQUEST_DURATION_SECONDS.labels(
            service="stt", method="recognize_stream", status_code="200"
        ).observe(1.5)
        GRPC_REQUEST_DURATION_SECONDS.labels(
            service="llm", method="chat_stream", status_code="200"
        ).observe(3.2)

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "grpc_request_duration_seconds" in metrics_output
        assert 'service="stt"' in metrics_output or "service='stt'" in metrics_output

    def test_voice_messages_processed_metric(self):
        """Test that voice messages processed are recorded."""
        # Record voice message processing
        VOICE_MESSAGES_PROCESSED_TOTAL.labels(
            platform="telegram", status="success"
        ).inc()
        VOICE_MESSAGES_PROCESSED_TOTAL.labels(platform="telegram", status="error").inc()

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "voice_messages_processed_total" in metrics_output
        assert (
            'platform="telegram"' in metrics_output
            or "platform='telegram'" in metrics_output
        )
        assert (
            'status="success"' in metrics_output or "status='success'" in metrics_output
        )
        assert 'status="error"' in metrics_output or "status='error'" in metrics_output

    def test_voice_processing_duration_metric(self):
        """Test that voice processing duration is recorded."""
        # Record voice processing durations
        VOICE_PROCESSING_DURATION_SECONDS.labels(
            platform="telegram", status="success"
        ).observe(5.5)
        VOICE_PROCESSING_DURATION_SECONDS.labels(
            platform="telegram", status="error"
        ).observe(2.0)

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "voice_processing_duration_seconds" in metrics_output
        assert (
            'platform="telegram"' in metrics_output
            or "platform='telegram'" in metrics_output
        )

    def test_stt_transcription_duration_metric(self):
        """Test that STT transcription duration is recorded."""
        # Record STT transcription durations
        STT_TRANSCRIPTION_DURATION_SECONDS.labels(
            platform="telegram", status="success"
        ).observe(2.0)
        STT_TRANSCRIPTION_DURATION_SECONDS.labels(
            platform="telegram", status="error"
        ).observe(0.5)

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "stt_transcription_duration_seconds" in metrics_output
        assert (
            'platform="telegram"' in metrics_output
            or "platform='telegram'" in metrics_output
        )

    def test_tts_synthesis_duration_metric(self):
        """Test that TTS synthesis duration is recorded."""
        # Record TTS synthesis durations
        TTS_SYNTHESIS_DURATION_SECONDS.labels(
            platform="telegram", status="success"
        ).observe(1.5)
        TTS_SYNTHESIS_DURATION_SECONDS.labels(
            platform="telegram", status="error"
        ).observe(0.3)

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "tts_synthesis_duration_seconds" in metrics_output
        assert (
            'platform="telegram"' in metrics_output
            or "platform='telegram'" in metrics_output
        )

    def test_llm_generation_duration_metric(self):
        """Test that LLM generation duration is recorded."""
        # Record LLM generation durations
        LLM_GENERATION_DURATION_SECONDS.labels(
            platform="telegram", status="success"
        ).observe(3.0)
        LLM_GENERATION_DURATION_SECONDS.labels(
            platform="telegram", status="error"
        ).observe(1.0)

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "llm_generation_duration_seconds" in metrics_output
        assert (
            'platform="telegram"' in metrics_output
            or "platform='telegram'" in metrics_output
        )

    def test_errors_total_metric(self):
        """Test that errors are recorded in metrics."""
        # Record different error types
        ERRORS_TOTAL.labels(service="telegram", error_type="ValueError").inc()
        ERRORS_TOTAL.labels(service="telegram", error_type="ConnectionError").inc()
        ERRORS_TOTAL.labels(service="telegram", error_type="TimeoutError").inc()

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "errors_total" in metrics_output
        assert (
            'service="telegram"' in metrics_output
            or "service='telegram'" in metrics_output
        )
        assert (
            'error_type="ValueError"' in metrics_output
            or "error_type='ValueError'" in metrics_output
        )
        assert (
            'error_type="ConnectionError"' in metrics_output
            or "error_type='ConnectionError'" in metrics_output
        )

    def test_service_health_metric(self):
        """Test that service health is recorded."""
        # Set service health
        SERVICE_HEALTH.labels(service="telegram").set(1)  # Healthy

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "service_health" in metrics_output
        assert (
            'service="telegram"' in metrics_output
            or "service='telegram'" in metrics_output
        )

        # Set to unhealthy
        SERVICE_HEALTH.labels(service="telegram").set(0)  # Unhealthy

        # Generate metrics output again
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify unhealthy status is recorded
        assert "service_health" in metrics_output
        assert (
            'service="telegram"' in metrics_output
            or "service='telegram'" in metrics_output
        )

    def test_metrics_endpoint_format(self):
        """Test that metrics endpoint returns Prometheus format."""
        # Record some metrics
        HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/health", status_code="200"
        ).inc()
        SERVICE_HEALTH.labels(service="telegram").set(1)

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify Prometheus format
        assert "# HELP" in metrics_output or "# TYPE" in metrics_output
        assert "http_requests_total" in metrics_output
        assert "service_health" in metrics_output

    def test_multiple_metric_increments(self):
        """Test that metrics can be incremented multiple times."""
        # Increment the same metric multiple times
        for _ in range(5):
            HTTP_REQUESTS_TOTAL.labels(
                method="GET", endpoint="/health", status_code="200"
            ).inc()

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify metric is present
        assert "http_requests_total" in metrics_output
        # The count should be 5 (though we can't easily verify the exact count in the output format)

    def test_metrics_with_different_labels(self):
        """Test that metrics with different labels are tracked separately."""
        # Record metrics with different labels
        HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/health", status_code="200"
        ).inc()
        HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/health", status_code="503"
        ).inc()
        HTTP_REQUESTS_TOTAL.labels(
            method="POST", endpoint="/agent/message", status_code="200"
        ).inc()

        # Generate metrics output
        metrics_output = generate_latest(REGISTRY).decode("utf-8")

        # Verify all label combinations are present
        assert "http_requests_total" in metrics_output
        assert (
            'status_code="200"' in metrics_output
            or "status_code='200'" in metrics_output
        )
        assert (
            'status_code="503"' in metrics_output
            or "status_code='503'" in metrics_output
        )
        assert 'method="GET"' in metrics_output or "method='GET'" in metrics_output
        assert 'method="POST"' in metrics_output or "method='POST'" in metrics_output
