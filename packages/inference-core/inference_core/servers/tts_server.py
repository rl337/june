from __future__ import annotations

import os
import asyncio
import grpc
from grpc import aio
from typing import Optional

from ..strategies import TtsStrategy, InferenceRequest
from ..utils import setup_logging
from ..config import config
from june_grpc_api.generated import tts_pb2, tts_pb2_grpc


class _TtsServicer(tts_pb2_grpc.TextToSpeechServicer):
    def __init__(self, strategy: TtsStrategy) -> None:
        self._strategy = strategy
        self._sample_rate = 16000

    async def Synthesize(self, request: tts_pb2.SynthesisRequest, context: aio.ServicerContext) -> tts_pb2.AudioResponse:
        result = self._strategy.infer(
            InferenceRequest(
                payload=request.text,
                metadata={"voice_id": request.voice_id, "language": request.language}
            )
        )
        audio_bytes = result.payload if isinstance(result.payload, bytes) else bytes(result.payload)
        sample_rate = result.metadata.get("sample_rate", self._sample_rate)
        duration_ms = result.metadata.get("duration_ms", int(len(audio_bytes) / sample_rate / 2 * 1000))
        
        return tts_pb2.AudioResponse(
            audio_data=audio_bytes,
            sample_rate=sample_rate,
            encoding="pcm16",
            duration_ms=duration_ms
        )


class TtsGrpcApp:
    def __init__(self, strategy: TtsStrategy, port: Optional[int] = None, interceptors: Optional[list] = None) -> None:
        self.strategy = strategy
        self.port = port or int(os.getenv("TTS_PORT", "50053"))
        self._server: Optional[aio.Server] = None
        self.interceptors = interceptors or []

    def initialize(self) -> None:
        setup_logging(config.monitoring.log_level, "tts")
        self.strategy.warmup()

    async def _run_async(self) -> None:
        server = aio.server(interceptors=self.interceptors if self.interceptors else None)
        tts_pb2_grpc.add_TextToSpeechServicer_to_server(_TtsServicer(self.strategy), server)
        server.add_insecure_port(f"[::]:{self.port}")
        await server.start()
        await server.wait_for_termination()

    def run(self) -> None:
        asyncio.run(self._run_async())

