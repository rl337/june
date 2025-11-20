"""
Message API service command implementation.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from essence.command import Command

logger = logging.getLogger(__name__)


class MessageAPIServiceCommand(Command):
    """
    Command for running the Message API service.

    Provides REST API for programmatic access to message histories (GET/list)
    and sending/editing messages (POST/PUT/PATCH). This enables bi-directional
    communication between the agent and user via Telegram/Discord.
    """

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "message-api-service"
        """
        return "message-api-service"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Run the Message API service for bi-directional agent-user communication"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("MESSAGE_API_PORT", "8082")),
            help="Port to run the API service on (default: 8082 or MESSAGE_API_PORT env var)",
        )
        parser.add_argument(
            "--host",
            type=str,
            default=os.getenv("MESSAGE_API_HOST", "0.0.0.0"),
            help="Host to bind the API service to (default: 0.0.0.0 or MESSAGE_API_HOST env var)",
        )

    def init(self) -> None:
        """Initialize the command."""
        pass

    def run(self) -> None:
        """Run the Message API service."""
        from essence.services.message_api.main import main

        # Override environment variables with command-line arguments if provided
        if hasattr(self.args, "port") and self.args.port:
            os.environ["MESSAGE_API_PORT"] = str(self.args.port)
        if hasattr(self.args, "host") and self.args.host:
            os.environ["MESSAGE_API_HOST"] = self.args.host

        logger.info("Starting Message API service...")
        main()

    def cleanup(self) -> None:
        """Clean up resources."""
        pass
