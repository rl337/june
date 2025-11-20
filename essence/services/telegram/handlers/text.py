"""Text message handler for Telegram bot - handles owner/whitelisted user messages."""
import logging
from typing import Optional

from opentelemetry import trace
from telegram import Update
from telegram.ext import ContextTypes

from essence.chat.utils.tracing import get_tracer

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
    Handle text messages from Telegram users.

    Flow:
    - Non-whitelisted users: Ignore completely (no response)
    - Owner users: Append to USER_MESSAGES.md with status "NEW" for looping agent to process
    - Whitelisted (non-owner) users: Forward message to owner

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

            # Check if user is whitelisted
            from essence.chat.user_messages_sync import (
                is_user_whitelisted,
                is_user_owner,
                append_message_to_user_messages,
            )

            is_whitelisted = is_user_whitelisted(str(user_id), "telegram")
            span.set_attribute("whitelisted", is_whitelisted)

            # Non-whitelisted users: Ignore completely (no response)
            if not is_whitelisted:
                logger.info(f"Ignoring message from non-whitelisted user {user_id}")
                span.set_attribute("action", "ignored")
                span.set_status(trace.Status(trace.StatusCode.OK))
                return  # Silently ignore - don't send any response

            # Get username if available
            username = None
            try:
                if update.effective_user.username:
                    username = f"@{update.effective_user.username}"
            except Exception:
                pass

            # Check if user is owner
            is_owner = is_user_owner(str(user_id), "telegram")
            span.set_attribute("is_owner", is_owner)

            if is_owner:
                # Owner: Append to USER_MESSAGES.md with status "NEW"
                logger.info(
                    f"Owner user {user_id} - appending to USER_MESSAGES.md with status NEW"
                )

                success = append_message_to_user_messages(
                    user_id=str(user_id),
                    chat_id=str(chat_id),
                    platform="telegram",
                    message_type="Request",
                    content=user_message,
                    message_id=str(update.message.message_id),
                    status="NEW",
                    username=username,
                )

                if success:
                    span.set_attribute("action", "appended_to_user_messages")
                    logger.info(f"Successfully appended owner message to USER_MESSAGES.md")
                else:
                    span.set_attribute("action", "append_failed")
                    logger.error(f"Failed to append owner message to USER_MESSAGES.md")

                span.set_status(trace.Status(trace.StatusCode.OK))
                return

            else:
                # Whitelisted (non-owner): Forward to owner
                logger.info(
                    f"Whitelisted (non-owner) user {user_id} - forwarding message to owner"
                )

                # Get owner user IDs for forwarding
                from essence.chat.user_messages_sync import get_owner_users

                owner_users = get_owner_users("telegram")
                if not owner_users:
                    logger.warning(
                        "No owner users configured, cannot forward whitelisted user message"
                    )
                    span.set_attribute("action", "forward_failed_no_owner")
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    return

                # Forward to first owner (for now - could be enhanced to forward to all)
                owner_user_id = owner_users[0]

                # Append forwarded message to USER_MESSAGES.md
                forward_content = f"[Forwarded from whitelisted user {user_id} (@{username or 'unknown'})] {user_message}"

                success = append_message_to_user_messages(
                    user_id=owner_user_id,
                    chat_id=str(chat_id),  # Use original chat_id
                    platform="telegram",
                    message_type="Request",
                    content=forward_content,
                    message_id=str(update.message.message_id),
                    status="NEW",
                    username=f"forwarded_from_{user_id}",
                )

                if success:
                    span.set_attribute("action", "forwarded_to_owner")
                    logger.info(
                        f"Successfully forwarded whitelisted user message to owner {owner_user_id}"
                    )
                else:
                    span.set_attribute("action", "forward_failed")
                    logger.error(
                        f"Failed to forward whitelisted user message to owner {owner_user_id}"
                    )

                span.set_status(trace.Status(trace.StatusCode.OK))
                return

        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
