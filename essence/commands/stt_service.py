"""
STT (Speech-to-Text) service command implementation.
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from essence.command import Command

logger = logging.getLogger(__name__)


class STTServiceCommand(Command):
    """Command for running the STT service."""
    
    @classmethod
    def get_name(cls) -> str:
        return "stt"
    
    @classmethod
    def get_description(cls) -> str:
        return "Run the Speech-to-Text service"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("STT_PORT", "50052")),
            help="gRPC service port (default: 50052)"
        )
        parser.add_argument(
            "--metrics-port",
            type=int,
            default=int(os.getenv("STT_METRICS_PORT", "8002")),
            help="HTTP metrics port (default: 8002)"
        )
    
    def init(self) -> None:
        """Initialize STT service."""
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Import the service
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "stt"))
        from main import serve
        
        self.serve_func = serve
        logger.info("STT service initialized")
    
    def run(self) -> None:
        """Run the STT service."""
        # STT service uses async serve() function
        asyncio.run(self.serve_func())
    
    def cleanup(self) -> None:
        """Clean up STT service resources."""
        logger.info("STT service cleanup complete")
