"""Command handlers for Telegram bot."""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from essence.services.telegram.conversation_storage import ConversationStorage
from essence.services.telegram.language_preferences import (
    get_supported_languages,
    is_language_supported,
    DEFAULT_LANGUAGE,
)

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """Handle /start command - welcome message explaining bot capabilities."""
    try:
        await update.message.reply_text(
            "👋 Hello! I'm June, your voice assistant.\n\n"
            "Send me a voice message and I'll:\n"
            "1️⃣ Transcribe it\n"
            "2️⃣ Process it with AI\n"
            "3️⃣ Send back a voice response\n\n"
            "Use /help for more information.",
            parse_mode="Markdown",
        )
        logger.info("Start command executed successfully")
    except Exception as e:
        logger.error(f"Failed to send start command response: {e}", exc_info=True)
        # Fallback: send without Markdown if parsing fails
        try:
            await update.message.reply_text(
                "👋 Hello! I'm June, your voice assistant.\n\n"
                "Send me a voice message and I'll:\n"
                "1️⃣ Transcribe it\n"
                "2️⃣ Process it with AI\n"
                "3️⃣ Send back a voice response\n\n"
                "Use /help for more information."
            )
        except Exception as fallback_error:
            logger.error(
                f"Failed to send fallback start message: {fallback_error}",
                exc_info=True,
            )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """Handle /help command - display help information with available commands and usage instructions."""
    try:
        await update.message.reply_text(
            "📖 **June Voice Assistant Help**\n\n"
            "**Commands:**\n"
            "/start - Start interacting with June\n"
            "/help - Show this help message\n"
            "/status - Check service status\n"
            "/language - Set language for voice messages\n\n"
            "**Usage:**\n"
            "Just send me a voice message (🎤) and I'll respond with a voice message!\n\n"
            "**Limits:**\n"
            f"📦 Maximum file size: {config.max_file_size / (1024 * 1024):.1f} MB\n"
            "⏱️ Maximum duration: ~1 minute",
            parse_mode="Markdown",
        )
        logger.info("Help command executed successfully")
    except Exception as e:
        logger.error(f"Failed to send help command response: {e}", exc_info=True)
        # Fallback: send without Markdown if parsing fails
        try:
            await update.message.reply_text(
                "📖 June Voice Assistant Help\n\n"
                "Commands:\n"
                "/start - Start interacting with June\n"
                "/help - Show this help message\n"
                "/status - Check service status\n"
                "/language - Set language for voice messages\n\n"
                "Usage:\n"
                "Just send me a voice message (🎤) and I'll respond with a voice message!\n\n"
                "Limits:\n"
                f"📦 Maximum file size: {config.max_file_size / (1024 * 1024):.1f} MB\n"
                "⏱️ Maximum duration: ~1 minute"
            )
        except Exception as fallback_error:
            logger.error(
                f"Failed to send fallback help message: {fallback_error}", exc_info=True
            )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """Handle /status command - check and display service health status."""
    import asyncio
    import grpc
    from dependencies.grpc_pool import get_grpc_pool
    from dependencies.config import get_stt_address, get_tts_address, get_llm_address

    logger.info("Status command received, checking service health...")

    # Initialize status message
    status_lines = ["🔍 **Service Status**\n"]
    status_lines.append("✅ Bot: Online\n")

    # Services to check
    services = {
        "STT": get_stt_address(),
        "TTS": get_tts_address(),
        "LLM": get_llm_address(),
    }

    pool = get_grpc_pool()

    # Check each service
    for service_name, address in services.items():
        try:
            # Check service connectivity with timeout
            async def check_service(service_name, pool):
                if service_name == "STT":
                    async with pool.get_stt_channel() as channel:
                        return channel.get_state()
                elif service_name == "TTS":
                    async with pool.get_tts_channel() as channel:
                        return channel.get_state()
                elif service_name == "LLM":
                    async with pool.get_llm_channel() as channel:
                        return channel.get_state()

            try:
                state = await asyncio.wait_for(
                    check_service(service_name, pool), timeout=3.0
                )
                if state == grpc.ChannelConnectivity.READY:
                    status_lines.append(f"✅ {service_name}: Online ({address})\n")
                    logger.info(f"Status check: {service_name} is online")
                else:
                    status_lines.append(
                        f"⚠️ {service_name}: Degraded ({address}) - State: {state}\n"
                    )
                    logger.warning(
                        f"Status check: {service_name} is degraded (state: {state})"
                    )
            except asyncio.TimeoutError:
                status_lines.append(f"❌ {service_name}: Timeout ({address})\n")
                logger.warning(f"Status check: {service_name} connection timeout")
            except grpc.aio.AioRpcError as e:
                status_lines.append(
                    f"❌ {service_name}: Error ({address}) - {e.code()}\n"
                )
                logger.error(
                    f"Status check: {service_name} gRPC error: {e.code()}",
                    exc_info=True,
                )
            except Exception as e:
                status_lines.append(
                    f"❌ {service_name}: Error ({address}) - {str(e)[:50]}\n"
                )
                logger.error(
                    f"Status check: {service_name} check failed: {e}", exc_info=True
                )
        except Exception as e:
            status_lines.append(f"❌ {service_name}: Unable to check - {str(e)[:50]}\n")
            logger.error(
                f"Status check: Failed to check {service_name}: {e}", exc_info=True
            )

    # Send status message
    status_message = "".join(status_lines)
    try:
        await update.message.reply_text(status_message, parse_mode="Markdown")
        logger.info("Status command completed successfully")
    except Exception as e:
        logger.error(f"Failed to send status message: {e}", exc_info=True)
        # Fallback: send without Markdown if parsing fails
        try:
            await update.message.reply_text(
                status_message.replace("**", "").replace("`", "")
            )
        except Exception as fallback_error:
            logger.error(
                f"Failed to send fallback status message: {fallback_error}",
                exc_info=True,
            )


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """Handle /language command."""
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)

    # Get command arguments
    args = context.args if context.args else []

    if not args:
        # Show current language and available languages
        current_lang = ConversationStorage.get_language_preference(user_id, chat_id)
        supported = get_supported_languages()

        # Format language list
        lang_list = "\n".join(
            [
                f"  • {code}: {name}" + (" (current)" if code == current_lang else "")
                for code, name in sorted(supported.items())
            ]
        )

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

        if ConversationStorage.set_language_preference(user_id, chat_id, language_code):
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
