"""
Telegram service command implementation.
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from essence.command import Command

logger = logging.getLogger(__name__)


class TelegramServiceCommand(Command):
    """
    Command for running the Telegram bot service.
    
    Orchestrates the Telegram voice message processing pipeline:
    voice message → STT → LLM → TTS → voice response. Supports both polling
    and webhook modes for receiving Telegram updates.
    
    The service receives voice messages from Telegram, processes them through
    the STT, inference API, and TTS services, then sends responses back to users.
    """
    
    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.
        
        Returns:
            Command name: "telegram-service"
        """
        return "telegram-service"
    
    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.
        
        Returns:
            Description of what this command does
        """
        return "Run the Telegram bot service"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.
        
        Configures service ports and webhook settings for Telegram bot operation.
        
        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("TELEGRAM_SERVICE_PORT", "8080")),
            help="Health check HTTP port (default: 8080)"
        )
        parser.add_argument(
            "--webhook-port",
            type=int,
            default=int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8443")),
            help="Webhook port (default: 8443)"
        )
        parser.add_argument(
            "--use-webhook",
            action="store_true",
            default=os.getenv("TELEGRAM_USE_WEBHOOK", "false").lower() == "true",
            help="Use webhook mode instead of polling"
        )
        parser.add_argument(
            "--webhook-url",
            type=str,
            default=os.getenv("TELEGRAM_WEBHOOK_URL", ""),
            help="Webhook URL (required if --use-webhook)"
        )
    
    def init(self) -> None:
        """
        Initialize Telegram service.
        
        Validates required environment variables (TELEGRAM_BOT_TOKEN), sets up
        signal handlers for graceful shutdown, and initializes the TelegramBotService.
        
        Raises:
            ValueError: If TELEGRAM_BOT_TOKEN environment variable is not set
        """
        # Validate required environment variables
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Import the service class from essence
        from essence.services.telegram.main import TelegramBotService
        
        self.service = TelegramBotService()
        logger.info("Telegram service initialized")
    
    def run(self) -> None:
        """
        Run the Telegram service.
        
        Starts the Telegram bot service in either polling or webhook mode.
        This method blocks until the service is stopped (via signal handler).
        The service processes voice messages and orchestrates the STT → LLM → TTS pipeline.
        """
        # Run the service (this will block)
        use_webhook = self.args.use_webhook
        webhook_url = self.args.webhook_url or os.getenv("TELEGRAM_WEBHOOK_URL")
        self.service.run(use_webhook=use_webhook, webhook_url=webhook_url)
    
    def cleanup(self) -> None:
        """
        Clean up Telegram service resources.
        
        Releases any resources held by the Telegram service. Actual cleanup
        is handled by the service's shutdown logic when signals are received.
        """
        # Service cleanup is handled by the service's shutdown logic
        logger.info("Telegram service cleanup complete")

