"""Text message handler for Telegram bot - uses TelegramResponse agent."""
import asyncio
import logging
import re
import time
from typing import Optional

from opentelemetry import trace
from telegram import Update
from telegram.ext import ContextTypes

from essence.chat.agent.handler import stream_agent_message
from essence.chat.message_builder import MessageBuilder
from essence.chat.utils.tracing import get_tracer
from essence.services.telegram.conversation_storage import ConversationStorage
from essence.services.telegram.message_history_helpers import (
    edit_text_with_history,
    reply_text_with_history,
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


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


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, config
):
    """
    Handle text messages from Telegram users by calling the TelegramResponse agent.

    Args:
        update: Telegram update object
        context: Telegram context
        config: Service configuration
    """
    with tracer.start_as_current_span("telegram.text_message.handle") as span:
        try:
            user_message = update.message.text
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id

            # Set span attributes
            span.set_attribute("user_id", str(user_id))
            span.set_attribute("chat_id", str(chat_id))
            span.set_attribute(
                "message_length", len(user_message) if user_message else 0
            )
            span.set_attribute("platform", "telegram")

            # Check if user is authorized (allow list)
            import os

            authorized_users_str = os.getenv("TELEGRAM_AUTHORIZED_USERS", "")
            if authorized_users_str:
                authorized_users = [
                    int(uid.strip())
                    for uid in authorized_users_str.split(",")
                    if uid.strip().isdigit()
                ]
                if authorized_users and user_id not in authorized_users:
                    logger.info(f"Ignoring message from unauthorized user {user_id}")
                    span.set_attribute("authorized", False)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    # Silently ignore - don't send any response
                    return

            span.set_attribute("authorized", True)

            logger.info(
                f"Received text message from user {user_id} in chat {chat_id}: {user_message[:100]}"
            )

            # Extract and store user preferences (name, favorite color) if mentioned
            name, favorite_color = extract_user_info(user_message)
            if name or favorite_color:
                with tracer.start_as_current_span(
                    "telegram.text_message.store_preferences"
                ) as pref_span:
                    try:
                        pref_span.set_attribute("user_id", str(user_id))
                        pref_span.set_attribute("chat_id", str(chat_id))
                        pref_span.set_attribute("has_name", name is not None)
                        pref_span.set_attribute(
                            "has_favorite_color", favorite_color is not None
                        )
                        ConversationStorage.set_user_preferences(
                            str(user_id),
                            str(chat_id),
                            name=name,
                            favorite_color=favorite_color,
                        )
                        if name or favorite_color:
                            logger.info(
                                f"Stored user preferences for {user_id}/{chat_id}: name={name}, favorite_color={favorite_color}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to store user preferences: {e}", exc_info=True
                        )
                        pref_span.record_exception(e)
                        pref_span.set_status(
                            trace.Status(trace.StatusCode.ERROR, str(e))
                        )

            # Simple status-based approach:
            # 1. Send "received request" immediately
            # 2. Send "processing" when making agentic call
            # 3. Send "generating" with dots for each chunk
            # 4. Replace with final result when done

            status_message = None
            raw_llm_response = ""

            # Step 1: Send "received request" immediately
            try:
                status_message = await update.message.reply_text("✅ Received request")
                logger.info(f"Sent 'received request' to user {user_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to send 'received request': {e}, continuing anyway"
                )
                # Continue processing even if initial status fails

            # Step 2: Update to "processing" when making agentic call
            if status_message:
                try:
                    await status_message.edit_text("🔄 Processing...")
                    logger.info(f"Updated to 'processing' for user {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to update to 'processing': {e}")

            # Initialize message builder for final result (using HTML format for native strikethrough support)
            message_builder = MessageBuilder(
                service_name="telegram",
                user_id=str(user_id),
                chat_id=str(chat_id),
                format="html",
            )

            try:
                # Stream responses from the agent
                chunk_count = 0
                with tracer.start_as_current_span(
                    "telegram.text_message.stream_agent"
                ) as stream_span:
                    stream_span.set_attribute("user_id", str(user_id))
                    stream_span.set_attribute("chat_id", str(chat_id))
                    stream_span.set_attribute(
                        "message_length", len(user_message) if user_message else 0
                    )
                    stream_span.set_attribute("platform", "telegram")

                    for message_text, is_final, message_type in stream_agent_message(
                        user_message,
                        user_id=user_id,
                        chat_id=chat_id,
                        line_timeout=30.0,  # 30 seconds between JSON lines
                        max_total_time=300.0,  # 5 minutes total
                        platform="telegram",
                        agent_script_name="telegram_response_agent.sh",
                        agent_script_simple_name="telegram_response_agent_simple.sh",
                        max_message_length=4096,
                    ):
                        # Skip empty final signal - we'll handle final result separately
                        if not message_text and is_final:
                            break

                        if not message_text:
                            continue

                        # Track the raw LLM response - use result type as authoritative, otherwise keep longest
                        if message_type == "result":
                            raw_llm_response = message_text
                            logger.info(
                                f"Received authoritative result message: {len(raw_llm_response)} chars"
                            )
                            stream_span.set_attribute("result_received", True)
                            stream_span.set_attribute(
                                "result_length", len(raw_llm_response)
                            )
                        elif len(message_text) > len(raw_llm_response):
                            raw_llm_response = message_text
                            logger.debug(
                                f"Extended raw_llm_response: {len(raw_llm_response)} chars"
                            )

                        # Step 3: Update status to "generating" with dots for each chunk
                        chunk_count += 1
                        stream_span.set_attribute("chunk_count", chunk_count)
                        if status_message:
                            dots = "." * min(chunk_count, 5)  # Max 5 dots
                            try:
                                await status_message.edit_text(f"⚙️ Generating{dots}")
                            except Exception as e:
                                logger.debug(f"Failed to update generating status: {e}")

                    stream_span.set_attribute("total_chunks", chunk_count)
                    stream_span.set_attribute(
                        "final_response_length",
                        len(raw_llm_response) if raw_llm_response else 0,
                    )

                # Step 4: Replace with final result when done
                if raw_llm_response:
                    with tracer.start_as_current_span(
                        "telegram.text_message.build_and_render"
                    ) as render_span:
                        render_span.set_attribute("user_id", str(user_id))
                        render_span.set_attribute("chat_id", str(chat_id))
                        render_span.set_attribute(
                            "response_length", len(raw_llm_response)
                        )
                        try:
                            # Build full turn and render
                            turn = message_builder.build_turn(
                                user_message, raw_llm_response
                            )
                            rendered_parts = message_builder.split_message_if_needed(
                                4096
                            )
                            render_span.set_attribute(
                                "rendered_parts_count", len(rendered_parts)
                            )

                            logger.info(
                                f"Final message split into {len(rendered_parts)} parts"
                            )

                            if rendered_parts:
                                # Replace status message with first part (or send as new if no status message)
                                user_id = (
                                    str(update.effective_user.id)
                                    if update.effective_user
                                    else None
                                )
                                chat_id = (
                                    str(update.effective_chat.id)
                                    if update.effective_chat
                                    else None
                                )

                                if status_message:
                                    try:
                                        await edit_text_with_history(
                                            status_message,
                                            rendered_parts[0],
                                            parse_mode="HTML",
                                            user_id=user_id,
                                            chat_id=chat_id,
                                            message_type="text",
                                            rendering_metadata={
                                                "part": 1,
                                                "total_parts": len(rendered_parts),
                                            },
                                            raw_text=raw_llm_response
                                            if raw_llm_response
                                            else None,
                                        )
                                        logger.info(
                                            f"Replaced status with final message (first part: {len(rendered_parts[0])} chars)"
                                        )
                                        render_span.set_attribute("message_sent", True)
                                    except Exception as edit_err:
                                        # If edit fails, send as new message
                                        error_msg = str(edit_err)
                                        if (
                                            "Message is not modified" in error_msg
                                            or "message is not modified"
                                            in error_msg.lower()
                                        ):
                                            logger.debug(
                                                f"Final message unchanged, skipping edit"
                                            )
                                        else:
                                            logger.warning(
                                                f"Failed to edit status message, sending as new: {edit_err}"
                                            )
                                            await reply_text_with_history(
                                                update,
                                                rendered_parts[0],
                                                parse_mode="HTML",
                                                message_type="text",
                                                rendering_metadata={
                                                    "part": 1,
                                                    "total_parts": len(rendered_parts),
                                                    "fallback": True,
                                                },
                                                raw_text=raw_llm_response
                                                if raw_llm_response
                                                else None,
                                            )
                                else:
                                    # No status message, send as new
                                    await reply_text_with_history(
                                        update,
                                        rendered_parts[0],
                                        parse_mode="HTML",
                                        message_type="text",
                                        rendering_metadata={
                                            "part": 1,
                                            "total_parts": len(rendered_parts),
                                        },
                                        raw_text=raw_llm_response
                                        if raw_llm_response
                                        else None,
                                    )
                                    logger.info(
                                        f"Sent final message (first part: {len(rendered_parts[0])} chars)"
                                    )
                                    render_span.set_attribute("message_sent", True)

                                # Send additional parts as new messages
                                for i, part in enumerate(rendered_parts[1:], 1):
                                    logger.info(
                                        f"Sending additional part {i+1}/{len(rendered_parts)} (length: {len(part)})"
                                    )
                                    await reply_text_with_history(
                                        update,
                                        part,
                                        parse_mode="HTML",
                                        message_type="text",
                                        rendering_metadata={
                                            "part": i + 1,
                                            "total_parts": len(rendered_parts),
                                        },
                                        raw_text=raw_llm_response
                                        if raw_llm_response and i == 0
                                        else None,
                                    )

                            # Log the turn for debugging
                            try:
                                turn.log_to_file()
                            except Exception as log_error:
                                logger.warning(
                                    f"Failed to log turn to file: {log_error}"
                                )
                        except Exception as final_error:
                            logger.error(
                                f"Failed to render final message: {final_error}",
                                exc_info=True,
                            )
                            render_span.record_exception(final_error)
                            render_span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(final_error))
                            )
                            from essence.chat.error_handler import (
                                render_error_for_platform,
                            )

                            error_text = render_error_for_platform(
                                final_error,
                                "telegram",
                                "❌ I encountered an error finalizing my response.",
                            )
                            try:
                                await status_message.edit_text(
                                    error_text, parse_mode="HTML"
                                )
                            except:
                                pass
                else:
                    # No response received
                    span.set_attribute("response_received", False)
                    if status_message:
                        try:
                            await status_message.edit_text("⚠️ No response generated")
                        except:
                            pass
                    else:
                        try:
                            await update.message.reply_text("⚠️ No response generated")
                        except:
                            pass

            except Exception as stream_error:
                logger.error(
                    f"Error streaming agent response: {stream_error}", exc_info=True
                )
                span.record_exception(stream_error)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(stream_error)))
                # Update status message with error
                try:
                    from essence.chat.error_handler import render_error_for_platform

                    error_text = render_error_for_platform(
                        stream_error,
                        "telegram",
                        "❌ I encountered an error processing your message. Please try again.",
                    )
                    if status_message:
                        await status_message.edit_text(error_text, parse_mode="HTML")
                    else:
                        await update.message.reply_text(error_text, parse_mode="HTML")
                except Exception as send_error:
                    logger.error(
                        f"Failed to send error message: {send_error}", exc_info=True
                    )

        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            try:
                from essence.chat.error_handler import render_error_for_platform

                error_text = render_error_for_platform(
                    e,
                    "telegram",
                    "❌ I encountered an error processing your message. Please try again.",
                )
                await update.message.reply_text(error_text, parse_mode="HTML")
            except Exception as send_error:
                logger.error(
                    f"Failed to send error message: {send_error}", exc_info=True
                )
