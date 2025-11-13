"""
TTS (Text-to-Speech) service command implementation.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from essence.command import Command

logger = logging.getLogger(__name__)


class TTSServiceCommand(Command):
    """Command for running the TTS service."""
    
    @classmethod
    def get_name(cls) -> str:
        return "tts"
    
    @classmethod
    def get_description(cls) -> str:
        return "Run the Text-to-Speech service"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("TTS_PORT", "50053")),
            help="gRPC service port (default: 50053)"
        )
        parser.add_argument(
            "--model",
            type=str,
            default=os.getenv("TTS_MODEL", "tts_models/en/ljspeech/tacotron2-DDC"),
            help="TTS model to use"
        )
    
    def init(self) -> None:
        """Initialize TTS service."""
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Import the service
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "tts"))
        from main import TTSService
        
        self.service = TTSService(port=self.args.port, model=self.args.model)
        logger.info("TTS service initialized")
    
    def run(self) -> None:
        """Run the TTS service."""
        self.service.run()
    
    def cleanup(self) -> None:
        """Clean up TTS service resources."""
        if hasattr(self.service, 'cleanup'):
            self.service.cleanup()
        logger.info("TTS service cleanup complete")

