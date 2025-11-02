from __future__ import annotations

import logging
import os
from typing import Dict, Any, Optional

from ..strategies import LlmStrategy, InferenceRequest, InferenceResponse
from ..config import config

logger = logging.getLogger(__name__)


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
    ) -> None:
        """Initialize Qwen3 LLM strategy.

        Args:
            model_name: HuggingFace model name (defaults to config.model.name)
            device: Device to run on (defaults to config.model.device)
            max_context_length: Maximum context length (defaults to config.model.max_context_length)
            use_yarn: Whether to use YaRN for long context (defaults to config.model.use_yarn)
            huggingface_token: HuggingFace token for private models (defaults to config.model.huggingface_token)
            model_cache_dir: Directory to cache models (defaults to config.model.model_cache_dir)
        """
        self.model_name = model_name or config.model.name
        self.device = device or config.model.device
        self.max_context_length = max_context_length or config.model.max_context_length
        self.use_yarn = use_yarn if use_yarn is not None else config.model.use_yarn
        self.huggingface_token = huggingface_token or config.model.huggingface_token
        self.model_cache_dir = model_cache_dir or config.model.model_cache_dir

        # Set HuggingFace cache directories if provided
        if config.model.huggingface_cache_dir:
            os.environ["HF_HOME"] = config.model.huggingface_cache_dir
        if config.model.transformers_cache_dir:
            os.environ["TRANSFORMERS_CACHE"] = config.model.transformers_cache_dir

        self._model = None
        self._tokenizer = None

    def warmup(self) -> None:
        """Load and initialize the Qwen3 model."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch

            logger.info(
                "Loading Qwen3 model: %s on device: %s",
                self.model_name,
                self.device,
            )

            # Set device for torch
            device_map = "auto" if self.device.startswith("cuda") else self.device

            # Load tokenizer
            logger.info("Loading tokenizer...")
            tokenizer_kwargs = {}
            if self.huggingface_token:
                tokenizer_kwargs["token"] = self.huggingface_token

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                cache_dir=self.model_cache_dir,
                trust_remote_code=True,
                **tokenizer_kwargs,
            )

            # Load model
            logger.info("Loading model (this may take a while)...")
            model_kwargs = {
                "cache_dir": self.model_cache_dir,
                "trust_remote_code": True,
                "torch_dtype": torch.float16 if self.device.startswith("cuda") else torch.float32,
            }
            if self.huggingface_token:
                model_kwargs["token"] = self.huggingface_token

            # Use device_map="auto" for CUDA to handle multi-GPU
            if self.device.startswith("cuda"):
                model_kwargs["device_map"] = "auto"
                model_kwargs["low_cpu_mem_usage"] = True
            else:
                # For CPU, we'll move the model after loading
                model_kwargs["device_map"] = None

            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                **model_kwargs,
            )

            # Move to device if not using device_map="auto"
            if not self.device.startswith("cuda") or "device_map" not in model_kwargs:
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

            # Generate
            with torch.no_grad():
                outputs = self._model.generate(
                    inputs.input_ids,
                    **generation_kwargs
                )

            # Decode output
            generated_text = self._tokenizer.decode(
                outputs[0], skip_special_tokens=True
            )

            # Remove the original prompt from the generated text if it's included
            if generated_text.startswith(prompt):
                generated_text = generated_text[len(prompt) :].strip()

            # Count tokens (approximate)
            input_tokens = len(inputs.input_ids[0])
            output_tokens = len(outputs[0]) - input_tokens

            return InferenceResponse(
                payload={"text": generated_text, "tokens": output_tokens},
                metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
            )

        except Exception as e:
            logger.error("Failed to generate text with Qwen3: %s", e, exc_info=True)
            raise RuntimeError(f"Generation failed: {e}") from e
