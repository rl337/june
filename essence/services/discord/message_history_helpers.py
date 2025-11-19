"""
Helper functions for tracking Discord message history.

Provides wrapper functions that intercept message sending and store
messages in history for debugging.
"""
import logging
from typing import Optional, Dict, Any
import discord

from essence.chat.message_history import get_message_history

logger = logging.getLogger(__name__)


async def send_with_history(
    channel: discord.TextChannel,
    content: str,
    user_id: Optional[str] = None,
    message_type: str = "text",
    rendering_metadata: Optional[Dict[str, Any]] = None
) -> discord.Message:
    """
    Send a message to a Discord channel and track it in history.
    
    Args:
        channel: Discord TextChannel to send to
        content: Message content
        user_id: User ID (if available from context)
        message_type: Type of message ("text", "error", "status")
        rendering_metadata: Additional metadata about rendering
        
    Returns:
        Sent Message object
    """
    message = await channel.send(content)
    
    # Store in history
    try:
        channel_id = str(channel.id) if channel else "unknown"
        message_id = str(message.id) if message else None
        
        # Try to get user_id from message if not provided
        if not user_id and message and message.author:
            user_id = str(message.author.id)
        
        if user_id:
            get_message_history().add_message(
                platform="discord",
                user_id=user_id,
                chat_id=channel_id,
                message_content=content,
                message_type=message_type,
                message_id=message_id,
                raw_text=content,
                formatted_text=content,  # Discord uses markdown
                rendering_metadata=rendering_metadata or {}
            )
    except Exception as e:
        logger.warning(f"Failed to store message in history: {e}")
    
    return message


async def edit_with_history(
    message: discord.Message,
    content: str,
    user_id: Optional[str] = None,
    message_type: str = "text",
    rendering_metadata: Optional[Dict[str, Any]] = None
) -> discord.Message:
    """
    Edit a Discord message and track it in history.
    
    Args:
        message: Discord Message object to edit
        content: New message content
        user_id: User ID (if not available from message)
        message_type: Type of message ("text", "error", "status")
        rendering_metadata: Additional metadata about rendering
        
    Returns:
        Edited Message object
    """
    edited_message = await message.edit(content=content)
    
    # Store in history
    try:
        channel_id = str(message.channel.id) if message.channel else "unknown"
        message_id = str(edited_message.id) if edited_message else None
        
        # Try to get user_id from message if not provided
        if not user_id and message and message.author:
            user_id = str(message.author.id)
        
        if user_id:
            get_message_history().add_message(
                platform="discord",
                user_id=user_id,
                chat_id=channel_id,
                message_content=content,
                message_type=message_type,
                message_id=message_id,
                raw_text=content,
                formatted_text=content,  # Discord uses markdown
                rendering_metadata=rendering_metadata or {}
            )
    except Exception as e:
        logger.warning(f"Failed to store edited message in history: {e}")
    
    return edited_message
