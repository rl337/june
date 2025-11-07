"""
Telegram Bot Service - Voice-to-Text-to-Voice integration.

Receives voice messages from Telegram users, transcribes them using STT,
processes through LLM, converts response to speech using TTS, and sends back.
"""
import logging
import os
import threading
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from inference_core import config, setup_logging
from handlers import start_command, help_command, status_command, handle_voice_message
from dependencies.config import (
    get_service_config,
    get_stt_address,
    get_metrics_storage
)

# Setup logging
setup_logging(config.monitoring.log_level, "telegram")
logger = logging.getLogger(__name__)


class TelegramBotService:
    """Telegram bot service for voice-to-text-to-voice processing."""
    
    def __init__(self):
        """Initialize the Telegram bot service."""
        self.config = get_service_config()
        self.stt_address = get_stt_address()
        
        if not self.config.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        
        # Initialize Telegram application
        self.application = Application.builder().token(self.config.bot_token).build()
        
        # Initialize health check server
        self.health_app = FastAPI()
        self._setup_health_endpoint()
        
        # Register handlers
        self._register_handlers()
    
    def _setup_health_endpoint(self):
        """Setup health check endpoint."""
        @self.health_app.get("/health")
        async def health_check():
            """Health check endpoint for Docker health checks."""
            return JSONResponse(
                content={
                    "status": "healthy",
                    "service": "telegram-bot"
                },
                status_code=200
            )
    
    def _register_handlers(self):
        """Register command and message handlers."""
        # Command handlers - wrap to pass config
        async def start_wrapper(update, context):
            await start_command(update, context, self.config)
        
        async def help_wrapper(update, context):
            await help_command(update, context, self.config)
        
        async def status_wrapper(update, context):
            await status_command(update, context, self.config)
        
        async def voice_wrapper(update, context):
            await handle_voice_message(
                update,
                context,
                self.config,
                self.stt_address,
                get_metrics_storage
            )
        
        self.application.add_handler(CommandHandler("start", start_wrapper))
        self.application.add_handler(CommandHandler("help", help_wrapper))
        self.application.add_handler(CommandHandler("status", status_wrapper))
        self.application.add_handler(MessageHandler(filters.VOICE, voice_wrapper))
    
    def _run_health_server(self):
        """Run health check HTTP server in a separate thread."""
        port = int(os.getenv("TELEGRAM_SERVICE_PORT", "8080"))
        logger.info(f"Starting health check server on port {port}")
        uvicorn.run(self.health_app, host="0.0.0.0", port=port, log_level="error")
    
    def run(self, use_webhook: bool = False, webhook_url: Optional[str] = None):
        """Run the Telegram bot (polling or webhook) and health check server."""
        # Start health check server in a separate thread
        health_thread = threading.Thread(target=self._run_health_server, daemon=True)
        health_thread.start()
        logger.info("Health check server started")
        
        # Run Telegram bot
        if use_webhook and webhook_url:
            logger.info(f"Starting bot in webhook mode: {webhook_url}")
            # TODO: Implement webhook setup
            self.application.run_webhook(
                webhook_url=webhook_url,
                port=int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8443"))
            )
        else:
            logger.info("Starting bot in polling mode")
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Main entry point."""
    try:
        service = TelegramBotService()
        use_webhook = os.getenv("TELEGRAM_USE_WEBHOOK", "false").lower() == "true"
        webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
        service.run(use_webhook=use_webhook, webhook_url=webhook_url)
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
