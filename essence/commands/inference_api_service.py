"""
Inference API service command implementation.
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
    Command for running the Inference API service.
    
    Provides gRPC service for LLM inference using Qwen3 models. Receives text
    prompts via gRPC, processes them through the language model, and returns
    generated text responses.
    
    The service manages model loading, GPU allocation, quantization, and inference
    orchestration. It is used by Telegram and Discord services to generate AI
    responses to user messages.
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
        return "Run the Inference API service (LLM orchestration)"
    
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
