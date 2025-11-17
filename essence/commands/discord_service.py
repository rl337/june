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
    """Command for running the Discord bot service."""
    
    @classmethod
    def get_name(cls) -> str:
        return "discord-service"
    
    @classmethod
    def get_description(cls) -> str:
        return "Run the Discord bot service"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("DISCORD_SERVICE_PORT", "8081")),
            help="Health check HTTP port (default: 8081)"
        )
    
    def init(self) -> None:
        """Initialize Discord service."""
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
        """Run the Discord service."""
        asyncio.run(self.service.run())
    
    def cleanup(self) -> None:
        """Clean up Discord service resources."""
        logger.info("Discord service cleanup complete")

