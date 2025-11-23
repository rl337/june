from __future__ import annotations

import logging
import os
from concurrent import futures
from typing import Iterator, Optional

import grpc
from june_grpc_api.generated import llm_pb2, llm_pb2_grpc

from ..config import config
from ..strategies import InferenceRequest, LlmStrategy
from .. import setup_logging

logger = logging.getLogger(__name__)


def _format_chat_messages(messages: list[llm_pb2.ChatMessage]) -> str:
    """Format chat messages into a prompt string.

    Converts gRPC ChatMessage objects into a prompt format suitable for Qwen3.
    Uses a simple format: role: content per message.
    """
    formatted_parts = []
    for message in messages:
        role = message.role
        content = message.content

        if role == "system":
            formatted_parts.append(f"System: {content}")
        elif role == "user":
            formatted_parts.append(f"Human: {content}")
        elif role == "assistant":
            formatted_parts.append(f"Assistant: {content}")
        elif role == "tool":
            formatted_parts.append(f"Tool: {content}")

    # Add prompt for assistant response
    formatted_parts.append("Assistant:")
    return "\n\n".join(formatted_parts)


def _extract_generation_params(params: Optional[llm_pb2.GenerationParameters]) -> dict:
    """Extract generation parameters from gRPC message."""
    if not params:
        return {}

    result = {}
    if params.max_tokens > 0:
        result["max_tokens"] = params.max_tokens
    if params.temperature > 0:
        result["temperature"] = params.temperature
    if params.top_p > 0:
        result["top_p"] = params.top_p
    if params.top_k > 0:
        result["top_k"] = params.top_k
    if params.repetition_penalty > 0:
        result["repetition_penalty"] = params.repetition_penalty

    return result


class _LlmServicer(llm_pb2_grpc.LLMInferenceServicer):
    def __init__(self, strategy: LlmStrategy) -> None:
        self._strategy = strategy

    def Generate(
        self, request: llm_pb2.GenerationRequest, context
    ) -> llm_pb2.GenerationResponse:
        """One-shot text generation."""
        try:
            params = _extract_generation_params(request.params)
            result = self._strategy.infer(
                InferenceRequest(
                    payload={"prompt": request.prompt, "params": params}, metadata={}
                )
            )

            # Extract response
            if isinstance(result.payload, dict):
                text = result.payload.get("text", "")
                tokens = result.payload.get("tokens", 0)
            else:
                text = str(result.payload)
                tokens = 0

            # Build response
            response = llm_pb2.GenerationResponse(
                text=text,
                tokens_generated=tokens,
                finish_reason=llm_pb2.FinishReason.STOP,
            )

            # Add usage stats if available
            if result.metadata:
                input_tokens = result.metadata.get("input_tokens", 0)
                output_tokens = result.metadata.get("output_tokens", tokens)
                response.usage.prompt_tokens = input_tokens
                response.usage.completion_tokens = output_tokens
                response.usage.total_tokens = input_tokens + output_tokens

            return response

        except Exception as e:
            logger.error(f"Generation error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return llm_pb2.GenerationResponse(
                text="", finish_reason=llm_pb2.FinishReason.ERROR
            )

    def GenerateStream(
        self, request: llm_pb2.GenerationRequest, context
    ) -> Iterator[llm_pb2.GenerationChunk]:
        """Streaming text generation."""
        try:
            params = _extract_generation_params(request.params)
            result = self._strategy.infer(
                InferenceRequest(
                    payload={"prompt": request.prompt, "params": params}, metadata={}
                )
            )

            # Extract response
            if isinstance(result.payload, dict):
                text = result.payload.get("text", "")
            else:
                text = str(result.payload)

            # Stream text in chunks (simplified - split by words)
            tokens = text.split()
            for i, token in enumerate(tokens):
                is_final = i == len(tokens) - 1
                chunk = llm_pb2.GenerationChunk(
                    token=token + (" " if not is_final else ""),
                    is_final=is_final,
                    index=i,
                    finish_reason=llm_pb2.FinishReason.STOP
                    if is_final
                    else llm_pb2.FinishReason.STOP,
                )
                yield chunk

        except Exception as e:
            logger.error(f"Generation stream error: {e}", exc_info=True)
            error_chunk = llm_pb2.GenerationChunk(
                token="", is_final=True, finish_reason=llm_pb2.FinishReason.ERROR
            )
            yield error_chunk

    def Chat(self, request: llm_pb2.ChatRequest, context) -> llm_pb2.ChatResponse:
        """One-shot chat with conversation history."""
        try:
            # Format messages into prompt
            formatted_prompt = _format_chat_messages(request.messages)

            # Extract parameters
            params = _extract_generation_params(request.params)

            # Generate response
            result = self._strategy.infer(
                InferenceRequest(
                    payload={"prompt": formatted_prompt, "params": params}, metadata={}
                )
            )

            # Extract response text
            if isinstance(result.payload, dict):
                text = result.payload.get("text", "").strip()
                tokens = result.payload.get("tokens", 0)
            else:
                text = str(result.payload).strip()
                tokens = 0

            # Build response
            assistant_message = llm_pb2.ChatMessage(role="assistant", content=text)

            response = llm_pb2.ChatResponse(
                message=assistant_message, tokens_generated=tokens
            )

            # Add usage stats if available
            if result.metadata:
                input_tokens = result.metadata.get("input_tokens", 0)
                output_tokens = result.metadata.get("output_tokens", tokens)
                response.usage.prompt_tokens = input_tokens
                response.usage.completion_tokens = output_tokens
                response.usage.total_tokens = input_tokens + output_tokens

            return response

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return llm_pb2.ChatResponse(
                message=llm_pb2.ChatMessage(role="assistant", content="")
            )

    def ChatStream(
        self, request: llm_pb2.ChatRequest, context
    ) -> Iterator[llm_pb2.ChatChunk]:
        """Streaming chat with conversation history."""
        try:
            # Format messages into prompt
            formatted_prompt = _format_chat_messages(request.messages)

            # Extract parameters
            params = _extract_generation_params(request.params)

            # Generate response
            result = self._strategy.infer(
                InferenceRequest(
                    payload={"prompt": formatted_prompt, "params": params}, metadata={}
                )
            )

            # Extract response text
            if isinstance(result.payload, dict):
                text = result.payload.get("text", "").strip()
            else:
                text = str(result.payload).strip()

            # Stream text in chunks (simplified - split by words)
            tokens = text.split()
            for i, token in enumerate(tokens):
                is_final = i == len(tokens) - 1
                chunk = llm_pb2.ChatChunk(
                    content_delta=token + (" " if not is_final else ""),
                    role="assistant",
                    is_final=is_final,
                    finish_reason=llm_pb2.FinishReason.STOP
                    if is_final
                    else llm_pb2.FinishReason.STOP,
                )
                yield chunk

        except Exception as e:
            logger.error(f"Chat stream error: {e}", exc_info=True)
            error_chunk = llm_pb2.ChatChunk(
                content_delta="",
                role="assistant",
                is_final=True,
                finish_reason=llm_pb2.FinishReason.ERROR,
            )
            yield error_chunk


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
        llm_pb2_grpc.add_LLMInferenceServicer_to_server(
            _LlmServicer(self.strategy), server
        )
        server.add_insecure_port(f"[::]:{self.port}")
        server.start()
        server.wait_for_termination()
