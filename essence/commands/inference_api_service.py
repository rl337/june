"""
Legacy Inference API service command implementation.

⚠️ **DEPRECATED:** This command is deprecated. The project has migrated to TensorRT-LLM
for optimized GPU inference. This service is kept for backward compatibility only.

**Current Implementation:** TensorRT-LLM (via Triton Inference Server in home_infra/shared-network)
**Legacy Implementation:** inference-api service (available via `--profile legacy`)

To use legacy inference-api:
- Set `LLM_URL=grpc://inference-api:50051` environment variable
- Start service with `docker compose --profile legacy up -d inference-api`

See: `docs/guides/TENSORRT_LLM_SETUP.md` for TensorRT-LLM setup and migration guide.
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from essence.command import Command

logger = logging.getLogger(__name__)


class InferenceAPIServiceCommand(Command):
    """
    Command for running the legacy Inference API service (DEPRECATED).
    
    ⚠️ **DEPRECATED:** This service is deprecated. Use TensorRT-LLM instead.
    
    Legacy gRPC service for LLM inference using Qwen3 models. This service is
    kept for backward compatibility only. All new deployments should use TensorRT-LLM
    (accessible via tensorrt-llm:8000 in home_infra/shared-network).
    
    The service manages model loading, GPU allocation, quantization, and inference
    orchestration. It was previously used by Telegram and Discord services, but these
    now default to TensorRT-LLM.
    """
    
    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.
        
        Returns:
            Command name: "inference-api"
        """
        return "inference-api"
    
    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.
        
        Returns:
            Description of what this command does
        """
        return "Run the legacy Inference API service (DEPRECATED - use TensorRT-LLM instead)"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.
        
        Configures gRPC service port and HTTP metrics port for the Inference API service.
        
        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("INFERENCE_API_PORT", "50051")),
            help="gRPC service port (default: 50051)"
        )
        parser.add_argument(
            "--metrics-port",
            type=int,
            default=int(os.getenv("INFERENCE_API_METRICS_PORT", "8001")),
            help="HTTP metrics port (default: 8001)"
        )
    
    def init(self) -> None:
        """
        Initialize Inference API service.
        
        Sets up signal handlers for graceful shutdown and imports the Inference API
        service's serve function. The service will be started when run() is called.
        Model loading happens during service startup.
        """
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Import the service
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "inference-api"))
        from main import serve
        
        self.serve_func = serve
        logger.info("Inference API service initialized")
    
    def run(self) -> None:
        """
        Run the Inference API service.
        
        Starts the gRPC server for LLM inference. This method blocks until the
        service is stopped (via signal handler). The service loads models on startup
        (if not already loaded) and processes inference requests using Qwen3 models.
        """
        # Inference API service uses async serve() function
        asyncio.run(self.serve_func())
    
    def cleanup(self) -> None:
        """
        Clean up Inference API service resources.
        
        Releases any resources held by the Inference API service, including
        model memory and GPU allocations. Actual cleanup is handled by the
        service's shutdown logic when signals are received.
        """
        logger.info("Inference API service cleanup complete")
