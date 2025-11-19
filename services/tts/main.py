import asyncio
import logging
import os

from inference_core import TtsGrpcApp
from inference_core.tts.espeak_strategy import EspeakTtsStrategy
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)
from prometheus_client.exposition import start_http_server

# Initialize tracing early
try:
    import sys
    from pathlib import Path

    # Add essence package to path for tracing import
    essence_path = Path(__file__).parent.parent.parent / "essence"
    if str(essence_path) not in sys.path:
        sys.path.insert(0, str(essence_path))
    from essence.chat.utils.tracing import setup_tracing

    setup_tracing(service_name="june-tts")
except ImportError:
    pass

# Import rate limiting
try:
    from june_rate_limit import RateLimitConfig, RateLimitInterceptor

    RATE_LIMIT_AVAILABLE = True
except ImportError:
    RATE_LIMIT_AVAILABLE = False
    RateLimitInterceptor = None
    RateLimitConfig = None

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
REGISTRY = CollectorRegistry()
TTS_REQUESTS_TOTAL = Counter(
    "tts_requests_total", "Total TTS requests", ["status"], registry=REGISTRY
)
TTS_SYNTHESIS_TIME = Histogram(
    "tts_synthesis_time_seconds", "TTS synthesis time", registry=REGISTRY
)
TTS_AUDIO_DURATION = Histogram(
    "tts_audio_duration_seconds", "Generated audio duration", registry=REGISTRY
)
TTS_ERRORS_TOTAL = Counter(
    "tts_errors_total", "Total errors", ["error_type"], registry=REGISTRY
)
ACTIVE_CONNECTIONS = Gauge(
    "tts_active_connections", "Active gRPC connections", registry=REGISTRY
)


def main() -> None:
    # Start HTTP server for Prometheus metrics
    metrics_port = int(os.getenv("TTS_METRICS_PORT", "8003"))
    try:
        start_http_server(metrics_port, registry=REGISTRY)
        logger.info(f"Started Prometheus metrics server on port {metrics_port}")
    except Exception as e:
        logger.warning(f"Failed to start metrics server on port {metrics_port}: {e}")

    # Setup interceptors
    interceptors = []
    if RATE_LIMIT_AVAILABLE:
        rate_limit_config = RateLimitConfig(
            default_per_minute=int(os.getenv("RATE_LIMIT_TTS_PER_MINUTE", "60")),
            default_per_hour=int(os.getenv("RATE_LIMIT_TTS_PER_HOUR", "1000")),
            use_redis=False,  # Use in-memory rate limiting for MVP (Redis not required)
            fallback_to_memory=True,
        )
        rate_limit_interceptor = RateLimitInterceptor(config=rate_limit_config)
        interceptors.append(rate_limit_interceptor)
        logger.info(
            "Rate limiting enabled for TTS service (in-memory, Redis not required)"
        )

    strategy = EspeakTtsStrategy(sample_rate=int(os.getenv("TTS_SAMPLE_RATE", "16000")))
    app = TtsGrpcApp(strategy, interceptors=interceptors if interceptors else None)
    app.initialize()
    app.run()


if __name__ == "__main__":
    main()
