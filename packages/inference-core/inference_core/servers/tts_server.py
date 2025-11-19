from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import grpc
from grpc import aio
from june_grpc_api.generated import tts_pb2, tts_pb2_grpc

from ..config import config
from ..strategies import InferenceRequest, TtsStrategy
from ..utils import setup_logging

logger = logging.getLogger(__name__)

# Try to import tracing
tracer = None
try:
    import sys
    from pathlib import Path

    # Add essence package to path for tracing import
    essence_path = Path(__file__).parent.parent.parent.parent / "essence"
    if str(essence_path) not in sys.path:
        sys.path.insert(0, str(essence_path))
    from opentelemetry import trace

    from essence.chat.utils.tracing import get_tracer

    tracer = get_tracer(__name__)
except (ImportError, Exception) as e:
    logger.debug(f"Tracing not available: {e}")
    tracer = None


class _TtsServicer(tts_pb2_grpc.TextToSpeechServicer):
    def __init__(self, strategy: TtsStrategy) -> None:
        self._strategy = strategy
        self._sample_rate = 16000

    async def Synthesize(
        self, request: tts_pb2.SynthesisRequest, context: aio.ServicerContext
    ) -> tts_pb2.AudioResponse:
        span = None
        if tracer is not None:
            span = tracer.start_span("tts.synthesize")
            span.set_attribute("tts.text_length", len(request.text))
            if request.voice_id:
                span.set_attribute("tts.voice_id", request.voice_id)
            if request.language:
                span.set_attribute("tts.language", request.language)

        try:
            result = self._strategy.infer(
                InferenceRequest(
                    payload=request.text,
                    metadata={
                        "voice_id": request.voice_id,
                        "language": request.language,
                    },
                )
            )
            audio_bytes = (
                result.payload
                if isinstance(result.payload, bytes)
                else bytes(result.payload)
            )
            sample_rate = result.metadata.get("sample_rate", self._sample_rate)
            duration_ms = result.metadata.get(
                "duration_ms", int(len(audio_bytes) / sample_rate / 2 * 1000)
            )

            # Update span with results
            if span:
                span.set_attribute("tts.audio_size_bytes", len(audio_bytes))
                span.set_attribute("tts.sample_rate", sample_rate)
                span.set_attribute("tts.duration_ms", duration_ms)
                span.set_status(trace.Status(trace.StatusCode.OK))

            return tts_pb2.AudioResponse(
                audio_data=audio_bytes,
                sample_rate=sample_rate,
                encoding="pcm16",
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}", exc_info=True)
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
            raise
        finally:
            if span:
                span.end()

    async def HealthCheck(
        self, request: tts_pb2.HealthRequest, context: aio.ServicerContext
    ) -> tts_pb2.HealthResponse:
        """Health check endpoint."""
        span = None
        if tracer is not None:
            span = tracer.start_span("tts.health_check")

        try:
            # Check if strategy is available and healthy
            is_healthy = self._strategy is not None

            # Try to check strategy health if it has a health check method
            if is_healthy and hasattr(self._strategy, "is_healthy"):
                try:
                    is_healthy = self._strategy.is_healthy()
                except Exception as e:
                    logger.warning(f"Strategy health check failed: {e}")
                    is_healthy = False

            # Get available voices if strategy supports it
            available_voices = []
            if is_healthy and hasattr(self._strategy, "get_available_voices"):
                try:
                    available_voices = self._strategy.get_available_voices()
                except Exception:
                    # If not supported, use default
                    available_voices = ["default"]

            if span:
                span.set_attribute("tts.healthy", is_healthy)
                span.set_attribute("tts.available_voices_count", len(available_voices))
                span.set_status(
                    trace.Status(
                        trace.StatusCode.OK if is_healthy else trace.StatusCode.ERROR
                    )
                )

            return tts_pb2.HealthResponse(
                healthy=is_healthy,
                version="0.2.0",
                available_voices=available_voices if available_voices else ["default"],
            )
        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
            return tts_pb2.HealthResponse(
                healthy=False, version="0.2.0", available_voices=[]
            )
        finally:
            if span:
                span.end()


class TtsGrpcApp:
    def __init__(
        self,
        strategy: TtsStrategy,
        port: Optional[int] = None,
        interceptors: Optional[list] = None,
    ) -> None:
        self.strategy = strategy
        self.port = port or int(os.getenv("TTS_PORT", "50053"))
        self._server: Optional[aio.Server] = None
        self.interceptors = interceptors or []

    def initialize(self) -> None:
        setup_logging(config.monitoring.log_level, "tts")
        self.strategy.warmup()

    async def _run_async(self) -> None:
        server = aio.server(
            interceptors=self.interceptors if self.interceptors else None
        )
        tts_pb2_grpc.add_TextToSpeechServicer_to_server(
            _TtsServicer(self.strategy), server
        )
        server.add_insecure_port(f"[::]:{self.port}")
        await server.start()
        await server.wait_for_termination()

    def run(self) -> None:
        asyncio.run(self._run_async())
