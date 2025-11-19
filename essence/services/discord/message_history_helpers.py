"""
Helper functions for tracking Discord message history.

Provides wrapper functions that intercept message sending and store
messages in history for debugging.
"""
import logging
from typing import Any, Dict, Optional

import discord

from essence.chat.message_history import get_message_history

logger = logging.getLogger(__name__)


async def send_with_history(
    channel: discord.TextChannel,
    content: str,
    user_id: Optional[str] = None,
    message_type: str = "text",
    rendering_metadata: Optional[Dict[str, Any]] = None,
    raw_text: Optional[str] = None,
) -> discord.Message:
    """
    Send a message to a Discord channel and track it in history.

    Args:
        channel: Discord TextChannel to send to
        content: Message content (formatted/rendered text)
        user_id: User ID (if available from context)
        message_type: Type of message ("text", "error", "status")
        rendering_metadata: Additional metadata about rendering
        raw_text: Raw text before formatting (if different from content)

    Returns:
        Sent Message object
    """
    message = await channel.send(content)

    # Store in history with enhanced metadata
    try:
        channel_id = str(channel.id) if channel else "unknown"
        message_id = str(message.id) if message else None

        # Try to get user_id from message if not provided
        if not user_id and message and message.author:
            user_id = str(message.author.id)

        if user_id:
            # Build comprehensive rendering metadata
            metadata = {
                "message_length": len(content),
                "discord_max_length": 2000,
                "within_limit": len(content) <= 2000,
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
                platform="discord",
                user_id=user_id,
                chat_id=channel_id,
                message_content=content,
                message_type=message_type,
                message_id=message_id,
                raw_text=raw_text or content,
                formatted_text=content,  # Discord uses markdown
                rendering_metadata=metadata,
            )
    except Exception as e:
        logger.warning(f"Failed to store message in history: {e}")

    return message


async def edit_with_history(
    message: discord.Message,
    content: str,
    user_id: Optional[str] = None,
    message_type: str = "text",
    rendering_metadata: Optional[Dict[str, Any]] = None,
    raw_text: Optional[str] = None,
) -> discord.Message:
    """
    Edit a Discord message and track it in history.

    Args:
        message: Discord Message object to edit
        content: New message content (formatted/rendered text)
        user_id: User ID (if not available from message)
        message_type: Type of message ("text", "error", "status")
        rendering_metadata: Additional metadata about rendering
        raw_text: Raw text before formatting (if different from content)

    Returns:
        Edited Message object
    """
    edited_message = await message.edit(content=content)

    # Store in history with enhanced metadata
    try:
        channel_id = str(message.channel.id) if message.channel else "unknown"
        message_id = str(edited_message.id) if edited_message else None

        # Try to get user_id from message if not provided
        if not user_id and message and message.author:
            user_id = str(message.author.id)

        if user_id:
            # Build comprehensive rendering metadata
            metadata = {
                "message_length": len(content),
                "discord_max_length": 2000,
                "within_limit": len(content) <= 2000,
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
                platform="discord",
                user_id=user_id,
                chat_id=channel_id,
                message_content=content,
                message_type=message_type,
                message_id=message_id,
                raw_text=raw_text or content,
                formatted_text=content,  # Discord uses markdown
                rendering_metadata=metadata,
            )
    except Exception as e:
        logger.warning(f"Failed to store edited message in history: {e}")

    return edited_message
