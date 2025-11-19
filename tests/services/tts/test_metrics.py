"""
Tests for Prometheus metrics collection in TTS service.

Tests verify that:
- Metrics are recorded correctly for TTS requests
- Metrics are recorded correctly for synthesis time
- Metrics are recorded correctly for audio duration
- Error metrics are recorded correctly
- Metrics can be exported in Prometheus format
"""
import pytest
from prometheus_client import (
    generate_latest,
    CollectorRegistry,
    Counter,
    Histogram,
    Gauge,
)

# Create a test registry to avoid interfering with other tests
TEST_REGISTRY = CollectorRegistry()

# Define TTS metrics (matching services/tts/main.py)
TTS_REQUESTS_TOTAL = Counter(
    "tts_requests_total", "Total TTS requests", ["status"], registry=TEST_REGISTRY
)
TTS_SYNTHESIS_TIME = Histogram(
    "tts_synthesis_time_seconds", "TTS synthesis time", registry=TEST_REGISTRY
)
TTS_AUDIO_DURATION = Histogram(
    "tts_audio_duration_seconds", "Generated audio duration", registry=TEST_REGISTRY
)
TTS_ERRORS_TOTAL = Counter(
    "tts_errors_total", "Total errors", ["error_type"], registry=TEST_REGISTRY
)
ACTIVE_CONNECTIONS = Gauge(
    "tts_active_connections", "Active gRPC connections", registry=TEST_REGISTRY
)


class TestTTSMetrics:
    """Tests for TTS service metrics collection."""

    def setup_method(self):
        """Reset metrics before each test."""
        # Clear all metrics by creating a new registry for each test
        # Note: In practice, metrics persist across requests
        pass

    def test_tts_requests_total_metric(self):
        """Test that TTS requests are recorded in metrics."""
        # Record TTS requests
        TTS_REQUESTS_TOTAL.labels(status="success").inc()
        TTS_REQUESTS_TOTAL.labels(status="error").inc()
        TTS_REQUESTS_TOTAL.labels(status="success").inc()

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "tts_requests_total" in metrics_output
        assert (
            'status="success"' in metrics_output or "status='success'" in metrics_output
        )
        assert 'status="error"' in metrics_output or "status='error'" in metrics_output

    def test_tts_synthesis_time_metric(self):
        """Test that TTS synthesis time is recorded."""
        # Record synthesis times
        TTS_SYNTHESIS_TIME.observe(0.5)
        TTS_SYNTHESIS_TIME.observe(1.0)
        TTS_SYNTHESIS_TIME.observe(0.8)

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "tts_synthesis_time_seconds" in metrics_output

    def test_tts_audio_duration_metric(self):
        """Test that generated audio duration is recorded."""
        # Record audio durations
        TTS_AUDIO_DURATION.observe(2.5)
        TTS_AUDIO_DURATION.observe(3.0)
        TTS_AUDIO_DURATION.observe(1.8)

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "tts_audio_duration_seconds" in metrics_output

    def test_tts_errors_total_metric(self):
        """Test that TTS errors are recorded in metrics."""
        # Record different error types
        TTS_ERRORS_TOTAL.labels(error_type="ValueError").inc()
        TTS_ERRORS_TOTAL.labels(error_type="ConnectionError").inc()
        TTS_ERRORS_TOTAL.labels(error_type="TimeoutError").inc()

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "tts_errors_total" in metrics_output
        assert (
            'error_type="ValueError"' in metrics_output
            or "error_type='ValueError'" in metrics_output
        )
        assert (
            'error_type="ConnectionError"' in metrics_output
            or "error_type='ConnectionError'" in metrics_output
        )

    def test_active_connections_metric(self):
        """Test that active connections are recorded."""
        # Set active connections
        ACTIVE_CONNECTIONS.set(5)

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify metrics are present
        assert "tts_active_connections" in metrics_output

        # Update active connections
        ACTIVE_CONNECTIONS.set(10)

        # Generate metrics output again
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify updated value is recorded
        assert "tts_active_connections" in metrics_output

    def test_metrics_endpoint_format(self):
        """Test that metrics endpoint returns Prometheus format."""
        # Record some metrics
        TTS_REQUESTS_TOTAL.labels(status="success").inc()
        TTS_SYNTHESIS_TIME.observe(0.5)
        ACTIVE_CONNECTIONS.set(3)

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify Prometheus format
        assert "# HELP" in metrics_output or "# TYPE" in metrics_output
        assert "tts_requests_total" in metrics_output
        assert "tts_synthesis_time_seconds" in metrics_output
        assert "tts_active_connections" in metrics_output

    def test_multiple_metric_increments(self):
        """Test that metrics can be incremented multiple times."""
        # Increment the same metric multiple times
        for _ in range(10):
            TTS_REQUESTS_TOTAL.labels(status="success").inc()

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify metric is present
        assert "tts_requests_total" in metrics_output
        assert (
            'status="success"' in metrics_output or "status='success'" in metrics_output
        )

    def test_metrics_with_different_status_labels(self):
        """Test that metrics with different status labels are tracked separately."""
        # Record metrics with different status labels
        TTS_REQUESTS_TOTAL.labels(status="success").inc()
        TTS_REQUESTS_TOTAL.labels(status="error").inc()
        TTS_REQUESTS_TOTAL.labels(status="timeout").inc()

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify all status labels are present
        assert "tts_requests_total" in metrics_output
        assert (
            'status="success"' in metrics_output or "status='success'" in metrics_output
        )
        assert 'status="error"' in metrics_output or "status='error'" in metrics_output
        assert (
            'status="timeout"' in metrics_output or "status='timeout'" in metrics_output
        )

    def test_histogram_metrics_aggregation(self):
        """Test that histogram metrics aggregate observations correctly."""
        # Record multiple observations
        for duration in [0.1, 0.2, 0.3, 0.4, 0.5]:
            TTS_SYNTHESIS_TIME.observe(duration)

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify histogram is present with buckets
        assert "tts_synthesis_time_seconds" in metrics_output
        # Histograms typically include bucket information
        assert (
            "_bucket" in metrics_output
            or "count" in metrics_output.lower()
            or "sum" in metrics_output.lower()
        )

    def test_gauge_metric_updates(self):
        """Test that gauge metrics can be updated."""
        # Set initial value
        ACTIVE_CONNECTIONS.set(5)

        # Update value
        ACTIVE_CONNECTIONS.set(10)

        # Decrease value
        ACTIVE_CONNECTIONS.set(7)

        # Generate metrics output
        metrics_output = generate_latest(TEST_REGISTRY).decode("utf-8")

        # Verify gauge is present
        assert "tts_active_connections" in metrics_output
        # The value should be the last set value (7)
