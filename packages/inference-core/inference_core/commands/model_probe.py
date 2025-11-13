import logging
from typing import Optional

from ..cli import Command


logger = logging.getLogger(__name__)


class ModelProbe(Command):
    name = "model-probe"
    help = "Verify model loading using inference-core loaders (placeholder)."

    def __init__(self) -> None:
        self.model_name: Optional[str] = None

    def add_args(self, subparser):
        subparser.add_argument("--model", required=True, help="Model identifier to load")
        subparser.add_argument("--device", default="cpu", help="Device to target (cpu/cuda:0)")

    def initialize(self, args):
        self.model_name = args.model
        self.device = args.device

    def run(self, args) -> int:
        """Test model loading with the specified model and device."""
        logger.info("Model probe requested: name=%s device=%s", self.model_name, self.device)
        
        try:
            # Try to load Qwen3 model if model name suggests it's a Qwen model
            if "qwen" in self.model_name.lower():
                from ..llm.qwen3_strategy import Qwen3LlmStrategy
                
                logger.info("Loading Qwen3 model for testing...")
                strategy = Qwen3LlmStrategy(
                    model_name=self.model_name,
                    device=self.device
                )
                
                try:
                    strategy.warmup()
                    logger.info("? Model loaded successfully")
                    
                    # Test a simple inference
                    logger.info("Testing inference with sample prompt...")
                    test_request = {
                        "prompt": "Hello, world!",
                        "params": {"max_tokens": 10, "temperature": 0.7}
                    }
                    result = strategy.infer(test_request)
                    logger.info("? Inference successful: %s", result.payload.get("text", "")[:50])
                    
                    return 0
                except ImportError as e:
                    logger.error("Failed to import required dependencies: %s", e)
                    logger.error("Install with: pip install 'inference-core[llm]'")
                    return 1
                except Exception as e:
                    logger.error("Failed to load model: %s", e, exc_info=True)
                    return 1
            else:
                logger.warning("Model probe only supports Qwen models currently")
                logger.info("Model loader not yet implemented for: %s", self.model_name)
                return 0
        except Exception as e:
            logger.error("Model probe failed: %s", e, exc_info=True)
            return 1





