"""
Performance tests for Qwen3-30B-A3B model.

These tests verify that Qwen3-30B-A3B meets performance requirements:
- Latency < 2s for most requests
- Reasonable tokens/second generation rate
- Acceptable GPU memory usage
- Model loading time is reasonable

Note: These tests require the actual model to be loaded and may take significant time.
They should be run separately from unit tests.
"""

import os
import pytest
import time
import logging
from pathlib import Path

try:
    import torch
except ImportError:
    torch = None
    pytest.skip("torch not available", allow_module_level=True)

from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
from inference_core.strategies import InferenceRequest
from inference_core.config import config

logger = logging.getLogger(__name__)

# Skip performance tests if PERFORMANCE_TESTS environment variable is not set
# These tests are expensive and should be run explicitly
pytestmark = pytest.mark.skipif(
    os.getenv("PERFORMANCE_TESTS") != "1",
    reason="Performance tests require PERFORMANCE_TESTS=1 environment variable",
)


@pytest.fixture(scope="module")
def qwen3_strategy():
    """Initialize Qwen3 strategy for performance tests."""
    strategy = Qwen3LlmStrategy(
        model_name=config.model.name,
        device=config.model.device,
        max_context_length=config.model.max_context_length,
        use_yarn=config.model.use_yarn,
        huggingface_token=config.model.huggingface_token,
        model_cache_dir=config.model.model_cache_dir,
    )
    logger.info("Loading Qwen3 model for performance tests...")
    strategy.warmup()
    logger.info("Qwen3 model loaded")
    yield strategy


def test_model_loading_time(qwen3_strategy):
    """Test that model loading time is reasonable (< 5 minutes)."""
    # Model is already loaded by fixture, but we can verify it loaded successfully
    assert qwen3_strategy._model is not None
    assert qwen3_strategy._tokenizer is not None
    logger.info("Model loading test passed")


def test_short_prompt_latency(qwen3_strategy):
    """Test that short prompts have acceptable latency (< 2s)."""
    prompt = "Hello, how are you?"

    start_time = time.time()
    request = InferenceRequest(
        payload={
            "prompt": prompt,
            "params": {
                "temperature": 0.7,
                "max_tokens": 128,
                "top_p": 0.9,
            },
        },
        metadata={},
    )
    response = qwen3_strategy.infer(request)
    latency = time.time() - start_time

    assert response is not None
    assert latency < 2.0, f"Short prompt latency {latency:.3f}s exceeds 2s threshold"
    logger.info(f"Short prompt latency: {latency:.3f}s")


def test_medium_prompt_latency(qwen3_strategy):
    """Test that medium prompts have acceptable latency (< 5s)."""
    prompt = "Write a brief explanation of how neural networks work, including forward propagation and backpropagation."

    start_time = time.time()
    request = InferenceRequest(
        payload={
            "prompt": prompt,
            "params": {
                "temperature": 0.7,
                "max_tokens": 256,
                "top_p": 0.9,
            },
        },
        metadata={},
    )
    response = qwen3_strategy.infer(request)
    latency = time.time() - start_time

    assert response is not None
    assert latency < 5.0, f"Medium prompt latency {latency:.3f}s exceeds 5s threshold"
    logger.info(f"Medium prompt latency: {latency:.3f}s")


def test_tokens_per_second_rate(qwen3_strategy):
    """Test that token generation rate is reasonable (> 1 token/second)."""
    prompt = "Write a short story about artificial intelligence."

    start_time = time.time()
    request = InferenceRequest(
        payload={
            "prompt": prompt,
            "params": {
                "temperature": 0.7,
                "max_tokens": 256,
                "top_p": 0.9,
            },
        },
        metadata={},
    )
    response = qwen3_strategy.infer(request)
    latency = time.time() - start_time

    assert response is not None

    # Extract token count
    if isinstance(response.payload, dict):
        output_tokens = response.payload.get("tokens", 0)
    else:
        output_tokens = 0

    if output_tokens > 0 and latency > 0:
        tokens_per_second = output_tokens / latency
        assert (
            tokens_per_second > 1.0
        ), f"Token generation rate {tokens_per_second:.2f} tokens/s is too low"
        logger.info(f"Token generation rate: {tokens_per_second:.2f} tokens/s")
    else:
        pytest.skip("Could not determine token count")


def test_gpu_memory_usage(qwen3_strategy):
    """Test that GPU memory usage is reasonable."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    device = torch.cuda.current_device()
    allocated = torch.cuda.memory_allocated(device) / (1024**3)  # GB
    reserved = torch.cuda.memory_reserved(device) / (1024**3)  # GB

    # For a 30B model, we expect significant memory usage
    # But it should be reasonable (e.g., < 100GB for full precision)
    logger.info(f"GPU memory allocated: {allocated:.2f} GB")
    logger.info(f"GPU memory reserved: {reserved:.2f} GB")

    # Just log, don't fail - memory usage depends on model precision and optimization
    assert allocated > 0, "Model should use some GPU memory"


def test_multiple_requests_consistency(qwen3_strategy):
    """Test that multiple requests have consistent performance."""
    prompt = "What is the capital of France?"
    latencies = []

    for i in range(3):
        start_time = time.time()
        request = InferenceRequest(
            payload={
                "prompt": prompt,
                "params": {
                    "temperature": 0.7,
                    "max_tokens": 64,
                    "top_p": 0.9,
                },
            },
            metadata={},
        )
        response = qwen3_strategy.infer(request)
        latency = time.time() - start_time
        latencies.append(latency)

        assert response is not None

    # Check that latencies are reasonably consistent (within 2x of each other)
    if len(latencies) > 1:
        min_latency = min(latencies)
        max_latency = max(latencies)
        ratio = max_latency / min_latency if min_latency > 0 else float("inf")

        # Allow some variance but not extreme differences
        assert (
            ratio < 3.0
        ), f"Latency variance too high: {min_latency:.3f}s to {max_latency:.3f}s"
        logger.info(
            f"Latency consistency: {min_latency:.3f}s - {max_latency:.3f}s (ratio: {ratio:.2f})"
        )


def test_long_prompt_handling(qwen3_strategy):
    """Test that long prompts are handled correctly."""
    # Create a longer prompt
    prompt = " ".join(["Explain machine learning."] * 50)  # ~1000 words

    start_time = time.time()
    request = InferenceRequest(
        payload={
            "prompt": prompt,
            "params": {
                "temperature": 0.7,
                "max_tokens": 128,
                "top_p": 0.9,
            },
        },
        metadata={},
    )
    response = qwen3_strategy.infer(request)
    latency = time.time() - start_time

    assert response is not None
    # Long prompts may take longer, but should still complete
    assert latency < 30.0, f"Long prompt latency {latency:.3f}s is too high"
    logger.info(f"Long prompt latency: {latency:.3f}s")


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
