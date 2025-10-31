from __future__ import annotations

import os
import grpc
from concurrent import futures
from typing import Optional

from ..strategies import SttStrategy
from ..utils import setup_logging
from ..config import config
from june_grpc_api.generated import asr_pb2, asr_pb2_grpc


class _SttServicer(asr_pb2_grpc.SpeechToTextServicer):
    def __init__(self, strategy: SttStrategy) -> None:
        self._strategy = strategy

    def Recognize(self, request: asr_pb2.RecognitionRequest, context) -> asr_pb2.RecognitionResponse:
        result = self._strategy.infer(
            # InferenceRequest mapping: use bytes payload and metadata
            request.audio_data
        )
        resp = asr_pb2.RecognitionResponse()
        r = resp.results.add()
        r.transcript = result.payload if isinstance(result.payload, str) else str(result.payload)
        r.confidence = float(result.metadata.get("confidence", 0.0)) if result.metadata else 0.0
        return resp


class SttGrpcApp:
    def __init__(self, strategy: SttStrategy, port: Optional[int] = None) -> None:
        self.strategy = strategy
        self.port = port or int(os.getenv("STT_PORT", "50052"))
        self._server: Optional[grpc.Server] = None

    def initialize(self) -> None:
        setup_logging(config.monitoring.log_level, "stt")
        self.strategy.warmup()

    def run(self) -> None:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        asr_pb2_grpc.add_SpeechToTextServicer_to_server(_SttServicer(self.strategy), server)
        server.add_insecure_port(f"[::]:{self.port}")
        server.start()
        server.wait_for_termination()




