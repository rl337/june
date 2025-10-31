"""Tests for LLM strategies."""
import pytest

from inference_core.llm.passthrough_strategy import PassthroughLlmStrategy
from inference_core.strategies import InferenceRequest, InferenceResponse


def test_passthrough_llm_strategy_warmup():
    """Test PassthroughLlmStrategy warmup succeeds."""
    strategy = PassthroughLlmStrategy()
    strategy.warmup()  # Should not raise


def test_passthrough_llm_strategy_infer_with_string_payload():
    """Test PassthroughLlmStrategy.infer handles string in payload."""
    strategy = PassthroughLlmStrategy()
    strategy.warmup()
    
    request = InferenceRequest(payload="hello", metadata={})
    result = strategy.infer(request)
    
    assert isinstance(result, InferenceResponse)
    assert isinstance(result.payload, dict)
    assert result.payload.get("text") == "[passthrough] hello"
    assert result.payload.get("tokens") is None


def test_passthrough_llm_strategy_infer_with_request():
    """Test PassthroughLlmStrategy.infer accepts InferenceRequest."""
    strategy = PassthroughLlmStrategy()
    strategy.warmup()
    
    request = InferenceRequest(
        payload={"prompt": "hello", "params": {"max_tokens": 100}},
        metadata={}
    )
    result = strategy.infer(request)
    
    assert isinstance(result, InferenceResponse)
    assert result.payload.get("text") == "[passthrough] hello"


def test_passthrough_llm_strategy_infer_with_dict():
    """Test PassthroughLlmStrategy.infer accepts dict directly."""
    strategy = PassthroughLlmStrategy()
    strategy.warmup()
    
    result = strategy.infer({"prompt": "test", "params": {}})
    
    assert isinstance(result, InferenceResponse)
    assert result.payload.get("text") == "[passthrough] test"


def test_passthrough_llm_strategy_infer_handles_empty_prompt():
    """Test PassthroughLlmStrategy handles empty prompt."""
    strategy = PassthroughLlmStrategy()
    strategy.warmup()
    
    request = InferenceRequest(payload={"prompt": "", "params": {}}, metadata={})
    result = strategy.infer(request)
    
    assert result.payload.get("text") == "[passthrough] "


def test_passthrough_llm_strategy_infer_preserves_params():
    """Test PassthroughLlmStrategy preserves params in request."""
    strategy = PassthroughLlmStrategy()
    strategy.warmup()
    
    request = InferenceRequest(
        payload={"prompt": "hello", "params": {"max_tokens": 200, "temperature": 0.8}},
        metadata={}
    )
    result = strategy.infer(request)
    
    # Params are stored but not used in passthrough (just logged)
    assert result.payload.get("text") == "[passthrough] hello"

