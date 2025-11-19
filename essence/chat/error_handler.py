"""
Error handling utilities for structured error messages.
"""

import logging
import traceback
from typing import Optional

from .human_interface import ErrorMessage, EscapedText, Message
from .message_builder import MessageBuilder

logger = logging.getLogger(__name__)


def create_error_message(
    exception: Exception,
    user_friendly_message: Optional[str] = None,
    include_traceback: bool = False,
) -> Message:
    """
    Create a structured error message from an exception.

    Args:
        exception: The exception that occurred
        user_friendly_message: Optional user-friendly message (defaults to generic)
        include_traceback: Whether to include full traceback in error details

    Returns:
        Message containing error information
    """
    error_type = type(exception).__name__
    error_details = str(exception)

    if include_traceback:
        error_details += "\n\n" + traceback.format_exc()

    if user_friendly_message is None:
        user_friendly_message = (
            f"❌ I encountered an error processing your request. Please try again."
        )

    # Create error message widget
    error_widget = ErrorMessage(
        user_message=user_friendly_message,
        error_details=error_details,
        error_type=error_type,
    )

    # Return as a message with escaped text (safe for all platforms)
    # The error details are included but escaped
    error_text = f"{error_widget.user_message}\n\nError: {error_widget.error_type}"
    if include_traceback:
        error_text += f"\n\nDetails: {error_widget.error_details}"

    return Message(content=[EscapedText(text=error_text)])


def render_error_for_platform(
    exception: Exception,
    platform: str,
    user_friendly_message: Optional[str] = None,
    include_traceback: bool = False,
) -> str:
    """
    Create and render an error message for a specific platform.

    Args:
        exception: The exception that occurred
        platform: Platform name ('telegram', 'discord', etc.)
        user_friendly_message: Optional user-friendly message
        include_traceback: Whether to include full traceback

    Returns:
        Platform-specific markdown string for the error
    """
    error_message = create_error_message(
        exception, user_friendly_message, include_traceback
    )
    builder = MessageBuilder(service_name=platform)
    return builder.render_message(error_message)
