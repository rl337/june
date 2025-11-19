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
    """
    Command for running the STT (Speech-to-Text) service.

    Provides gRPC service for converting audio/voice messages to text using
    Whisper models. Receives audio data via gRPC, performs speech recognition,
    and returns transcribed text.

    The service is used by Telegram and Discord services to convert voice
    messages into text for LLM processing.
    """

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "stt"
        """
        return "stt"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Run the Speech-to-Text service"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures gRPC service port and HTTP metrics port for the STT service.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("STT_PORT", "50052")),
            help="gRPC service port (default: 50052)",
        )
        parser.add_argument(
            "--metrics-port",
            type=int,
            default=int(os.getenv("STT_METRICS_PORT", "8002")),
            help="HTTP metrics port (default: 8002)",
        )

    def init(self) -> None:
        """
        Initialize STT service.

        Sets up signal handlers for graceful shutdown and imports the STT
        service's serve function. The service will be started when run() is called.
        """
        # Setup signal handlers
        self.setup_signal_handlers()

        # Import the service
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "services" / "stt")
        )
        from main import serve

        self.serve_func = serve
        logger.info("STT service initialized")

    def run(self) -> None:
        """
        Run the STT service.

        Starts the gRPC server for speech-to-text conversion. This method blocks
        until the service is stopped (via signal handler). The service listens
        for audio transcription requests and processes them using Whisper models.
        """
        # STT service uses async serve() function
        asyncio.run(self.serve_func())

    def cleanup(self) -> None:
        """
        Clean up STT service resources.

        Releases any resources held by the STT service. Actual cleanup
        is handled by the service's shutdown logic when signals are received.
        """
        logger.info("STT service cleanup complete")
