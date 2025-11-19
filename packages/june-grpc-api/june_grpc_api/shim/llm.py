from typing import AsyncGenerator, Dict, List, Optional

import grpc

from ..generated import llm_pb2, llm_pb2_grpc


class GenerationParams:
    def __init__(self, max_tokens: int = 128, temperature: float = 0.7):
        self.max_tokens = max_tokens
        self.temperature = temperature

    def to_proto(self) -> llm_pb2.GenerationParameters:
        return llm_pb2.GenerationParameters(
            max_tokens=self.max_tokens, temperature=self.temperature
        )


class LLMClient:
    """gRPC client for Inference API service.

    Supports both one-shot and streaming generation/chat operations.
    """

    def __init__(self, channel: grpc.Channel):
        self._stub = llm_pb2_grpc.LLMInferenceStub(channel)

    async def generate(
        self,
        prompt: str,
        params: Optional[GenerationParams] = None,
        timeout: Optional[float] = 30.0,
    ) -> str:
        """One-shot text generation.

        Args:
            prompt: Input prompt text
            params: Optional generation parameters
            timeout: Request timeout in seconds

        Returns:
            Generated text response
        """
        p = (params or GenerationParams()).to_proto()
        request = llm_pb2.GenerationRequest(prompt=prompt, params=p)
        response = await self._stub.Generate(request, timeout=timeout)
        return response.text

    async def generate_stream(
        self,
        prompt: str,
        params: Optional[GenerationParams] = None,
        timeout: Optional[float] = 30.0,
    ) -> AsyncGenerator[str, None]:
        """Streaming text generation.

        Args:
            prompt: Input prompt text
            params: Optional generation parameters
            timeout: Request timeout in seconds

        Yields:
            Text chunks as they are generated
        """
        p = (params or GenerationParams()).to_proto()
        request = llm_pb2.GenerationRequest(prompt=prompt, params=p, stream=True)

        async for chunk in self._stub.GenerateStream(request, timeout=timeout):
            if chunk.token:
                yield chunk.token
            if chunk.is_final:
                break

    async def chat(
        self,
        messages: List[Dict[str, str]],
        params: Optional[GenerationParams] = None,
        timeout: Optional[float] = 30.0,
    ) -> str:
        """One-shot chat with conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Roles can be: 'system', 'user', 'assistant', 'tool'
            params: Optional generation parameters
            timeout: Request timeout in seconds

        Returns:
            Assistant's response text

        Example:
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ]
            response = await client.chat(messages)
        """
        p = (params or GenerationParams()).to_proto()

        # Convert message dicts to ChatMessage protos
        chat_messages = []
        for msg in messages:
            chat_msg = llm_pb2.ChatMessage(
                role=msg.get("role", "user"), content=msg.get("content", "")
            )
            chat_messages.append(chat_msg)

        request = llm_pb2.ChatRequest(messages=chat_messages, params=p)
        response = await self._stub.Chat(request, timeout=timeout)
        return response.message.content

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        params: Optional[GenerationParams] = None,
        timeout: Optional[float] = 30.0,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat with conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Roles can be: 'system', 'user', 'assistant', 'tool'
            params: Optional generation parameters
            timeout: Request timeout in seconds

        Yields:
            Text chunks as they are generated

        Example:
            messages = [
                {"role": "user", "content": "Tell me a story"}
            ]
            async for chunk in client.chat_stream(messages):
                print(chunk, end='', flush=True)
        """
        p = (params or GenerationParams()).to_proto()

        # Convert message dicts to ChatMessage protos
        chat_messages = []
        for msg in messages:
            chat_msg = llm_pb2.ChatMessage(
                role=msg.get("role", "user"), content=msg.get("content", "")
            )
            chat_messages.append(chat_msg)

        request = llm_pb2.ChatRequest(messages=chat_messages, params=p, stream=True)

        async for chunk in self._stub.ChatStream(request, timeout=timeout):
            if chunk.content_delta:
                yield chunk.content_delta
            if chunk.is_final:
                break
