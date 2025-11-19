"""
Discord service command implementation.
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from essence.command import Command

logger = logging.getLogger(__name__)


class DiscordServiceCommand(Command):
    """
    Command for running the Discord bot service.

    Orchestrates the Discord voice message processing pipeline:
    voice message → STT → LLM → TTS → voice response. Receives voice messages
    from Discord servers and processes them through the STT, inference API,
    and TTS services.

    The service integrates with Discord's voice channels and message system
    to provide voice-based AI interactions.
    """

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "discord-service"
        """
        return "discord-service"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Run the Discord bot service"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures the health check HTTP port for the Discord service.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("DISCORD_SERVICE_PORT", "8081")),
            help="Health check HTTP port (default: 8081)",
        )

    def init(self) -> None:
        """
        Initialize Discord service.

        Validates required environment variables (DISCORD_BOT_TOKEN), sets up
        signal handlers for graceful shutdown, and initializes the DiscordBotService.

        Raises:
            ValueError: If DISCORD_BOT_TOKEN environment variable is not set
        """
        # Validate required environment variables
        if not os.getenv("DISCORD_BOT_TOKEN"):
            raise ValueError("DISCORD_BOT_TOKEN environment variable is required")

        # Setup signal handlers
        self.setup_signal_handlers()

        # Import the service class from essence
        from essence.services.discord.main import DiscordBotService

        self.service = DiscordBotService()
        logger.info("Discord service initialized")

    def run(self) -> None:
        """
        Run the Discord service.

        Starts the Discord bot service and begins processing voice messages.
        This method blocks until the service is stopped (via signal handler).
        The service processes voice messages and orchestrates the STT → LLM → TTS pipeline.
        """
        asyncio.run(self.service.run())

    def cleanup(self) -> None:
        """
        Clean up Discord service resources.

        Releases any resources held by the Discord service. Actual cleanup
        is handled by the service's shutdown logic when signals are received.
        """
        logger.info("Discord service cleanup complete")
