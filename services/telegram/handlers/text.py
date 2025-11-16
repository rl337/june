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
# In Docker container, chat-service-base is copied to /app/chat-service-base
_script_dir = Path(__file__).parent
possible_paths = [
    Path("/app") / "chat-service-base",  # Docker container path (copied by Dockerfile)
    _script_dir.parent.parent / "chat-service-base",  # Relative from handlers/ (local dev)
    Path("/app") / "services" / "chat-service-base",  # Alternative Docker path
]

chat_base_path = None
for path in possible_paths:
    resolved = path.resolve()
    if resolved.exists() and (resolved / "agent" / "handler.py").exists():
        chat_base_path = resolved
        break

if chat_base_path:
    chat_base_abs = str(chat_base_path.absolute())
    sys.path.insert(0, chat_base_abs)
    from agent.handler import stream_agent_message
else:
    raise ImportError(f"Could not find chat-service-base directory. Tried: {possible_paths}")

# Add essence to path for human interface
# In Docker container, essence is copied to /app/essence
essence_paths = [
    Path("/app") / "essence",  # Docker container path
    Path(__file__).parent.parent.parent.parent / "essence",  # Local dev relative path
]
for essence_path in essence_paths:
    if essence_path.exists():
        sys.path.insert(0, str(essence_path.absolute()))
        break
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
        
        # Initialize first message pattern tracker for this request
        # This will be used to detect authoritative result messages
        _first_message_pattern = None
        
        try:
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
                    logger.info(f"Received final signal. raw_llm_response length: {len(raw_llm_response) if raw_llm_response else 0}")
                    if raw_llm_response:
                        try:
                            # Build full turn for logging
                            turn = message_builder.build_turn(user_message, raw_llm_response)
                            rendered_parts = message_builder.split_message_if_needed(4096)
                            
                            logger.info(f"Final message split into {len(rendered_parts)} parts. First part length: {len(rendered_parts[0]) if rendered_parts else 0}")
                            
                            if rendered_parts:
                                if last_message:
                                    # Edit first part in place, send rest as new
                                    logger.info(f"Editing final message (first part: {len(rendered_parts[0])} chars)")
                                    await last_message.edit_text(rendered_parts[0], parse_mode="Markdown")
                                    for i, part in enumerate(rendered_parts[1:], 1):
                                        logger.info(f"Sending additional part {i+1}/{len(rendered_parts)} (length: {len(part)})")
                                        await update.message.reply_text(part, parse_mode="Markdown")
                                        message_count += 1
                                else:
                                    # No message sent yet, send all parts
                                    logger.info(f"Sending final message (first part: {len(rendered_parts[0])} chars)")
                                    last_message = await update.message.reply_text(rendered_parts[0], parse_mode="Markdown")
                                    message_count += 1
                                    for i, part in enumerate(rendered_parts[1:], 1):
                                        logger.info(f"Sending additional part {i+1}/{len(rendered_parts)} (length: {len(part)})")
                                        await update.message.reply_text(part, parse_mode="Markdown")
                                        message_count += 1
                            
                            # Log the turn for debugging
                            try:
                                turn.log_to_file()
                            except Exception as log_error:
                                logger.warning(f"Failed to log turn to file: {log_error}")
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
                
                # Track the raw LLM response
                # Strategy:
                # 1. If new message is longer, it's likely an extension - use it
                # 2. If new message is significantly shorter but starts with the same pattern as the FIRST message we saw,
                #    it's likely the authoritative result message (full accumulated) - use it
                # 3. Otherwise, keep the longest version
                message_updated = False
                
                # Get the first message pattern (from the very first message, not the current accumulated)
                if not _first_message_pattern and raw_llm_response:
                    # Store the pattern from the first message we see
                    _first_message_pattern = raw_llm_response[:30] if len(raw_llm_response) >= 30 else raw_llm_response
                
                first_message_pattern = _first_message_pattern
                
                if len(message_text) > len(raw_llm_response):
                    # New message is longer - it's an extension
                    raw_llm_response = message_text
                    message_updated = True
                    logger.debug(f"Extended raw_llm_response: {len(raw_llm_response)} chars, preview={raw_llm_response[:50]}...")
                elif message_text and raw_llm_response and first_message_pattern and message_text.startswith(first_message_pattern) and len(message_text) < len(raw_llm_response) * 0.9:
                    # Message is shorter but starts with same pattern as FIRST message - likely the authoritative result message
                    # This handles cases where we incorrectly accumulated duplicates, and the result message is the correct shorter version
                    old_length = len(raw_llm_response)
                    raw_llm_response = message_text
                    message_updated = True
                    logger.info(f"Replaced with authoritative result message (shorter but correct): {len(raw_llm_response)} chars (was {old_length} chars)")
                elif message_text and raw_llm_response and message_text not in raw_llm_response:
                    # Different content - check if it's actually longer or if we should keep the accumulated one
                    # Usually cursor-agent sends full accumulated text, so longer = more complete
                    if len(message_text) > len(raw_llm_response):
                        raw_llm_response = message_text
                        message_updated = True
                        logger.debug(f"Replaced with longer message: {len(raw_llm_response)} chars")
                
                # Always render and update with the longest accumulated message
                # Update on every new chunk to show incremental progress
                if raw_llm_response and (message_updated or last_message is None):
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
                        # Use lenient validation during streaming (is_final=False) to allow incomplete markdown
                        # Only do strict validation on final messages
                        from essence.chat.platform_validators import get_validator
                        validator = get_validator("telegram")
                        is_valid, errors = validator.validate(rendered_text, lenient=not is_final)
                        
                        if not is_valid:
                            # If invalid, try to re-parse and render more carefully
                            # Don't escape the entire raw_llm_response - that loses all structure
                            # Instead, re-parse and render, which will handle escaping at the widget level
                            logger.warning(f"Invalid Telegram markdown detected during streaming, re-parsing: {errors}")
                            # Re-parse to ensure widgets are correct
                            widgets = parse_markdown(raw_llm_response)
                            rendered_text = translator.render_message(widgets)
                            # Re-validate after re-parsing
                            is_valid, errors = validator.validate(rendered_text, lenient=not is_final)
                            if not is_valid:
                                # If still invalid, only then escape (but this should be rare)
                                logger.warning(f"Still invalid after re-parsing, escaping: {errors}")
                                from essence.chat.human_interface import EscapedText
                                safe_widget = EscapedText(text=raw_llm_response)
                                rendered_text = translator.render_widget(safe_widget)
                        
                        # For streaming, show full message (don't truncate - let final handler split if needed)
                        # Only truncate if it's extremely long to avoid Telegram API errors
                        original_length = len(rendered_text)
                        if len(rendered_text) > 4096:
                            # For very long messages during streaming, show first 4096 chars
                            # The final handler will properly split the full message
                            rendered_text = rendered_text[:4096]
                            logger.debug(f"Truncated streaming message to 4096 chars (full length: {original_length})")
                        
                        if last_message is None:
                            # First message - send it immediately for streaming
                            last_message = await update.message.reply_text(rendered_text, parse_mode="Markdown")
                            message_count += 1
                            last_message_id = last_message.message_id
                            logger.info(f"Sent initial streaming message to user {user_id} (length: {len(rendered_text)}, is_final: {is_final})")
                        else:
                            # Update existing message in place for streaming - this should add more text
                            await last_message.edit_text(rendered_text, parse_mode="Markdown")
                            logger.info(f"Updated streaming message in place (length: {len(rendered_text)}, is_final: {is_final})")
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
                    
                    # If this is the final message, we've already updated the message above
                    # Continue to get the final empty signal to trigger final processing
                    if is_final:
                        # Don't skip - we want to process this final chunk
                        # The final empty signal will come next to trigger final processing
                        pass
            
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

