"""
Shared Prometheus metrics for june services.

This module provides standardized metrics that all services should use
for consistent observability across the platform.
"""
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

# Create a shared registry (services can use their own if needed)
REGISTRY = CollectorRegistry()

# HTTP Request Metrics
HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code'],
    registry=REGISTRY
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint', 'status_code'],
    registry=REGISTRY
)

# gRPC Request Metrics
GRPC_REQUESTS_TOTAL = Counter(
    'grpc_requests_total',
    'Total gRPC requests',
    ['service', 'method', 'status_code'],
    registry=REGISTRY
)

GRPC_REQUEST_DURATION_SECONDS = Histogram(
    'grpc_request_duration_seconds',
    'gRPC request duration in seconds',
    ['service', 'method', 'status_code'],
    registry=REGISTRY
)

# Voice Processing Metrics
VOICE_MESSAGES_PROCESSED_TOTAL = Counter(
    'voice_messages_processed_total',
    'Total voice messages processed',
    ['platform', 'status'],
    registry=REGISTRY
)

VOICE_PROCESSING_DURATION_SECONDS = Histogram(
    'voice_processing_duration_seconds',
    'Voice message processing duration in seconds',
    ['platform', 'status'],
    registry=REGISTRY
)

STT_TRANSCRIPTION_DURATION_SECONDS = Histogram(
    'stt_transcription_duration_seconds',
    'STT transcription duration in seconds',
    ['platform', 'status'],
    registry=REGISTRY
)

TTS_SYNTHESIS_DURATION_SECONDS = Histogram(
    'tts_synthesis_duration_seconds',
    'TTS synthesis duration in seconds',
    ['platform', 'status'],
    registry=REGISTRY
)

LLM_GENERATION_DURATION_SECONDS = Histogram(
    'llm_generation_duration_seconds',
    'LLM generation duration in seconds',
    ['platform', 'status'],
    registry=REGISTRY
)

# Error Metrics
ERRORS_TOTAL = Counter(
    'errors_total',
    'Total errors',
    ['service', 'error_type'],
    registry=REGISTRY
)

# Service Health Metrics
SERVICE_HEALTH = Gauge(
    'service_health',
    'Service health status (1 = healthy, 0 = unhealthy)',
    ['service'],
    registry=REGISTRY
)
