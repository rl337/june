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
    """
    Command for running the TTS (Text-to-Speech) service.

    Provides gRPC service for converting text to speech audio using TTS models
    (FastSpeech2/espeak). Receives text via gRPC, synthesizes speech audio,
    and returns audio data.

    The service is used by Telegram and Discord services to convert LLM-generated
    text responses into voice messages for users.
    """

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "tts"
        """
        return "tts"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Run the Text-to-Speech service"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures gRPC service port and TTS model selection.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("TTS_PORT", "50053")),
            help="gRPC service port (default: 50053)",
        )
        parser.add_argument(
            "--model",
            type=str,
            default=os.getenv("TTS_MODEL", "tts_models/en/ljspeech/tacotron2-DDC"),
            help="TTS model to use",
        )

    def init(self) -> None:
        """
        Initialize TTS service.

        Sets up signal handlers for graceful shutdown. The service will be started when run() is called.
        """
        # Setup signal handlers
        self.setup_signal_handlers()
        logger.info("TTS service initialized")

    def run(self) -> None:
        """
        Run the TTS service.

        Starts the gRPC server for text-to-speech conversion. This method blocks
        until the service is stopped (via signal handler). The service listens
        for text synthesis requests and processes them using TTS models.
        """
        # Import and run the TTS service main function
        # The main.py is in /app/services/tts/main.py in the container
        tts_main_path = Path(__file__).parent.parent.parent / "services" / "tts" / "main.py"
        sys.path.insert(0, str(tts_main_path.parent))
        import importlib.util
        spec = importlib.util.spec_from_file_location("tts_main", str(tts_main_path))
        tts_main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tts_main)
        
        # Run the TTS service
        tts_main.main()

    def cleanup(self) -> None:
        """
        Clean up TTS service resources.

        Releases any resources held by the TTS service, including model memory
        and gRPC connections. Calls the service's cleanup method if available.
        """
        if hasattr(self.service, "cleanup"):
            self.service.cleanup()
        logger.info("TTS service cleanup complete")
