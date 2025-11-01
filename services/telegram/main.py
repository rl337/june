"""
Telegram Bot Service - Voice-to-Text-to-Voice integration.

Receives voice messages from Telegram users, transcribes them using STT,
processes through LLM, converts response to speech using TTS, and sends back.
"""
import asyncio
import logging
import os
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from inference_core import config, setup_logging
from june_grpc_api import asr as asr_shim, tts as tts_shim, llm as llm_shim

# Setup logging
setup_logging(config.monitoring.log_level, "telegram")
logger = logging.getLogger(__name__)


class TelegramBotService:
    """Telegram bot service for voice-to-text-to-voice processing."""
    
    def __init__(self):
        """Initialize the Telegram bot service."""
        self.config = config.telegram
        self.stt_address = os.getenv("STT_URL", "stt:50052").replace("grpc://", "")
        self.tts_address = os.getenv("TTS_URL", "tts:50053").replace("grpc://", "")
        self.llm_address = os.getenv("LLM_URL", "inference-api:50051").replace("grpc://", "")
        
        if not self.config.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        
        # Initialize Telegram application
        self.application = Application.builder().token(self.config.bot_token).build()
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register command and message handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # Voice message handler
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        await update.message.reply_text(
            "👋 Hello! I'm June, your voice assistant.\n\n"
            "Send me a voice message and I'll:\n"
            "1️⃣ Transcribe it\n"
            "2️⃣ Process it with AI\n"
            "3️⃣ Send back a voice response\n\n"
            "Use /help for more information."
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        await update.message.reply_text(
            "📖 **June Voice Assistant Help**\n\n"
            "**Commands:**\n"
            "/start - Start interacting with June\n"
            "/help - Show this help message\n"
            "/status - Check service status\n\n"
            "**Usage:**\n"
            "Just send me a voice message (🎤) and I'll respond with a voice message!\n\n"
            "**Limits:**\n"
            f"• Maximum file size: {self.config.max_file_size / (1024 * 1024):.1f} MB\n"
            "• Maximum duration: ~1 minute"
        )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        # TODO: Check service health
        await update.message.reply_text(
            "✅ **Service Status**\n\n"
            "🤖 Bot: Online\n"
            "🎤 STT: Checking...\n"
            "🗣️ TTS: Checking...\n"
            "🧠 LLM: Checking...\n\n"
            "(Status checks will be implemented in next phase)"
        )
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming voice messages."""
        voice = update.message.voice
        
        # Check file size
        if voice.file_size and voice.file_size > self.config.max_file_size:
            await update.message.reply_text(
                f"❌ Voice message too large. Maximum size: {self.config.max_file_size / (1024 * 1024):.1f} MB"
            )
            return
        
        # Send processing status
        status_msg = await update.message.reply_text("🔄 Processing your voice message...")
        
        try:
            # TODO: Implement full pipeline in next phases
            # 1. Download voice file
            # 2. Convert OGG to WAV
            # 3. Send to STT
            # 4. Send to LLM
            # 5. Send to TTS
            # 6. Convert to OGG
            # 7. Send response
            
            await status_msg.edit_text(
                "⚠️ Voice processing pipeline not yet implemented.\n\n"
                "This will be completed in Phase 2-4."
            )
        except Exception as e:
            logger.error(f"Error processing voice message: {e}", exc_info=True)
            await status_msg.edit_text(
                f"❌ Error processing voice message: {str(e)}\n\n"
                "Please try again later."
            )
    
    def run(self, use_webhook: bool = False, webhook_url: Optional[str] = None):
        """Run the Telegram bot (polling or webhook)."""
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

