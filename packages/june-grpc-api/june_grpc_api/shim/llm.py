import grpc
from typing import Optional

from ..generated import llm_pb2, llm_pb2_grpc


class GenerationParams:
    def __init__(self, max_tokens: int = 128, temperature: float = 0.7):
        self.max_tokens = max_tokens
        self.temperature = temperature

    def to_proto(self) -> llm_pb2.GenerationParameters:
        return llm_pb2.GenerationParameters(max_tokens=self.max_tokens, temperature=self.temperature)


class LLMClient:
    def __init__(self, channel: grpc.Channel):
        self._stub = llm_pb2_grpc.LLMInferenceStub(channel)

    async def generate(self, prompt: str, params: Optional[GenerationParams] = None, timeout: Optional[float] = 30.0) -> str:
        p = (params or GenerationParams()).to_proto()
        request = llm_pb2.GenerationRequest(prompt=prompt, params=p)
        response = await self._stub.Generate(request, timeout=timeout)
        return response.text




