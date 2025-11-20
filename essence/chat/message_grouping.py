"""
Message Grouping for Agent Communication

Groups multiple messages/requests together when possible to reduce message spam
and improve user experience.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default grouping configuration
DEFAULT_TIME_WINDOW_SECONDS = 30  # Group messages within 30 seconds
DEFAULT_MAX_GROUP_LENGTH = 3500  # Telegram max is 4096, leave room for formatting
DEFAULT_MAX_MESSAGES_PER_GROUP = 5  # Maximum messages to group together


@dataclass
class GroupedMessage:
    """Represents a grouped message"""

    messages: List[str]
    message_types: List[str]
    total_length: int
    can_group: bool
    group_id: Optional[str] = None  # For tracking grouped messages


def should_group_messages(
    messages: List[str],
    time_window: int = DEFAULT_TIME_WINDOW_SECONDS,
    max_length: int = DEFAULT_MAX_GROUP_LENGTH,
    max_messages: int = DEFAULT_MAX_MESSAGES_PER_GROUP,
) -> bool:
    """
    Determine if messages should be grouped together.

    Args:
        messages: List of message texts to consider grouping
        time_window: Time window in seconds (messages within this window can be grouped)
        max_length: Maximum total length for grouped message
        max_messages: Maximum number of messages to group

    Returns:
        True if messages should be grouped, False otherwise
    """
    if len(messages) < 2:
        return False

    if len(messages) > max_messages:
        return False

    total_length = sum(len(msg) for msg in messages)
    if total_length > max_length:
        return False

    # Add overhead for formatting (headers, separators, etc.)
    # Estimate ~50 chars per message for formatting
    formatted_length = total_length + (len(messages) * 50)
    if formatted_length > max_length:
        return False

    return True


def group_messages(
    messages: List[str],
    message_types: Optional[List[str]] = None,
    time_window: int = DEFAULT_TIME_WINDOW_SECONDS,
    max_length: int = DEFAULT_MAX_GROUP_LENGTH,
    max_messages: int = DEFAULT_MAX_MESSAGES_PER_GROUP,
) -> GroupedMessage:
    """
    Group multiple messages into a single formatted message.

    Args:
        messages: List of message texts to group
        message_types: Optional list of message types (e.g., "Request", "Response")
        time_window: Time window in seconds for grouping
        max_length: Maximum total length for grouped message
        max_messages: Maximum number of messages to group

    Returns:
        GroupedMessage object with grouped content and metadata
    """
    if message_types is None:
        message_types = ["text"] * len(messages)

    if len(messages) != len(message_types):
        logger.warning(
            f"Message count ({len(messages)}) doesn't match type count ({len(message_types)}), using defaults"
        )
        message_types = ["text"] * len(messages)

    can_group = should_group_messages(messages, time_window, max_length, max_messages)

    if not can_group or len(messages) == 1:
        # Return single message as-is
        return GroupedMessage(
            messages=messages,
            message_types=message_types,
            total_length=sum(len(msg) for msg in messages),
            can_group=False,
        )

    # Group messages with formatting
    grouped_parts = []
    for i, (msg, msg_type) in enumerate(zip(messages, message_types), 1):
        if len(messages) > 1:
            grouped_parts.append(f"**{msg_type} {i}:**\n{msg}")
        else:
            grouped_parts.append(msg)

    grouped_text = "\n\n---\n\n".join(grouped_parts)

    return GroupedMessage(
        messages=[grouped_text],
        message_types=["grouped"],
        total_length=len(grouped_text),
        can_group=True,
    )


def format_grouped_message(
    messages: List[str],
    message_types: Optional[List[str]] = None,
    platform: str = "telegram",
) -> str:
    """
    Format grouped messages for a specific platform.

    Args:
        messages: List of message texts
        message_types: Optional list of message types
        platform: Platform name ("telegram" or "discord")

    Returns:
        Formatted grouped message text
    """
    if message_types is None:
        message_types = ["text"] * len(messages)

    if len(messages) == 1:
        return messages[0]

    # Platform-specific formatting
    if platform == "telegram":
        # Use HTML formatting for Telegram
        parts = []
        for i, (msg, msg_type) in enumerate(zip(messages, message_types), 1):
            parts.append(f"<b>{msg_type} {i}:</b>\n{msg}")
        return "\n\n---\n\n".join(parts)
    elif platform == "discord":
        # Use Markdown formatting for Discord
        parts = []
        for i, (msg, msg_type) in enumerate(zip(messages, message_types), 1):
            parts.append(f"**{msg_type} {i}:**\n{msg}")
        return "\n\n---\n\n".join(parts)
    else:
        # Plain text fallback
        parts = []
        for i, (msg, msg_type) in enumerate(zip(messages, message_types), 1):
            parts.append(f"{msg_type} {i}:\n{msg}")
        return "\n\n---\n\n".join(parts)


def split_if_too_long(
    message: str, max_length: int, platform: str = "telegram"
) -> List[str]:
    """
    Split a message if it exceeds platform length limits.

    Args:
        message: Message text to potentially split
        max_length: Maximum length per message
        platform: Platform name ("telegram" or "discord")

    Returns:
        List of message parts (single item if no split needed)
    """
    if len(message) <= max_length:
        return [message]

    # Split by paragraphs first, then by sentences, then by words
    parts = []
    remaining = message

    while len(remaining) > max_length:
        # Try to split at paragraph boundary
        para_break = remaining.rfind("\n\n", 0, max_length)
        if para_break > max_length * 0.5:  # Only if we get at least 50% of max_length
            parts.append(remaining[:para_break].strip())
            remaining = remaining[para_break + 2 :].strip()
            continue

        # Try to split at sentence boundary
        sentence_breaks = [". ", "! ", "? "]
        best_break = -1
        for break_char in sentence_breaks:
            break_pos = remaining.rfind(break_char, 0, max_length)
            if break_pos > best_break:
                best_break = break_pos

        if best_break > max_length * 0.5:
            parts.append(remaining[: best_break + 1].strip())
            remaining = remaining[best_break + 2 :].strip()
            continue

        # Last resort: split at word boundary
        word_break = remaining.rfind(" ", 0, max_length)
        if word_break > max_length * 0.5:
            parts.append(remaining[:word_break].strip())
            remaining = remaining[word_break + 1 :].strip()
        else:
            # Force split (shouldn't happen often)
            parts.append(remaining[:max_length].strip())
            remaining = remaining[max_length:].strip()

    if remaining:
        parts.append(remaining.strip())

    return parts
