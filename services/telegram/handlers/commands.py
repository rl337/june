"""Command handlers for Telegram bot."""
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """Handle /start command."""
    await update.message.reply_text(
        "?? Hello! I'm June, your voice assistant.\n\n"
        "Send me a voice message and I'll:\n"
        "1?? Transcribe it\n"
        "2?? Process it with AI\n"
        "3?? Send back a voice response\n\n"
        "Use /help for more information."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """Handle /help command."""
    await update.message.reply_text(
        "?? **June Voice Assistant Help**\n\n"
        "**Commands:**\n"
        "/start - Start interacting with June\n"
        "/help - Show this help message\n"
        "/status - Check service status\n\n"
        "**Usage:**\n"
        "Just send me a voice message (??) and I'll respond with a voice message!\n\n"
        "**Limits:**\n"
        f"? Maximum file size: {config.max_file_size / (1024 * 1024):.1f} MB\n"
        "? Maximum duration: ~1 minute"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """Handle /status command."""
    # TODO: Check service health
    await update.message.reply_text(
        "? **Service Status**\n\n"
        "?? Bot: Online\n"
        "?? STT: Checking...\n"
        "??? TTS: Checking...\n"
        "?? LLM: Checking...\n\n"
        "(Status checks will be implemented in next phase)"
    )
