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
    """Command for running the Inference API service."""
    
    @classmethod
    def get_name(cls) -> str:
        return "inference-api"
    
    @classmethod
    def get_description(cls) -> str:
        return "Run the Inference API service (LLM orchestration)"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
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
        """Initialize Inference API service."""
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Import the service
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "inference-api"))
        from main import serve
        
        self.serve_func = serve
        logger.info("Inference API service initialized")
    
    def run(self) -> None:
        """Run the Inference API service."""
        # Inference API service uses async serve() function
        asyncio.run(self.serve_func())
    
    def cleanup(self) -> None:
        """Clean up Inference API service resources."""
        logger.info("Inference API service cleanup complete")
