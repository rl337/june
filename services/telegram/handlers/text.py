"""Text message handler for Telegram bot - uses TelegramResponse agent."""
import logging
import re
import time
import asyncio
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_response import call_telegram_response_agent, format_agent_response_for_telegram
from agent_handler import stream_agent_message
from conversation_storage import ConversationStorage

logger = logging.getLogger(__name__)


def extract_user_info(message: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract user name and favorite color from a message.
    
    Looks for patterns like:
    - "My name is X" or "I'm X" or "I am X"
    - "My favorite color is X" or "favorite color is X"
    - Handles combined statements like "My name is Bob and my favorite color is blue"
    
    Args:
        message: The user's message text
        
    Returns:
        Tuple of (name, favorite_color) - both can be None
    """
    name = None
    favorite_color = None
    
    # Normalize message for easier matching
    message_lower = message.lower()
    
    # Patterns for name extraction - capture word after "name is" or similar
    name_patterns = [
        r"my name is ([a-zA-Z]+)",
        r"i'?m ([a-zA-Z]+)",
        r"i am ([a-zA-Z]+)",
        r"name is ([a-zA-Z]+)",
        r"call me ([a-zA-Z]+)",
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            # Extract name, handling cases where it might be followed by "and"
            name_candidate = match.group(1).strip()
            # Check if there's more text after (like "and my favorite color")
            # The regex should stop at word boundaries, but let's be safe
            name = name_candidate.capitalize()
            break
    
    # Patterns for favorite color extraction
    color_patterns = [
        r"favorite color is ([a-zA-Z]+)",
        r"favourite color is ([a-zA-Z]+)",
        r"favorite colour is ([a-zA-Z]+)",
        r"favourite colour is ([a-zA-Z]+)",
        r"my favorite color is ([a-zA-Z]+)",
        r"my favourite color is ([a-zA-Z]+)",
    ]
    
    for pattern in color_patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            favorite_color = match.group(1).strip().lower()
            break
    
    return name, favorite_color


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """
    Handle text messages from Telegram users by calling the TelegramResponse agent.
    
    Args:
        update: Telegram update object
        context: Telegram context
        config: Service configuration
    """
    try:
        user_message = update.message.text
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Check if user is authorized (allow list)
        import os
        authorized_users_str = os.getenv("TELEGRAM_AUTHORIZED_USERS", "")
        if authorized_users_str:
            authorized_users = [int(uid.strip()) for uid in authorized_users_str.split(",") if uid.strip().isdigit()]
            if authorized_users and user_id not in authorized_users:
                logger.info(f"Ignoring message from unauthorized user {user_id}")
                # Silently ignore - don't send any response
                return
        
        logger.info(f"Received text message from user {user_id} in chat {chat_id}: {user_message[:100]}")
        
        # Extract and store user preferences (name, favorite color) if mentioned
        name, favorite_color = extract_user_info(user_message)
        if name or favorite_color:
            try:
                ConversationStorage.set_user_preferences(
                    str(user_id), 
                    str(chat_id), 
                    name=name, 
                    favorite_color=favorite_color
                )
                if name or favorite_color:
                    logger.info(f"Stored user preferences for {user_id}/{chat_id}: name={name}, favorite_color={favorite_color}")
            except Exception as e:
                logger.warning(f"Failed to store user preferences: {e}", exc_info=True)
        
        # Send initial "typing..." indicator
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # Stream responses from the agent as they arrive
        message_count = 0
        last_message_id = None
        last_typing_update = time.time()
        typing_update_interval = 4.0  # Update typing indicator every 4 seconds
        stream_active = True
        
        # Start typing indicator update task
        import asyncio
        async def keep_typing():
            """Keep typing indicator active while streaming."""
            while stream_active:
                await asyncio.sleep(typing_update_interval)
                if stream_active:
                    try:
                        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                    except Exception as e:
                        logger.debug(f"Failed to update typing indicator: {e}")
                        break
        
        typing_task = asyncio.create_task(keep_typing())
        
        try:
            import time
            for message_text, is_final in stream_agent_message(
                user_message,
                user_id=user_id,
                chat_id=chat_id,
                line_timeout=30.0,  # 30 seconds between JSON lines
                max_total_time=300.0  # 5 minutes total
            ):
                # Skip empty messages (final signal)
                if not message_text and is_final:
                    break
                
                if not message_text:
                    continue
                
                # Determine parse mode based on content
                parse_mode = None
                if "**" in message_text or "*" in message_text:
                    parse_mode = "Markdown"
                
                # Send the message
                try:
                    sent_message = await update.message.reply_text(
                        message_text,
                        parse_mode=parse_mode
                    )
                    message_count += 1
                    last_message_id = sent_message.message_id
                    logger.debug(f"Sent message {message_count} to user {user_id} (message_id: {last_message_id})")
                except Exception as send_error:
                    logger.error(f"Failed to send message to Telegram: {send_error}", exc_info=True)
                    # Try to send error message if this is the first message
                    if message_count == 0:
                        try:
                            await update.message.reply_text(
                                "❌ I encountered an error sending my response. Please try again."
                            )
                        except:
                            pass
                    break
                
                # If this is the final message, we're done
                if is_final:
                    break
            
            # Stop typing indicator
            stream_active = False
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
            
            if message_count > 0:
                logger.info(f"Successfully sent {message_count} message(s) to user {user_id}")
            else:
                logger.warning(f"No messages were sent to user {user_id}")
        
        except Exception as stream_error:
            # Stop typing indicator on error
            stream_active = False
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
            logger.error(f"Error streaming agent response: {stream_error}", exc_info=True)
            # Try to send error message if no messages were sent yet
            if message_count == 0:
                try:
                    await update.message.reply_text(
                        "❌ I encountered an error processing your message. Please try again."
                    )
                except Exception as send_error:
                    logger.error(f"Failed to send error message: {send_error}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error handling text message: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "❌ I encountered an error processing your message. Please try again."
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message: {send_error}", exc_info=True)

