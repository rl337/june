"""
Helper functions for tracking Telegram message history.

Provides wrapper functions that intercept message sending and store
messages in history for debugging.
"""
import logging
from typing import Optional, Dict, Any
from telegram import Update, Message
from telegram.ext import ContextTypes

from essence.chat.message_history import get_message_history

logger = logging.getLogger(__name__)


async def reply_text_with_history(
    update: Update,
    text: str,
    parse_mode: Optional[str] = None,
    message_type: str = "text",
    rendering_metadata: Optional[Dict[str, Any]] = None,
    raw_text: Optional[str] = None,
) -> Message:
    """
    Send a reply text message and track it in history.

    Args:
        update: Telegram update object
        text: Message text to send (formatted/rendered text)
        parse_mode: Parse mode (e.g., "HTML", "Markdown")
        message_type: Type of message ("text", "error", "status")
        rendering_metadata: Additional metadata about rendering
        raw_text: Raw text before formatting (if different from text)

    Returns:
        Sent Message object
    """
    message = await update.message.reply_text(text, parse_mode=parse_mode)

    # Store in history with enhanced metadata
    try:
        user_id = str(update.effective_user.id) if update.effective_user else "unknown"
        chat_id = str(update.effective_chat.id) if update.effective_chat else "unknown"
        message_id = str(message.message_id) if message else None

        # Build comprehensive rendering metadata
        metadata = {
            "parse_mode": parse_mode,
            "message_length": len(text),
            "telegram_max_length": 4096,
            "within_limit": len(text) <= 4096,
            **(rendering_metadata or {}),
        }

        # Add split/truncation info if present in rendering_metadata
        if rendering_metadata:
            if "part" in rendering_metadata and "total_parts" in rendering_metadata:
                metadata["is_split"] = rendering_metadata["total_parts"] > 1
                metadata["part_number"] = rendering_metadata["part"]
                metadata["total_parts"] = rendering_metadata["total_parts"]
            if "truncated" in rendering_metadata:
                metadata["was_truncated"] = True

        get_message_history().add_message(
            platform="telegram",
            user_id=user_id,
            chat_id=chat_id,
            message_content=text,
            message_type=message_type,
            message_id=message_id,
            raw_text=raw_text or text,
            formatted_text=text if parse_mode else None,
            rendering_metadata=metadata,
        )
    except Exception as e:
        logger.warning(f"Failed to store message in history: {e}")

    return message


async def edit_text_with_history(
    message: Message,
    text: str,
    parse_mode: Optional[str] = None,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    message_type: str = "text",
    rendering_metadata: Optional[Dict[str, Any]] = None,
    raw_text: Optional[str] = None,
) -> Message:
    """
    Edit a message text and track it in history.

    Args:
        message: Telegram Message object to edit
        text: New message text (formatted/rendered text)
        parse_mode: Parse mode (e.g., "HTML", "Markdown")
        user_id: User ID (if not available from message)
        chat_id: Chat ID (if not available from message)
        message_type: Type of message ("text", "error", "status")
        rendering_metadata: Additional metadata about rendering
        raw_text: Raw text before formatting (if different from text)

    Returns:
        Edited Message object
    """
    edited_message = await message.edit_text(text, parse_mode=parse_mode)

    # Store in history with enhanced metadata
    try:
        if not user_id and message.chat:
            user_id = str(
                message.chat.id
            )  # Fallback to chat_id if user_id not available
        if not chat_id and message.chat:
            chat_id = str(message.chat.id)

        if user_id and chat_id:
            message_id = str(edited_message.message_id) if edited_message else None

            # Build comprehensive rendering metadata
            metadata = {
                "parse_mode": parse_mode,
                "message_length": len(text),
                "telegram_max_length": 4096,
                "within_limit": len(text) <= 4096,
                "is_edit": True,
                **(rendering_metadata or {}),
            }

            # Add split/truncation info if present in rendering_metadata
            if rendering_metadata:
                if "part" in rendering_metadata and "total_parts" in rendering_metadata:
                    metadata["is_split"] = rendering_metadata["total_parts"] > 1
                    metadata["part_number"] = rendering_metadata["part"]
                    metadata["total_parts"] = rendering_metadata["total_parts"]
                if "truncated" in rendering_metadata:
                    metadata["was_truncated"] = True
                if "fallback" in rendering_metadata:
                    metadata["was_fallback"] = rendering_metadata["fallback"]

            get_message_history().add_message(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                message_content=text,
                message_type=message_type,
                message_id=message_id,
                raw_text=raw_text or text,
                formatted_text=text if parse_mode else None,
                rendering_metadata=metadata,
            )
    except Exception as e:
        logger.warning(f"Failed to store edited message in history: {e}")

    return edited_message


async def send_voice_with_history(
    update: Update,
    voice_path: str,
    caption: Optional[str] = None,
    message_type: str = "voice",
    rendering_metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """
    Send a voice message and track it in history.

    Args:
        update: Telegram update object
        voice_path: Path to voice file
        caption: Optional caption text
        message_type: Type of message (default: "voice")
        rendering_metadata: Additional metadata about rendering

    Returns:
        Sent Message object
    """
    with open(voice_path, "rb") as voice_file:
        message = await update.message.reply_voice(voice=voice_file, caption=caption)

    # Store in history
    try:
        user_id = str(update.effective_user.id) if update.effective_user else "unknown"
        chat_id = str(update.effective_chat.id) if update.effective_chat else "unknown"
        message_id = str(message.message_id) if message else None

        content = f"[Voice message]" + (f" - {caption}" if caption else "")

        get_message_history().add_message(
            platform="telegram",
            user_id=user_id,
            chat_id=chat_id,
            message_content=content,
            message_type=message_type,
            message_id=message_id,
            raw_text=caption,
            rendering_metadata={
                **(rendering_metadata or {}),
                "voice_file": voice_path,
                "has_caption": caption is not None,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to store voice message in history: {e}")

    return message
