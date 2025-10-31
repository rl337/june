from __future__ import annotations

import os
import grpc
from concurrent import futures
from typing import Optional

from ..strategies import LlmStrategy, InferenceRequest
from ..utils import setup_logging
from ..config import config
from june_grpc_api.generated import llm_pb2, llm_pb2_grpc


class _LlmServicer(llm_pb2_grpc.LLMInferenceServicer):
    def __init__(self, strategy: LlmStrategy) -> None:
        self._strategy = strategy

    def Generate(self, request: llm_pb2.GenerationRequest, context) -> llm_pb2.GenerationResponse:
        params = {}
        if request.params:
            params = {"max_tokens": request.params.max_tokens, "temperature": request.params.temperature}
        result = self._strategy.infer(
            InferenceRequest(
                payload={"prompt": request.prompt, "params": params},
                metadata={}
            )
        )
        if isinstance(result.payload, dict):
            text = result.payload.get("text", "")
        else:
            text = str(result.payload)
        return llm_pb2.GenerationResponse(text=text)


class LlmGrpcApp:
    def __init__(self, strategy: LlmStrategy, port: Optional[int] = None) -> None:
        self.strategy = strategy
        self.port = port or int(os.getenv("LLM_PORT", "50051"))
        self._server: Optional[grpc.Server] = None

    def initialize(self) -> None:
        setup_logging(config.monitoring.log_level, "llm")
        self.strategy.warmup()

    def run(self) -> None:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        llm_pb2_grpc.add_LLMInferenceServicer_to_server(_LlmServicer(self.strategy), server)
        server.add_insecure_port(f"[::]:{self.port}")
        server.start()
        server.wait_for_termination()

