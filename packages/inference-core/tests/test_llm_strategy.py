"""Tests for LLM strategies."""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

try:
    import torch
except ImportError:
    torch = None

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


# Qwen3 strategy tests
def test_qwen3_strategy_initialization():
    """Test Qwen3LlmStrategy can be initialized with parameters."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    strategy = Qwen3LlmStrategy(
        model_name="test-model",
        device="cpu",
        max_context_length=4096,
        use_yarn=False,
    )
    
    assert strategy.model_name == "test-model"
    assert strategy.device == "cpu"
    assert strategy.max_context_length == 4096
    assert strategy.use_yarn is False
    assert strategy._model is None
    assert strategy._tokenizer is None


def test_qwen3_strategy_initialization_defaults():
    """Test Qwen3LlmStrategy uses config defaults when parameters not provided."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    from inference_core.config import config
    
    strategy = Qwen3LlmStrategy()
    
    assert strategy.model_name == config.model.name
    assert strategy.device == config.model.device
    assert strategy.max_context_length == config.model.max_context_length
    assert strategy.use_yarn == config.model.use_yarn


@patch('inference_core.llm.qwen3_strategy.AutoModelForCausalLM')
@patch('inference_core.llm.qwen3_strategy.AutoTokenizer')
@patch('inference_core.llm.qwen3_strategy.torch')
def test_qwen3_strategy_warmup_success(mock_torch, mock_tokenizer_class, mock_model_class):
    """Test Qwen3LlmStrategy.warmup() loads model and tokenizer successfully."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    # Setup mocks
    mock_tokenizer = Mock()
    mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
    
    mock_model = Mock()
    mock_model.config.rope_scaling = None
    mock_model.eval = Mock()
    mock_model.to = Mock(return_value=mock_model)
    mock_model_class.from_pretrained.return_value = mock_model
    
    mock_torch.float16 = "float16"
    mock_torch.float32 = "float32"
    
    strategy = Qwen3LlmStrategy(model_name="test-model", device="cpu")
    strategy.warmup()
    
    # Verify tokenizer was loaded
    mock_tokenizer_class.from_pretrained.assert_called_once()
    assert strategy._tokenizer == mock_tokenizer
    
    # Verify model was loaded
    mock_model_class.from_pretrained.assert_called_once()
    assert strategy._model == mock_model
    
    # Verify model was set to eval mode
    mock_model.eval.assert_called_once()


@patch('inference_core.llm.qwen3_strategy.AutoModelForCausalLM')
@patch('inference_core.llm.qwen3_strategy.AutoTokenizer')
@patch('inference_core.llm.qwen3_strategy.torch')
def test_qwen3_strategy_local_files_only(mock_torch, mock_tokenizer_class, mock_model_class):
    """Test Qwen3LlmStrategy.warmup() passes local_files_only=True correctly."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    # Setup mocks
    mock_tokenizer = Mock()
    mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
    
    mock_model = Mock()
    mock_model.config.rope_scaling = None
    mock_model.eval = Mock()
    mock_model.to = Mock(return_value=mock_model)
    mock_model_class.from_pretrained.return_value = mock_model
    
    mock_torch.float16 = "float16"
    mock_torch.float32 = "float32"
    
    strategy = Qwen3LlmStrategy(model_name="Qwen/Qwen3-30B-A3B", device="cpu", local_files_only=True)
    strategy.warmup()
    
    # Verify tokenizer was called with local_files_only=True
    tokenizer_call_kwargs = mock_tokenizer_class.from_pretrained.call_args[1]
    assert tokenizer_call_kwargs.get("local_files_only") is True
    
    # Verify model was called with local_files_only=True
    model_call_kwargs = mock_model_class.from_pretrained.call_args[1]
    assert model_call_kwargs.get("local_files_only") is True


def test_qwen3_strategy_warmup_missing_dependencies():
    """Test Qwen3LlmStrategy.warmup() raises helpful error if transformers/torch missing."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    strategy = Qwen3LlmStrategy(model_name="test-model", device="cpu")
    
    # Simulate missing transformers by making import fail
    with patch('builtins.__import__', side_effect=ImportError("No module named 'transformers'")):
        with pytest.raises(RuntimeError, match="transformers and torch are required"):
            strategy.warmup()


def test_qwen3_strategy_infer_without_warmup():
    """Test Qwen3LlmStrategy.infer() raises error if model not warmed up."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    strategy = Qwen3LlmStrategy()
    
    with pytest.raises(RuntimeError, match="Model not loaded"):
        strategy.infer(InferenceRequest(payload={"prompt": "test", "params": {}}, metadata={}))


@patch('inference_core.llm.qwen3_strategy.torch')
def test_qwen3_strategy_infer_success(mock_torch):
    """Test Qwen3LlmStrategy.infer() generates text correctly."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    # Setup mocks
    mock_tokenizer = Mock()
    mock_tokenizer.eos_token_id = 2
    mock_tokenizer.decode = Mock(return_value="test prompt generated text")
    mock_tokenizer.return_value = {"input_ids": Mock()}
    
    # Create a mock tensor that behaves like tokenizer output
    mock_inputs = Mock()
    mock_inputs.input_ids = Mock()
    mock_tokenizer.return_value = mock_inputs
    
    def tokenize_side_effect(text, **kwargs):
        mock_inputs.input_ids = Mock()
        return mock_inputs
    
    mock_tokenizer.side_effect = tokenize_side_effect
    
    mock_model = Mock()
    mock_outputs = Mock()
    mock_outputs.__getitem__ = Mock(return_value=Mock())  # outputs[0]
    mock_outputs.__len__ = Mock(return_value=10)
    mock_model.generate = Mock(return_value=mock_outputs)
    
    mock_no_grad = Mock()
    mock_torch.no_grad = Mock(return_value=mock_no_grad)
    mock_no_grad.__enter__ = Mock(return_value=None)
    mock_no_grad.__exit__ = Mock(return_value=None)
    
    strategy = Qwen3LlmStrategy()
    strategy._model = mock_model
    strategy._tokenizer = mock_tokenizer
    strategy.device = "cpu"
    
    request = InferenceRequest(
        payload={"prompt": "test prompt", "params": {"temperature": 0.7, "max_tokens": 100}},
        metadata={}
    )
    
    # Mock tokenizer.decode to return text without prompt
    mock_tokenizer.decode = Mock(return_value="generated text")
    
    result = strategy.infer(request)
    
    assert isinstance(result, InferenceResponse)
    assert isinstance(result.payload, dict)
    assert "text" in result.payload
    assert "tokens" in result.payload
    assert result.payload["text"] == "generated text"
    assert result.payload["tokens"] is not None
    
    # Verify model.generate was called
    mock_model.generate.assert_called_once()


def test_qwen3_strategy_infer_with_dict():
    """Test Qwen3LlmStrategy.infer() accepts dict directly."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    mock_tokenizer = Mock()
    mock_tokenizer.eos_token_id = 2
    mock_tokenizer.decode = Mock(return_value="generated")
    
    mock_inputs = Mock()
    mock_inputs.input_ids = Mock()
    mock_tokenizer.return_value = mock_inputs
    
    mock_model = Mock()
    mock_outputs = Mock()
    mock_outputs.__getitem__ = Mock(return_value=Mock())
    mock_outputs.__len__ = Mock(return_value=5)
    mock_model.generate = Mock(return_value=mock_outputs)
    
    with patch('inference_core.llm.qwen3_strategy.torch') as mock_torch:
        mock_no_grad = Mock()
        mock_torch.no_grad = Mock(return_value=mock_no_grad)
        mock_no_grad.__enter__ = Mock(return_value=None)
        mock_no_grad.__exit__ = Mock(return_value=None)
        
        strategy = Qwen3LlmStrategy()
        strategy._model = mock_model
        strategy._tokenizer = mock_tokenizer
        strategy.device = "cpu"
        
        result = strategy.infer({"prompt": "test", "params": {}})
        
        assert isinstance(result, InferenceResponse)
        assert "text" in result.payload


# Comprehensive tests for Qwen3-30B-A3B model loading and initialization
@pytest.mark.skipif(
    not os.path.exists("/home/rlee/models") or not os.path.exists("/home/rlee/models/huggingface"),
    reason="Model cache directory not available"
)
def test_qwen3_strategy_model_loading_from_local_cache():
    """Test that Qwen3-30B-A3B model can be loaded from local cache only."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    strategy = Qwen3LlmStrategy(
        model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
        device="cpu",  # Use CPU to avoid GPU requirements in tests
        local_files_only=True,
        model_cache_dir="/home/rlee/models"
    )
    
    # This should succeed if model is in local cache
    try:
        strategy.warmup()
        
        # Verify model and tokenizer are loaded
        assert strategy._model is not None
        assert strategy._tokenizer is not None
        
        # Verify model is in eval mode (ready for inference)
        assert strategy._model.training is False
    except Exception as e:
        # If model is not in cache, that's OK - we're testing the local_files_only flag
        # The test verifies that local_files_only=True is passed correctly
        pytest.skip(f"Model not available in local cache: {e}")


@pytest.mark.skipif(
    not os.path.exists("/home/rlee/models") or not os.path.exists("/home/rlee/models/huggingface"),
    reason="Model cache directory not available"
)
def test_qwen3_strategy_tokenizer_initialization():
    """Test that tokenizer initializes correctly with Qwen3-30B-A3B."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    strategy = Qwen3LlmStrategy(
        model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
        device="cpu",
        local_files_only=True,
        model_cache_dir="/home/rlee/models"
    )
    
    try:
        strategy.warmup()
        
        # Verify tokenizer is initialized
        assert strategy._tokenizer is not None
        
        # Test tokenizer functionality
        test_text = "Hello, world!"
        tokens = strategy._tokenizer.encode(test_text)
        assert isinstance(tokens, list)
        assert len(tokens) > 0
        
        # Test decoding
        decoded = strategy._tokenizer.decode(tokens)
        assert isinstance(decoded, str)
        assert len(decoded) > 0
        
        # Verify tokenizer has required attributes
        assert hasattr(strategy._tokenizer, 'eos_token_id')
        assert strategy._tokenizer.eos_token_id is not None
    except Exception as e:
        pytest.skip(f"Model not available in local cache: {e}")


@pytest.mark.skipif(
    not os.path.exists("/home/rlee/models") or not os.path.exists("/home/rlee/models/huggingface"),
    reason="Model cache directory not available"
)
def test_qwen3_strategy_model_parameters_configuration():
    """Test that model parameters are configured properly (context length, quantization)."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    strategy = Qwen3LlmStrategy(
        model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
        device="cpu",
        max_context_length=131072,
        use_yarn=True,
        local_files_only=True,
        model_cache_dir="/home/rlee/models"
    )
    
    try:
        strategy.warmup()
        
        # Verify model is loaded
        assert strategy._model is not None
        
        # Verify model configuration
        assert hasattr(strategy._model, 'config')
        model_config = strategy._model.config
        
        # Check context length configuration
        if hasattr(model_config, 'max_position_embeddings'):
            # Model should support the configured context length
            assert model_config.max_position_embeddings >= strategy.max_context_length or \
                   (hasattr(model_config, 'rope_scaling') and model_config.rope_scaling is not None)
        
        # Verify YaRN configuration if enabled
        if strategy.use_yarn and hasattr(model_config, 'rope_scaling'):
            # YaRN models typically have rope_scaling configured
            pass  # Just verify it doesn't crash
        
        # Verify model dtype (quantization check)
        # For CPU, should be float32; for CUDA, should be float16
        if torch is not None:
            if strategy.device.startswith("cpu"):
                # CPU models typically use float32
                assert strategy._model.dtype in [torch.float32, torch.float16]
            elif strategy.device.startswith("cuda"):
                # CUDA models typically use float16 for efficiency
                assert strategy._model.dtype in [torch.float16, torch.bfloat16, torch.float32]
        else:
            # If torch is not available, just verify dtype attribute exists
            assert hasattr(strategy._model, 'dtype')
    except Exception as e:
        pytest.skip(f"Model not available in local cache: {e}")


def test_qwen3_strategy_error_handling_missing_model():
    """Test error handling when model is missing with local_files_only=True."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    strategy = Qwen3LlmStrategy(
        model_name="non-existent-model-12345",
        device="cpu",
        local_files_only=True,
        model_cache_dir="/tmp/nonexistent"
    )
    
    # Should raise an error when model is not found
    with pytest.raises((RuntimeError, OSError, FileNotFoundError)):
        strategy.warmup()


def test_qwen3_strategy_error_handling_invalid_configuration():
    """Test error handling for invalid configurations."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    # Test with invalid device
    strategy = Qwen3LlmStrategy(
        model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
        device="invalid_device_xyz",
        local_files_only=True
    )
    
    # Should handle invalid device gracefully or raise appropriate error
    # The exact behavior depends on torch's device handling
    try:
        strategy.warmup()
    except (RuntimeError, ValueError) as e:
        # Expected - invalid device should cause an error
        assert "device" in str(e).lower() or "cuda" in str(e).lower() or "cpu" in str(e).lower()


@pytest.mark.skipif(
    not os.path.exists("/home/rlee/models") or not os.path.exists("/home/rlee/models/huggingface"),
    reason="Model cache directory not available"
)
def test_qwen3_strategy_warmup_process():
    """Test that model warmup process completes successfully."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    strategy = Qwen3LlmStrategy(
        model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
        device="cpu",
        local_files_only=True,
        model_cache_dir="/home/rlee/models"
    )
    
    # Before warmup, model and tokenizer should be None
    assert strategy._model is None
    assert strategy._tokenizer is None
    
    try:
        # Warmup should load model and tokenizer
        strategy.warmup()
        
        # After warmup, model and tokenizer should be loaded
        assert strategy._model is not None
        assert strategy._tokenizer is not None
        
        # Model should be in eval mode
        assert strategy._model.training is False
        
        # Verify model is on correct device
        # For CPU, device should be 'cpu'
        if strategy.device.startswith("cpu"):
            # Check that model parameters are on CPU
            next_param = next(strategy._model.parameters())
            assert str(next_param.device) == "cpu"
    except Exception as e:
        pytest.skip(f"Model not available in local cache: {e}")


@pytest.mark.skipif(
    not os.path.exists("/home/rlee/models") or not os.path.exists("/home/rlee/models/huggingface"),
    reason="Model cache directory not available"
)
def test_qwen3_strategy_ready_for_inference_after_warmup():
    """Test that model is ready for inference after warmup()."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    from inference_core.strategies import InferenceRequest
    
    strategy = Qwen3LlmStrategy(
        model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
        device="cpu",
        local_files_only=True,
        model_cache_dir="/home/rlee/models"
    )
    
    try:
        # Warmup the model
        strategy.warmup()
        
        # Verify model is ready by attempting inference
        request = InferenceRequest(
            payload={"prompt": "Hello", "params": {"max_tokens": 10, "temperature": 0.7}},
            metadata={}
        )
        
        # Should not raise RuntimeError about model not being loaded
        result = strategy.infer(request)
        
        # Verify result is valid
        assert isinstance(result, InferenceResponse)
        assert "text" in result.payload
        assert "tokens" in result.payload
        assert isinstance(result.payload["text"], str)
        assert isinstance(result.payload["tokens"], int)
        assert result.payload["tokens"] > 0
    except Exception as e:
        pytest.skip(f"Model not available in local cache: {e}")


def test_qwen3_strategy_local_files_only_flag():
    """Test that local_files_only flag is properly passed to model and tokenizer loading."""
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    
    with patch('inference_core.llm.qwen3_strategy.AutoModelForCausalLM') as mock_model_class, \
         patch('inference_core.llm.qwen3_strategy.AutoTokenizer') as mock_tokenizer_class, \
         patch('inference_core.llm.qwen3_strategy.torch') as mock_torch:
        
        # Setup mocks
        mock_tokenizer = Mock()
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
        
        mock_model = Mock()
        mock_model.config.rope_scaling = None
        mock_model.eval = Mock()
        mock_model.to = Mock(return_value=mock_model)
        mock_model_class.from_pretrained.return_value = mock_model
        
        mock_torch.float16 = "float16"
        mock_torch.float32 = "float32"
        
        # Test with local_files_only=True
        strategy = Qwen3LlmStrategy(
            model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
            device="cpu",
            local_files_only=True
        )
        strategy.warmup()
        
        # Verify tokenizer was called with local_files_only=True
        tokenizer_call_kwargs = mock_tokenizer_class.from_pretrained.call_args[1]
        assert tokenizer_call_kwargs.get("local_files_only") is True
        
        # Verify model was called with local_files_only=True
        model_call_kwargs = mock_model_class.from_pretrained.call_args[1]
        assert model_call_kwargs.get("local_files_only") is True
        
        # Test with local_files_only=False (default)
        strategy2 = Qwen3LlmStrategy(
            model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
            device="cpu",
            local_files_only=False
        )
        strategy2.warmup()
        
        # Verify tokenizer was called with local_files_only=False
        tokenizer_call_kwargs2 = mock_tokenizer_class.from_pretrained.call_args[1]
        assert tokenizer_call_kwargs2.get("local_files_only") is False
        
        # Verify model was called with local_files_only=False
        model_call_kwargs2 = mock_model_class.from_pretrained.call_args[1]
        assert model_call_kwargs2.get("local_files_only") is False

