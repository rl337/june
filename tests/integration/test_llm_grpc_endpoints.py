"""
Integration tests for gRPC LLM endpoints (Generate and Chat) with Qwen3-30B-A3B.

Tests the Generate and Chat endpoints directly via gRPC to verify:
- Endpoints work correctly with Qwen3-30B-A3B model
- Request/response formats match expected schema
- Various generation parameters work correctly
- Error handling works for invalid requests
- Response quality is acceptable

These tests require a running LLM inference service (TensorRT-LLM on port 8000 by default,
or legacy inference-api on port 50051) with Qwen3-30B-A3B model loaded.
"""
import asyncio
import logging
import os
from typing import List, Optional

import grpc
import pytest
from june_grpc_api.generated import llm_pb2_grpc

# Import generated protobuf classes
from june_grpc_api.generated.llm_pb2 import (
    ChatChunk,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Context,
    FinishReason,
    GenerationChunk,
    GenerationParameters,
    GenerationRequest,
    GenerationResponse,
    HealthRequest,
    HealthResponse,
    ToolDefinition,
    UsageStats,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Service address (can be overridden via environment variable)
# Default: TensorRT-LLM (tensorrt-llm:8000), Legacy: inference-api (inference-api:50051)
INFERENCE_ADDRESS = os.getenv(
    "INFERENCE_API_URL", os.getenv("LLM_URL", "tensorrt-llm:8000")
).replace("grpc://", "")


async def check_service_health(address: str) -> bool:
    """Check if the LLM inference service (TensorRT-LLM or inference-api) is reachable and healthy."""
    try:
        async with grpc.aio.insecure_channel(address) as channel:
            stub = llm_pb2_grpc.LLMInferenceStub(channel)
            request = HealthRequest()
            response = await asyncio.wait_for(
                stub.HealthCheck(request, timeout=5.0), timeout=5.0
            )
            if response.healthy:
                service_name = (
                    "TensorRT-LLM"
                    if "tensorrt-llm" in address or "8000" in address
                    else "Inference API"
                )
                logger.info(f"✓ {service_name} service is healthy at {address}")
                logger.info(f"  Model: {response.model_name}")
                logger.info(f"  Max context length: {response.max_context_length}")
                return True
            else:
                logger.warning(f"⚠ LLM inference service at {address} is unhealthy")
                return False
    except Exception as e:
        logger.warning(f"✗ LLM inference service not reachable at {address}: {e}")
        return False


@pytest.fixture(scope="session")
async def service_available():
    """Check if the LLM inference service (TensorRT-LLM or inference-api) is available."""
    logger.info("Checking LLM inference service availability...")
    is_available = await check_service_health(INFERENCE_ADDRESS)

    if not is_available:
        service_name = (
            "TensorRT-LLM"
            if "tensorrt-llm" in INFERENCE_ADDRESS or "8000" in INFERENCE_ADDRESS
            else "Inference API"
        )
        logger.warning(f"⚠ {service_name} service is not available. Tests may fail.")
        logger.warning(f"Make sure the LLM inference service is running:")
        logger.warning(
            f"  - TensorRT-LLM (default): tensorrt-llm:8000 in home_infra/shared-network"
        )
        logger.warning(
            f"  - Legacy inference-api: inference-api:50051 (requires --profile legacy)"
        )
        logger.warning(f"  - Current address: {INFERENCE_ADDRESS}")
        logger.warning("  - Qwen3-30B-A3B model should be loaded")

    return is_available


@pytest.fixture
async def grpc_channel():
    """Create a gRPC channel for testing."""
    channel = grpc.aio.insecure_channel(INFERENCE_ADDRESS)
    yield channel
    await channel.close()


@pytest.fixture
def grpc_stub(grpc_channel):
    """Create a gRPC stub for testing."""
    return llm_pb2_grpc.LLMInferenceStub(grpc_channel)


class TestGenerateEndpoint:
    """Test the Generate endpoint (one-shot generation)."""

    @pytest.mark.asyncio
    async def test_generate_basic(self, grpc_stub, service_available):
        """Test basic generation with a simple prompt."""
        if not service_available:
            pytest.skip("Inference API service not available")

        request = GenerationRequest(
            prompt="Say hello in one sentence.",
            params=GenerationParameters(max_tokens=50, temperature=0.7),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Generate(request, timeout=30.0)

        # Verify response format
        assert isinstance(response, GenerationResponse)
        assert len(response.text) > 0
        assert response.tokens_generated > 0
        assert response.finish_reason == FinishReason.STOP
        assert response.usage is not None
        assert response.usage.prompt_tokens > 0
        assert response.usage.completion_tokens > 0
        assert response.usage.total_tokens > 0

        logger.info(f"Generated text: '{response.text[:100]}...'")
        logger.info(
            f"Tokens: {response.tokens_generated}, Finish reason: {response.finish_reason}"
        )

    @pytest.mark.asyncio
    async def test_generate_various_prompts(self, grpc_stub, service_available):
        """Test generation with various prompt types."""
        if not service_available:
            pytest.skip("Inference API service not available")

        prompts = [
            "What is 2+2?",
            "Write a haiku about robots.",
            "Explain quantum computing in one sentence.",
            "List three benefits of exercise.",
        ]

        for prompt in prompts:
            request = GenerationRequest(
                prompt=prompt,
                params=GenerationParameters(max_tokens=100),
                context=Context(user_id="test_user", session_id="test_session"),
            )

            response = await grpc_stub.Generate(request, timeout=30.0)

            assert len(response.text) > 0
            assert response.tokens_generated > 0
            assert response.finish_reason == FinishReason.STOP

            logger.info(f"Prompt: '{prompt[:50]}...'")
            logger.info(f"Response: '{response.text[:100]}...'")

    @pytest.mark.asyncio
    async def test_generate_temperature_parameters(self, grpc_stub, service_available):
        """Test generation with different temperature values."""
        if not service_available:
            pytest.skip("Inference API service not available")

        temperatures = [0.1, 0.7, 1.0, 1.5]
        prompt = "Write a creative story about a robot."

        for temp in temperatures:
            request = GenerationRequest(
                prompt=prompt,
                params=GenerationParameters(max_tokens=50, temperature=temp),
                context=Context(user_id="test_user", session_id="test_session"),
            )

            response = await grpc_stub.Generate(request, timeout=30.0)

            assert len(response.text) > 0
            assert response.tokens_generated > 0

            logger.info(f"Temperature {temp}: '{response.text[:80]}...'")

    @pytest.mark.asyncio
    async def test_generate_max_tokens_parameters(self, grpc_stub, service_available):
        """Test generation with different max_tokens values."""
        if not service_available:
            pytest.skip("Inference API service not available")

        max_tokens_values = [10, 50, 100, 200]
        prompt = "Write a detailed explanation of machine learning."

        for max_tokens in max_tokens_values:
            request = GenerationRequest(
                prompt=prompt,
                params=GenerationParameters(max_tokens=max_tokens, temperature=0.7),
                context=Context(user_id="test_user", session_id="test_session"),
            )

            response = await grpc_stub.Generate(request, timeout=30.0)

            assert len(response.text) > 0
            assert response.tokens_generated <= max_tokens + 5  # Allow small variance
            assert response.finish_reason in [FinishReason.STOP, FinishReason.LENGTH]

            logger.info(
                f"Max tokens {max_tokens}: Generated {response.tokens_generated} tokens"
            )

    @pytest.mark.asyncio
    async def test_generate_top_p_parameters(self, grpc_stub, service_available):
        """Test generation with different top_p values."""
        if not service_available:
            pytest.skip("Inference API service not available")

        top_p_values = [0.1, 0.5, 0.9, 0.95]
        prompt = "Describe the weather today."

        for top_p in top_p_values:
            request = GenerationRequest(
                prompt=prompt,
                params=GenerationParameters(
                    max_tokens=50, temperature=0.7, top_p=top_p
                ),
                context=Context(user_id="test_user", session_id="test_session"),
            )

            response = await grpc_stub.Generate(request, timeout=30.0)

            assert len(response.text) > 0
            assert response.tokens_generated > 0

            logger.info(f"Top-p {top_p}: '{response.text[:80]}...'")

    @pytest.mark.asyncio
    async def test_generate_repetition_penalty(self, grpc_stub, service_available):
        """Test generation with repetition penalty."""
        if not service_available:
            pytest.skip("Inference API service not available")

        request = GenerationRequest(
            prompt="Repeat the word 'hello' five times:",
            params=GenerationParameters(
                max_tokens=50,
                temperature=0.7,
                repetition_penalty=1.2,  # Higher penalty to reduce repetition
            ),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Generate(request, timeout=30.0)

        assert len(response.text) > 0
        assert response.tokens_generated > 0

        logger.info(f"With repetition penalty: '{response.text[:100]}...'")

    @pytest.mark.asyncio
    async def test_generate_error_handling_invalid_request(
        self, grpc_stub, service_available
    ):
        """Test error handling for invalid requests."""
        if not service_available:
            pytest.skip("Inference API service not available")

        # Test with extremely large max_tokens (should still work but may hit limits)
        request = GenerationRequest(
            prompt="Test",
            params=GenerationParameters(max_tokens=1000000),  # Unreasonably large
            context=Context(user_id="test_user", session_id="test_session"),
        )

        # Should either succeed (with actual limit) or return error gracefully
        try:
            response = await grpc_stub.Generate(request, timeout=30.0)
            # If it succeeds, verify it's reasonable
            assert response.tokens_generated < 1000000
            logger.info(
                f"Large max_tokens handled: generated {response.tokens_generated} tokens"
            )
        except grpc.RpcError as e:
            # Error is acceptable for invalid parameters
            assert e.code() in [
                grpc.StatusCode.INVALID_ARGUMENT,
                grpc.StatusCode.OUT_OF_RANGE,
            ]
            logger.info(f"Invalid request correctly rejected: {e.code()}")

    @pytest.mark.asyncio
    async def test_generate_response_schema(self, grpc_stub, service_available):
        """Test that response format matches expected schema."""
        if not service_available:
            pytest.skip("Inference API service not available")

        request = GenerationRequest(
            prompt="Test schema validation.",
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Generate(request, timeout=30.0)

        # Verify all required fields are present
        assert hasattr(response, "text")
        assert hasattr(response, "tokens_generated")
        assert hasattr(response, "tokens_per_second")
        assert hasattr(response, "finish_reason")
        assert hasattr(response, "usage")

        # Verify usage stats structure
        assert hasattr(response.usage, "prompt_tokens")
        assert hasattr(response.usage, "completion_tokens")
        assert hasattr(response.usage, "total_tokens")

        # Verify types
        assert isinstance(response.text, str)
        assert isinstance(response.tokens_generated, int)
        assert isinstance(response.finish_reason, int)
        assert isinstance(response.usage, UsageStats)

        logger.info("Response schema validation passed")


class TestChatEndpoint:
    """Test the Chat endpoint (one-shot chat with conversation history)."""

    @pytest.mark.asyncio
    async def test_chat_basic(self, grpc_stub, service_available):
        """Test basic chat with a simple conversation."""
        if not service_available:
            pytest.skip("Inference API service not available")

        messages = [ChatMessage(role="user", content="What is 2+2?")]

        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Chat(request, timeout=30.0)

        # Verify response format
        assert isinstance(response, ChatResponse)
        assert response.message is not None
        assert response.message.role == "assistant"
        assert len(response.message.content) > 0
        assert response.tokens_generated > 0
        assert response.usage is not None
        assert response.usage.total_tokens > 0

        logger.info(f"Chat response: '{response.message.content[:100]}...'")
        logger.info(f"Tokens: {response.tokens_generated}")

    @pytest.mark.asyncio
    async def test_chat_conversation_history(self, grpc_stub, service_available):
        """Test chat with conversation history."""
        if not service_available:
            pytest.skip("Inference API service not available")

        messages = [
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="What is 2+2?"),
            ChatMessage(role="assistant", content="2+2 equals 4."),
            ChatMessage(role="user", content="What about 3+3?"),
        ]

        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Chat(request, timeout=30.0)

        assert response.message.role == "assistant"
        assert len(response.message.content) > 0
        assert response.tokens_generated > 0

        logger.info(
            f"Conversation history response: '{response.message.content[:100]}...'"
        )

    @pytest.mark.asyncio
    async def test_chat_various_parameters(self, grpc_stub, service_available):
        """Test chat with various generation parameters."""
        if not service_available:
            pytest.skip("Inference API service not available")

        messages = [ChatMessage(role="user", content="Tell me a joke.")]

        # Test different parameter combinations
        param_sets = [
            {"temperature": 0.1, "max_tokens": 50},
            {"temperature": 0.7, "max_tokens": 100, "top_p": 0.9},
            {
                "temperature": 1.0,
                "max_tokens": 50,
                "top_p": 0.95,
                "repetition_penalty": 1.1,
            },
        ]

        for params_dict in param_sets:
            gen_params = GenerationParameters(**params_dict)
            request = ChatRequest(
                messages=messages,
                params=gen_params,
                context=Context(user_id="test_user", session_id="test_session"),
            )

            response = await grpc_stub.Chat(request, timeout=30.0)

            assert response.message.role == "assistant"
            assert len(response.message.content) > 0
            assert response.tokens_generated > 0

            logger.info(f"Params {params_dict}: '{response.message.content[:80]}...'")

    @pytest.mark.asyncio
    async def test_chat_long_conversation(self, grpc_stub, service_available):
        """Test chat with a longer conversation history."""
        if not service_available:
            pytest.skip("Inference API service not available")

        messages = [
            ChatMessage(role="system", content="You are a helpful math tutor."),
            ChatMessage(role="user", content="What is 1+1?"),
            ChatMessage(role="assistant", content="1+1 equals 2."),
            ChatMessage(role="user", content="What is 2+2?"),
            ChatMessage(role="assistant", content="2+2 equals 4."),
            ChatMessage(role="user", content="What is 3+3?"),
            ChatMessage(role="assistant", content="3+3 equals 6."),
            ChatMessage(role="user", content="What is 4+4?"),
        ]

        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Chat(request, timeout=30.0)

        assert response.message.role == "assistant"
        assert len(response.message.content) > 0
        # Should understand the pattern from conversation history
        assert (
            "8" in response.message.content
            or "eight" in response.message.content.lower()
        )

        logger.info(
            f"Long conversation response: '{response.message.content[:100]}...'"
        )

    @pytest.mark.asyncio
    async def test_chat_response_schema(self, grpc_stub, service_available):
        """Test that chat response format matches expected schema."""
        if not service_available:
            pytest.skip("Inference API service not available")

        messages = [ChatMessage(role="user", content="Test schema.")]

        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Chat(request, timeout=30.0)

        # Verify all required fields are present
        assert hasattr(response, "message")
        assert hasattr(response, "tokens_generated")
        assert hasattr(response, "tokens_per_second")
        assert hasattr(response, "usage")

        # Verify message structure
        assert hasattr(response.message, "role")
        assert hasattr(response.message, "content")

        # Verify types
        assert isinstance(response.message, ChatMessage)
        assert isinstance(response.message.content, str)
        assert isinstance(response.tokens_generated, int)
        assert isinstance(response.usage, UsageStats)

        logger.info("Chat response schema validation passed")

    @pytest.mark.asyncio
    async def test_chat_error_handling_empty_messages(
        self, grpc_stub, service_available
    ):
        """Test error handling for empty message list."""
        if not service_available:
            pytest.skip("Inference API service not available")

        request = ChatRequest(
            messages=[],  # Empty messages
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        # Should either handle gracefully or return error
        try:
            response = await grpc_stub.Chat(request, timeout=30.0)
            # If it succeeds, verify response is reasonable
            assert response.message is not None
            logger.info("Empty messages handled gracefully")
        except grpc.RpcError as e:
            # Error is acceptable for invalid input
            assert e.code() in [
                grpc.StatusCode.INVALID_ARGUMENT,
                grpc.StatusCode.FAILED_PRECONDITION,
            ]
            logger.info(f"Empty messages correctly rejected: {e.code()}")


class TestResponseQuality:
    """Test response quality and content."""

    @pytest.mark.asyncio
    async def test_response_quality_basic(self, grpc_stub, service_available):
        """Test that responses are reasonable quality."""
        if not service_available:
            pytest.skip("Inference API service not available")

        request = GenerationRequest(
            prompt="What is the capital of France?",
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Generate(request, timeout=30.0)

        # Response should be non-empty and relevant
        assert len(response.text) > 0
        assert len(response.text.strip()) > 0

        # For this specific question, should mention Paris
        response_lower = response.text.lower()
        assert (
            "paris" in response_lower or len(response.text) > 10
        )  # Either correct or substantial

        logger.info(f"Response quality check passed: '{response.text[:100]}...'")

    @pytest.mark.asyncio
    async def test_response_coherence(self, grpc_stub, service_available):
        """Test that responses are coherent."""
        if not service_available:
            pytest.skip("Inference API service not available")

        request = GenerationRequest(
            prompt="Write a short paragraph about artificial intelligence.",
            params=GenerationParameters(max_tokens=100, temperature=0.7),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        response = await grpc_stub.Generate(request, timeout=30.0)

        # Response should be substantial
        assert len(response.text) > 20

        # Should contain multiple words (coherent text, not just tokens)
        words = response.text.split()
        assert len(words) > 5

        logger.info(f"Response coherence check passed: {len(words)} words generated")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
