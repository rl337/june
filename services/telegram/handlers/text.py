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

# Add chat-service-base to path for shared agent handler
chat_base_path = Path(__file__).parent.parent.parent / "chat-service-base"
sys.path.insert(0, str(chat_base_path))

# Add essence to path for human interface
essence_path = Path(__file__).parent.parent.parent.parent / "essence"
sys.path.insert(0, str(essence_path))

from agent.handler import stream_agent_message
from conversation_storage import ConversationStorage
from essence.chat.message_builder import MessageBuilder

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
        last_message = None
        last_message_id = None
        last_typing_update = time.time()
        typing_update_interval = 4.0  # Update typing indicator every 4 seconds
        stream_active = True
        current_response = ""  # Track current response for in-place editing
        
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
        
        # Initialize message builder for structured messaging
        message_builder = MessageBuilder(
            service_name="telegram",
            user_id=str(user_id),
            chat_id=str(chat_id)
        )
        
        # Track the raw LLM response for building the turn
        raw_llm_response = ""
        
        try:
            import time
            for message_text, is_final in stream_agent_message(
                user_message,
                user_id=user_id,
                chat_id=chat_id,
                line_timeout=30.0,  # 30 seconds between JSON lines
                max_total_time=300.0,  # 5 minutes total
                platform="telegram",
                agent_script_name="telegram_response_agent.sh",
                agent_script_simple_name="telegram_response_agent_simple.sh",
                max_message_length=4096
            ):
                # Skip empty messages (final signal)
                if not message_text and is_final:
                    # Final signal - build full turn, handle splitting, and log
                    if raw_llm_response:
                        try:
                            # Build full turn for logging
                            turn = message_builder.build_turn(user_message, raw_llm_response)
                            rendered_parts = message_builder.split_message_if_needed(4096)
                            
                            if rendered_parts:
                                if last_message:
                                    # Edit first part in place, send rest as new
                                    await last_message.edit_text(rendered_parts[0], parse_mode="Markdown")
                                    for part in rendered_parts[1:]:
                                        await update.message.reply_text(part, parse_mode="Markdown")
                                        message_count += 1
                                else:
                                    # No message sent yet, send all parts
                                    last_message = await update.message.reply_text(rendered_parts[0], parse_mode="Markdown")
                                    message_count += 1
                                    for part in rendered_parts[1:]:
                                        await update.message.reply_text(part, parse_mode="Markdown")
                                        message_count += 1
                            
                            # Log the turn for debugging
                            turn.log_to_file()
                        except Exception as edit_error:
                            logger.error(f"Failed to edit final message: {edit_error}", exc_info=True)
                            from essence.chat.error_handler import render_error_for_platform
                            error_text = render_error_for_platform(
                                edit_error,
                                "telegram",
                                "❌ I encountered an error finalizing my response."
                            )
                            try:
                                if last_message:
                                    await last_message.edit_text(error_text, parse_mode="Markdown")
                                else:
                                    await update.message.reply_text(error_text, parse_mode="Markdown")
                            except:
                                pass
                    break
                
                if not message_text:
                    continue
                
                # Track the raw LLM response (use longest version for incremental updates)
                if len(message_text) > len(raw_llm_response):
                    raw_llm_response = message_text
                    
                    # For streaming, parse and render incrementally
                    # Don't build full turn until final (that's expensive)
                    try:
                        from essence.chat.markdown_parser import parse_markdown
                        from essence.chat.platform_translators import get_translator
                        
                        # Parse markdown incrementally
                        widgets = parse_markdown(raw_llm_response)
                        translator = get_translator("telegram")
                        rendered_text = translator.render_message(widgets)
                        
                        # Validate before sending
                        from essence.chat.platform_validators import get_validator
                        validator = get_validator("telegram")
                        is_valid, errors = validator.validate(rendered_text)
                        
                        if not is_valid:
                            # If invalid, escape the text to be safe
                            logger.warning(f"Invalid Telegram markdown detected, escaping: {errors}")
                            from essence.chat.human_interface import EscapedText
                            safe_widget = EscapedText(text=raw_llm_response)
                            rendered_text = translator.render_widget(safe_widget)
                        
                        # Split if needed (but only for final, for streaming just use first part)
                        if len(rendered_text) > 4096:
                            # For streaming, just show first part
                            rendered_text = rendered_text[:4096]
                        
                        if last_message is None:
                            # First message - send it immediately for streaming
                            last_message = await update.message.reply_text(rendered_text, parse_mode="Markdown")
                            message_count += 1
                            last_message_id = last_message.message_id
                            logger.debug(f"Sent initial streaming message to user {user_id} (length: {len(rendered_text)})")
                        else:
                            # Update existing message in place for streaming
                            await last_message.edit_text(rendered_text, parse_mode="Markdown")
                            logger.debug(f"Updated streaming message in place (length: {len(rendered_text)})")
                    except Exception as send_error:
                        logger.error(f"Failed to send/edit message to Telegram: {send_error}", exc_info=True)
                        # Use structured error message
                        from essence.chat.error_handler import render_error_for_platform
                        error_text = render_error_for_platform(
                            send_error,
                            "telegram",
                            "❌ I encountered an error sending my response. Please try again."
                        )
                        if message_count == 0:
                            try:
                                await update.message.reply_text(error_text, parse_mode="Markdown")
                            except:
                                pass
                        break
                    
                    # If this is the final message, we're done (but continue to get final signal)
                    if is_final:
                        continue
            
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
            # Try to send structured error message if no messages were sent yet
            if message_count == 0:
                try:
                    from essence.chat.error_handler import render_error_for_platform
                    error_text = render_error_for_platform(
                        stream_error,
                        "telegram",
                        "❌ I encountered an error processing your message. Please try again."
                    )
                    await update.message.reply_text(error_text, parse_mode="Markdown")
                except Exception as send_error:
                    logger.error(f"Failed to send error message: {send_error}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error handling text message: {e}", exc_info=True)
        try:
            from essence.chat.error_handler import render_error_for_platform
            error_text = render_error_for_platform(
                e,
                "telegram",
                "❌ I encountered an error processing your message. Please try again."
            )
            await update.message.reply_text(error_text, parse_mode="Markdown")
        except Exception as send_error:
            logger.error(f"Failed to send error message: {send_error}", exc_info=True)

