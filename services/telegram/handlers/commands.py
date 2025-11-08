"""Command handlers for Telegram bot."""
import logging
from telegram import Update
from telegram.ext import ContextTypes
import sys
from pathlib import Path

# Add parent directory to path to import language_preferences
sys.path.insert(0, str(Path(__file__).parent.parent))

from language_preferences import (
    get_language_preference,
    set_language_preference,
    get_supported_languages,
    is_language_supported,
    DEFAULT_LANGUAGE
)

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
        "/status - Check service status\n"
        "/language - Set language for voice messages\n\n"
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


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """Handle /language command."""
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    
    # Get command arguments
    args = context.args if context.args else []
    
    if not args:
        # Show current language and available languages
        current_lang = get_language_preference(user_id, chat_id)
        supported = get_supported_languages()
        
        # Format language list
        lang_list = "\n".join([
            f"  • {code}: {name}" + (" (current)" if code == current_lang else "")
            for code, name in sorted(supported.items())
        ])
        
        await update.message.reply_text(
            f"🌐 **Language Settings**\n\n"
            f"Current language: **{supported.get(current_lang, current_lang)}** ({current_lang})\n\n"
            f"**Available languages:**\n{lang_list}\n\n"
            f"To change language, use:\n`/language <code>`\n\n"
            f"Example: `/language es` for Spanish"
        )
    else:
        # Set language
        language_code = args[0].lower()
        
        if not is_language_supported(language_code):
            supported = get_supported_languages()
            lang_list = ", ".join([f"`{code}`" for code in sorted(supported.keys())])
            await update.message.reply_text(
                f"❌ Invalid language code: `{language_code}`\n\n"
                f"**Supported codes:** {lang_list}\n\n"
                f"Use `/language` to see all available languages."
            )
            return
        
        if set_language_preference(user_id, chat_id, language_code):
            lang_name = get_supported_languages()[language_code]
            await update.message.reply_text(
                f"✅ Language set to **{lang_name}** ({language_code})\n\n"
                f"Your voice messages will now be processed in {lang_name}.\n"
                f"Language detection is also enabled, so the system will automatically "
                f"detect the language if it differs from your preference."
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to set language. Please try again."
            )
