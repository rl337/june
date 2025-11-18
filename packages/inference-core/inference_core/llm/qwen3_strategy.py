from __future__ import annotations

import logging
import os
import time
from typing import Dict, Any, Optional
from contextlib import contextmanager

from ..strategies import LlmStrategy, InferenceRequest, InferenceResponse
from ..config import config
from ..utils.inference_cache import get_llm_cache

logger = logging.getLogger(__name__)


class TimeoutError(Exception):
    """Raised when inference exceeds timeout."""
    pass


@contextmanager
def timeout_context(seconds: float):
    """Context manager for timeout handling.
    
    Note: This is a best-effort timeout. For true interruption, 
    use async/await with asyncio.wait_for or threading-based timeout.
    This implementation checks elapsed time and raises if exceeded.
    """
    start_time = time.time()
    yield
    elapsed = time.time() - start_time
    if elapsed > seconds:
        raise TimeoutError(f"Operation timed out after {seconds} seconds (actual: {elapsed:.2f}s)")


class Qwen3LlmStrategy(LlmStrategy):
    """LLM strategy for Qwen3-30B-A3B model using transformers."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        max_context_length: Optional[int] = None,
        use_yarn: Optional[bool] = None,
        huggingface_token: Optional[str] = None,
        model_cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        use_quantization: Optional[bool] = None,
        quantization_bits: Optional[int] = None,  # 4 or 8 bits
        use_kv_cache: Optional[bool] = None,
    ) -> None:
        """Initialize Qwen3 LLM strategy.

        Args:
            model_name: HuggingFace model name (defaults to config.model.name)
            device: Device to run on (defaults to config.model.device)
            max_context_length: Maximum context length (defaults to config.model.max_context_length)
            use_yarn: Whether to use YaRN for long context (defaults to config.model.use_yarn)
            huggingface_token: HuggingFace token for private models (defaults to config.model.huggingface_token)
            model_cache_dir: Directory to cache models (defaults to config.model.model_cache_dir)
            local_files_only: If True, only load from local cache (defaults to False)
            use_quantization: Whether to use quantization (defaults to True for CUDA)
            quantization_bits: Number of bits for quantization (4 or 8, defaults to 8 for better compatibility)
            use_kv_cache: Whether to use KV cache for faster inference (defaults to True)
        """
        self.model_name = model_name or config.model.name
        self.device = device or config.model.device
        self.max_context_length = max_context_length or config.model.max_context_length
        self.use_yarn = use_yarn if use_yarn is not None else config.model.use_yarn
        self.huggingface_token = huggingface_token or config.model.huggingface_token
        self.model_cache_dir = model_cache_dir or config.model.model_cache_dir
        self.local_files_only = local_files_only if local_files_only is not None else False
        
        # GPU optimization settings
        # Default to quantization for CUDA devices (reduces memory usage significantly)
        if use_quantization is None:
            self.use_quantization = self.device.startswith("cuda")
        else:
            self.use_quantization = use_quantization
        
        # Default to 8-bit quantization (supports CPU offloading if needed, more compatible)
        # 4-bit is more memory efficient but doesn't support CPU offloading
        if quantization_bits is None:
            self.quantization_bits = 8 if self.use_quantization else None
        else:
            self.quantization_bits = quantization_bits if self.use_quantization else None
        
        # Default to KV cache for faster inference
        if use_kv_cache is None:
            self.use_kv_cache = True
        else:
            self.use_kv_cache = use_kv_cache

        # Set HuggingFace cache directories if provided
        if config.model.huggingface_cache_dir:
            os.environ["HF_HOME"] = config.model.huggingface_cache_dir
        if config.model.transformers_cache_dir:
            os.environ["TRANSFORMERS_CACHE"] = config.model.transformers_cache_dir

        self._model = None
        self._tokenizer = None
        self._past_key_values = None  # For KV cache
        
        # Initialize inference cache (can be disabled via environment variable)
        cache_enabled = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
        cache_max_size = int(os.getenv("LLM_CACHE_MAX_SIZE", "1000"))
        cache_ttl = float(os.getenv("LLM_CACHE_TTL_SECONDS", "3600"))  # 1 hour default
        self._cache = get_llm_cache(max_size=cache_max_size, ttl_seconds=cache_ttl if cache_enabled else None)
        if not cache_enabled:
            self._cache.enable_cache = False

    def warmup(self) -> None:
        """Load and initialize the Qwen3 model."""
        # Check if model is already loaded
        if self._model is not None and self._tokenizer is not None:
            logger.info(
                "Qwen3 model already loaded: %s on device: %s. Skipping reload.",
                self.model_name,
                self.device,
            )
            return
        
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(
                "Loading Qwen3 model: %s on device: %s",
                self.model_name,
                self.device,
            )

            # Check GPU compatibility early - before attempting any GPU operations
            # Some GPUs (e.g., NVIDIA GB10 with sm_121) may not be supported by PyTorch
            gpu_compatible = False
            if self.device.startswith("cuda") and torch.cuda.is_available():
                try:
                    device_capability = torch.cuda.get_device_capability(0)
                    device_name = torch.cuda.get_device_name(0)
                    logger.info(f"GPU detected: {device_name} with compute capability {device_capability}")
                    
                    # PyTorch 2.5.1 supports: sm_50, sm_80, sm_86, sm_89, sm_90, sm_90a
                    # If GPU has compute capability >= 12 (e.g., sm_121), it's not supported
                    if device_capability[0] >= 12:
                        logger.warning(
                            f"GPU compute capability {device_capability} is not supported by PyTorch 2.5.1. "
                            "PyTorch supports up to sm_90a. Falling back to CPU."
                        )
                        self.device = "cpu"
                        gpu_compatible = False
                    else:
                        # Test if we can actually use the GPU
                        try:
                            test_tensor = torch.zeros(10, device=self.device)
                            test_result = test_tensor.sum().item()
                            del test_tensor
                            torch.cuda.empty_cache()
                            if test_result == 0:
                                gpu_compatible = True
                                logger.info("GPU compatibility test passed")
                            else:
                                logger.warning("GPU tensor test failed, falling back to CPU")
                                self.device = "cpu"
                                gpu_compatible = False
                        except RuntimeError as e:
                            error_msg = str(e).lower()
                            if "no kernel image" in error_msg or "cuda" in error_msg or "kernel" in error_msg:
                                logger.warning(f"GPU not compatible: {e}. Falling back to CPU.")
                                self.device = "cpu"
                                gpu_compatible = False
                            else:
                                raise
                except Exception as e:
                    logger.warning(f"Error checking GPU compatibility: {e}. Falling back to CPU.")
                    self.device = "cpu"
                    gpu_compatible = False
            elif not self.device.startswith("cuda"):
                gpu_compatible = False
            else:
                gpu_compatible = False

            # Set device for torch based on compatibility check
            device_map = "auto" if (self.device.startswith("cuda") and gpu_compatible) else self.device

            # Load tokenizer
            logger.info("Loading tokenizer...")
            tokenizer_kwargs = {
                "local_files_only": self.local_files_only,
            }
            if self.huggingface_token:
                tokenizer_kwargs["token"] = self.huggingface_token

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                cache_dir=self.model_cache_dir,
                trust_remote_code=True,
                **tokenizer_kwargs,
            )

            # Load model with optional 4-bit quantization
            logger.info("Loading model (this may take a while)...")
            model_kwargs = {
                "cache_dir": self.model_cache_dir,
                "trust_remote_code": True,
                "local_files_only": self.local_files_only,
            }
            if self.huggingface_token:
                model_kwargs["token"] = self.huggingface_token

            # Apply quantization if enabled and GPU is compatible
            # Note: After compatibility check, self.device may have been changed to "cpu"
            if self.use_quantization and self.device.startswith("cuda") and gpu_compatible:
                try:
                    from transformers import BitsAndBytesConfig
                    
                    if self.quantization_bits == 4:
                        logger.info("Using 4-bit quantization for maximum memory efficiency")
                        quantization_config = BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_compute_dtype=torch.float16,
                            bnb_4bit_use_double_quant=True,
                            bnb_4bit_quant_type="nf4"  # NormalFloat4 for optimal performance
                        )
                        # 4-bit quantization doesn't support CPU/disk offloading
                        # Must fit entirely on GPU
                        model_kwargs["device_map"] = "cuda:0"
                        model_kwargs["low_cpu_mem_usage"] = True
                    elif self.quantization_bits == 8:
                        # GPU compatibility was already checked earlier
                        if gpu_compatible:
                            logger.info("Using 8-bit quantization (supports CPU offloading if needed)")
                            quantization_config = BitsAndBytesConfig(
                                load_in_8bit=True,
                                llm_int8_threshold=6.0,  # Threshold for outlier detection
                                llm_int8_enable_fp32_cpu_offload=True,  # Allow CPU offloading for FP32 layers
                            )
                            model_kwargs["quantization_config"] = quantization_config
                            model_kwargs["device_map"] = "auto"
                            logger.info("Using GPU with auto device_map for 8-bit quantization")
                        else:
                            # GPU not compatible or using CPU - disable quantization for CPU
                            logger.warning("GPU not compatible or using CPU. Disabling quantization for CPU inference.")
                            # Don't set quantization_config - model will load in full precision on CPU
                            model_kwargs["device_map"] = "cpu"
                            model_kwargs["torch_dtype"] = torch.float32  # Use float32 for CPU
                        model_kwargs["low_cpu_mem_usage"] = True
                    else:
                        raise ValueError(f"Unsupported quantization bits: {self.quantization_bits}. Use 4 or 8.")
                    
                    # Set torch_dtype based on device (float16 for GPU, float32 for CPU)
                    if not gpu_compatible or self.device == "cpu":
                        model_kwargs["torch_dtype"] = torch.float32
                    else:
                        model_kwargs["torch_dtype"] = torch.float16
                    
                    if torch.cuda.is_available() and gpu_compatible:
                        # Check available GPU memory
                        gpu_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                        logger.info(f"GPU memory available: {gpu_memory_gb:.2f} GB")
                    elif not gpu_compatible:
                        logger.info("Using CPU for model loading (GPU not compatible)")
                except ImportError:
                    logger.warning("bitsandbytes not available, falling back to standard loading")
                    model_kwargs["torch_dtype"] = torch.float16 if self.device.startswith("cuda") else torch.float32
                    if self.device.startswith("cuda"):
                        model_kwargs["device_map"] = "auto"
                        model_kwargs["low_cpu_mem_usage"] = True
                    else:
                        model_kwargs["device_map"] = None
            else:
                # Standard loading without quantization
                if gpu_compatible and self.device.startswith("cuda"):
                    model_kwargs["torch_dtype"] = torch.float16
                    model_kwargs["device_map"] = "auto"
                    model_kwargs["low_cpu_mem_usage"] = True
                else:
                    model_kwargs["torch_dtype"] = torch.float32
                    model_kwargs["device_map"] = "cpu" if not gpu_compatible else None
                    if not gpu_compatible:
                        logger.info("Using CPU for model loading (GPU not compatible, no quantization)")

            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                **model_kwargs,
            )

            # Move to device if not using device_map and not quantized
            # For quantized models with device_map, layers are already placed correctly
            if not self.use_quantization:
                if (not self.device.startswith("cuda") or model_kwargs.get("device_map") is None):
                    self._model = self._model.to(self.device)

            # Configure YaRN if enabled
            if self.use_yarn and self.max_context_length:
                logger.info(
                    "Configuring YaRN for context length: %d", self.max_context_length
                )
                # YaRN is typically configured through the model's config
                # The model should already support extended context if it's a YaRN-enabled model
                if hasattr(self._model.config, "rope_scaling"):
                    # Update rope_scaling if needed
                    logger.info("Model supports rope scaling for long context")

            # Set model to evaluation mode
            self._model.eval()

            # Log quantization status after loading
            if self.use_quantization and self.quantization_bits:
                # Verify quantization was actually applied
                quantization_applied = False
                if hasattr(self._model, 'hf_quantizer'):
                    quantization_applied = True
                elif hasattr(self._model, 'quantization_config'):
                    quant_config = self._model.quantization_config
                    if hasattr(quant_config, 'load_in_4bit') and quant_config.load_in_4bit:
                        quantization_applied = True
                    elif hasattr(quant_config, 'load_in_8bit') and quant_config.load_in_8bit:
                        quantization_applied = True
                elif hasattr(self._model, 'base_model') and hasattr(self._model.base_model, 'hf_quantizer'):
                    quantization_applied = True
                
                if quantization_applied:
                    logger.info(
                        "✅ Quantization successfully applied: %d-bit quantization active",
                        self.quantization_bits
                    )
                else:
                    logger.warning(
                        "⚠️  Quantization was configured (%d-bit) but may not be active. "
                        "Check model loading logs above for details.",
                        self.quantization_bits
                    )
            
            # Log memory usage if CUDA is available
            if torch.cuda.is_available() and gpu_compatible:
                try:
                    memory_allocated = torch.cuda.memory_allocated(0) / (1024**3)
                    memory_reserved = torch.cuda.memory_reserved(0) / (1024**3)
                    memory_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    logger.info(
                        "GPU Memory Usage: %.2f GB allocated / %.2f GB reserved / %.2f GB total",
                        memory_allocated, memory_reserved, memory_total
                    )
                except Exception as e:
                    logger.debug(f"Could not get GPU memory stats: {e}")

            logger.info("Qwen3 model loaded and initialized successfully")

        except ImportError as e:
            logger.error(
                "Failed to import transformers or torch. Install with: pip install transformers torch",
                exc_info=True,
            )
            raise RuntimeError(
                "transformers and torch are required for Qwen3 model. "
                "Install with: pip install transformers torch"
            ) from e
        except Exception as e:
            logger.error("Failed to load Qwen3 model: %s", e, exc_info=True)
            raise

    def infer(self, request: InferenceRequest | Dict[str, Any]) -> InferenceResponse:
        """Generate text using the Qwen3 model."""
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("Model not loaded. Call warmup() first.")

        try:
            import torch

            # Parse request
            if isinstance(request, dict):
                prompt = request.get("prompt", "")
                params = request.get("params", {})
            else:
                payload = request.payload
                if isinstance(payload, dict):
                    prompt = payload.get("prompt", "")
                    params = payload.get("params", {})
                else:
                    prompt = str(payload)
                    params = {}

            # Extract generation parameters
            temperature = params.get("temperature", 0.7)
            max_tokens = params.get("max_tokens", 2048)
            top_p = params.get("top_p", 0.9)
            top_k = params.get("top_k", None)
            repetition_penalty = params.get("repetition_penalty", None)

            # Check cache first (only for deterministic generation: temperature=0)
            cache_key = None
            if temperature == 0.0 and self._cache.enable_cache:
                cache_key = {
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "top_p": top_p,
                    "top_k": top_k,
                    "repetition_penalty": repetition_penalty,
                }
                cached_result = self._cache.get(cache_key, model_name=self.model_name)
                if cached_result is not None:
                    logger.debug("Cache hit for LLM inference")
                    return InferenceResponse(
                        payload={"text": cached_result["text"], "tokens": cached_result["tokens"]},
                        metadata={
                            "input_tokens": cached_result.get("input_tokens", 0),
                            "output_tokens": cached_result["tokens"],
                            "cached": True,
                        },
                    )

            # Tokenize input
            inputs = self._tokenizer(prompt, return_tensors="pt").to(self.device)

            # Prepare generation kwargs
            generation_kwargs = {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "do_sample": temperature > 0.0,
                "pad_token_id": self._tokenizer.eos_token_id,
            }
            
            # Add optional parameters if provided
            if top_k is not None and top_k > 0:
                generation_kwargs["top_k"] = int(top_k)
            
            if repetition_penalty is not None and repetition_penalty > 0:
                generation_kwargs["repetition_penalty"] = repetition_penalty

            # Enable KV cache for faster inference (reuses computed key-value pairs)
            if self.use_kv_cache:
                generation_kwargs["use_cache"] = True
                # If we have past_key_values from previous generation, use them
                if self._past_key_values is not None:
                    # Note: past_key_values usage requires careful handling of input_ids
                    # For now, we'll use use_cache=True which enables KV cache within a single generation
                    # Full past_key_values reuse would require tracking conversation state
                    pass

            # Measure inference performance
            inference_start_time = time.time()
            
            # Get timeout from config or request metadata (default: 300 seconds = 5 minutes)
            timeout_seconds = params.get("timeout", config.model.get("inference_timeout", 300) if hasattr(config.model, "get") else 300)
            if isinstance(request, InferenceRequest) and request.metadata:
                timeout_seconds = request.metadata.get("timeout_seconds", timeout_seconds)
            
            # Generate with timeout and OOM handling
            try:
                with torch.no_grad():
                    # Use timeout context if timeout is specified and reasonable
                    if timeout_seconds > 0 and timeout_seconds < 3600:  # Max 1 hour
                        with timeout_context(timeout_seconds):
                            outputs = self._model.generate(
                                inputs.input_ids,
                                **generation_kwargs
                            )
                    else:
                        outputs = self._model.generate(
                            inputs.input_ids,
                            **generation_kwargs
                        )
                    
                    # Store past_key_values for potential reuse in future calls
                    # Note: This requires the model to return past_key_values in outputs
                    # For now, we enable use_cache which improves performance within a single generation
            except TimeoutError as e:
                logger.error(f"Inference timeout after {timeout_seconds}s: {e}")
                # Clear CUDA cache if available
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                raise RuntimeError(f"Inference timed out after {timeout_seconds} seconds. Try reducing max_tokens or increasing timeout.") from e
            except RuntimeError as e:
                error_msg = str(e).lower()
                # Check for OOM errors
                if "out of memory" in error_msg or "cuda out of memory" in error_msg or "oom" in error_msg:
                    logger.error(f"Out of memory error during inference: {e}")
                    # Clear CUDA cache
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    raise RuntimeError(
                        f"Out of memory error during inference. "
                        f"Try reducing max_tokens (current: {max_tokens}), "
                        f"input length, or enable quantization."
                    ) from e
                # Re-raise other RuntimeErrors
                raise

            inference_end_time = time.time()
            inference_duration = inference_end_time - inference_start_time

            # Decode output
            decode_start_time = time.time()
            generated_text = self._tokenizer.decode(
                outputs[0], skip_special_tokens=True
            )
            decode_duration = time.time() - decode_start_time

            # Remove the original prompt from the generated text if it's included
            if generated_text.startswith(prompt):
                generated_text = generated_text[len(prompt) :].strip()

            # Count tokens (approximate)
            input_tokens = len(inputs.input_ids[0])
            output_tokens = len(outputs[0]) - input_tokens

            # Calculate performance metrics
            total_duration = inference_duration + decode_duration
            tokens_per_second = output_tokens / total_duration if total_duration > 0 else 0.0
            
            # Log performance metrics
            logger.info(
                "Qwen3 inference performance: %.2f tokens/s (%.2fs total, %d input tokens, %d output tokens, KV cache: %s)",
                tokens_per_second,
                total_duration,
                input_tokens,
                output_tokens,
                "enabled" if self.use_kv_cache and generation_kwargs.get("use_cache") else "disabled"
            )

            # Cache result if deterministic (temperature=0)
            if cache_key is not None and temperature == 0.0:
                self._cache.put(
                    cache_key,
                    {
                        "text": generated_text,
                        "tokens": output_tokens,
                        "input_tokens": input_tokens,
                    },
                    model_name=self.model_name,
                )

            return InferenceResponse(
                payload={"text": generated_text, "tokens": output_tokens},
                metadata={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cached": False,
                    "inference_duration_seconds": inference_duration,
                    "total_duration_seconds": total_duration,
                    "tokens_per_second": tokens_per_second,
                    "kv_cache_enabled": self.use_kv_cache and generation_kwargs.get("use_cache", False),
                },
            )

        except RuntimeError:
            # Re-raise RuntimeErrors (OOM, timeout) as-is
            raise
        except Exception as e:
            logger.error("Failed to generate text with Qwen3: %s", e, exc_info=True)
            # Clear CUDA cache on any error
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            raise RuntimeError(f"Generation failed: {e}") from e
