"""
Agent-to-User Communication Interface

Provides programmatic interface for agents to send messages directly to users
via Telegram or Discord, with support for common communication patterns.

**CRITICAL:** When agent-to-user communication is active via Telegram, the Telegram
service must be disabled to prevent race conditions. This module checks service
status and warns if services are running.
"""
import logging
import os
import subprocess
from enum import Enum
from typing import Any, Dict, List, Optional

from essence.chat.message_grouping import (
    format_grouped_message,
    group_messages,
    split_if_too_long,
)
from essence.chat.message_history import get_message_history
from essence.chat.message_history_analysis import validate_message_for_platform
from essence.chat.user_requests_sync import sync_message_to_user_requests

logger = logging.getLogger(__name__)


class CommunicationChannel(str, Enum):
    """Available communication channels"""

    TELEGRAM = "telegram"
    DISCORD = "discord"
    AUTO = "auto"  # Try Telegram first, fallback to Discord


class AgentCommunicationError(Exception):
    """Base exception for agent communication errors"""

    pass


class ServiceRunningError(AgentCommunicationError):
    """Raised when a service is running and would cause race conditions"""

    pass


class ChannelUnavailableError(AgentCommunicationError):
    """Raised when a communication channel is unavailable"""

    pass


def check_service_running(service_name: str) -> bool:
    """
    Check if a Docker service is running.

    Args:
        service_name: Name of the service (e.g., "telegram", "discord")

    Returns:
        True if service is running, False otherwise
    """
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "-q", service_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        # If docker command fails, assume service is not running
        return False


def check_telegram_service_running() -> bool:
    """Check if Telegram service is running"""
    return check_service_running("telegram")


def check_discord_service_running() -> bool:
    """Check if Discord service is running"""
    return check_service_running("discord")


def verify_service_stopped_for_platform(
    platform: CommunicationChannel,
) -> tuple[bool, Optional[str]]:
    """
    Verify that the service for the given platform is stopped.

    Args:
        platform: Platform to check

    Returns:
        Tuple of (is_stopped, error_message):
        - is_stopped: True if service is stopped, False if running
        - error_message: Error message if service is running, None if stopped
    """
    if platform == CommunicationChannel.TELEGRAM:
        if check_telegram_service_running():
            return (
                False,
                "Telegram service is running. Disable it before using agent communication "
                "to prevent race conditions. Run: docker compose stop telegram",
            )
    elif platform == CommunicationChannel.DISCORD:
        if check_discord_service_running():
            return (
                False,
                "Discord service is running. Disable it before using agent communication "
                "to prevent race conditions. Run: docker compose stop discord",
            )
    return True, None


def send_message_to_user(
    user_id: str,
    chat_id: str,
    message: str,
    platform: CommunicationChannel = CommunicationChannel.AUTO,
    message_type: str = "text",
    require_service_stopped: bool = True,
) -> Dict[str, Any]:
    """
    Send a message to a user via Telegram or Discord.

    This is a high-level interface that handles platform selection, service
    status checking, and message validation.

    **CRITICAL:** When using agent communication, the corresponding service
    (Telegram or Discord) MUST be stopped to prevent race conditions. This
    function will raise ServiceRunningError if the service is running and
    require_service_stopped=True.

    **Workflow:**
    1. Stop service: `docker compose stop telegram` (or `discord`)
    2. Use agent communication (send messages, read requests)
    3. Restart service when done: `docker compose start telegram` (or `discord`)

    Args:
        user_id: User ID to send message to
        chat_id: Chat/channel ID to send message to
        message: Message text to send
        platform: Platform to use (default: AUTO - try Telegram first, fallback to Discord)
        message_type: Type of message ("text", "error", "status", "clarification", "help_request", "progress")
        require_service_stopped: If True, raise error if service is running (prevents race conditions)

    Returns:
        Dictionary with result:
        - success: Whether message was sent successfully
        - platform: Platform used ("telegram" or "discord")
        - message_id: Message ID if sent successfully
        - error: Error message if failed

    Raises:
        ServiceRunningError: If service is running and require_service_stopped=True
        ChannelUnavailableError: If no communication channel is available
        AgentCommunicationError: For other communication errors
    """
    # Determine platform
    if platform == CommunicationChannel.AUTO:
        # Try Telegram first, fallback to Discord
        if _can_use_telegram(require_service_stopped):
            platform = CommunicationChannel.TELEGRAM
        elif _can_use_discord(require_service_stopped):
            platform = CommunicationChannel.DISCORD
        else:
            raise ChannelUnavailableError(
                "No communication channel available. Telegram and Discord services may be running "
                "or not configured. Disable services before using agent communication."
            )

    # Check service status before sending
    if require_service_stopped:
        is_stopped, error_message = verify_service_stopped_for_platform(platform)
        if not is_stopped:
            raise ServiceRunningError(error_message)

    # Send message
    if platform == CommunicationChannel.TELEGRAM:
        return _send_telegram_message(user_id, chat_id, message, message_type)
    elif platform == CommunicationChannel.DISCORD:
        return _send_discord_message(user_id, chat_id, message, message_type)
    else:
        raise ValueError(f"Invalid platform: {platform}")


def _can_use_telegram(require_service_stopped: bool) -> bool:
    """Check if Telegram can be used"""
    if require_service_stopped and check_telegram_service_running():
        return False
    # Check if bot token is available
    return bool(os.getenv("TELEGRAM_BOT_TOKEN"))


def _can_use_discord(require_service_stopped: bool) -> bool:
    """Check if Discord can be used"""
    if require_service_stopped and check_discord_service_running():
        return False
    # Check if bot token is available
    return bool(os.getenv("DISCORD_BOT_TOKEN"))


def _send_telegram_message(
    user_id: str, chat_id: str, message: str, message_type: str
) -> Dict[str, Any]:
    """
    Send a message via Telegram Bot API.

    Uses python-telegram-bot library to send messages directly via Bot API.
    """
    try:
        import httpx

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            raise ChannelUnavailableError("TELEGRAM_BOT_TOKEN not configured")

        # Validate message
        validation = validate_message_for_platform(message, "telegram")
        if not validation["valid"]:
            logger.warning(f"Message validation failed: {validation['errors']}")
            # Truncate if too long
            if not validation["within_length_limit"]:
                message = message[:4093] + "..."

        # Send message via Telegram Bot API
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",  # Use HTML for better formatting
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                sent_message = result.get("result", {})
                message_id = str(sent_message.get("message_id", ""))

                # Store in message history
                try:
                    get_message_history().add_message(
                        platform="telegram",
                        user_id=user_id,
                        chat_id=chat_id,
                        message_content=message,
                        message_type=message_type,
                        message_id=message_id,
                        raw_text=message,
                        formatted_text=message,
                        rendering_metadata={
                            "message_length": len(message),
                            "telegram_max_length": 4096,
                            "within_limit": len(message) <= 4096,
                            "sent_by_agent": True,
                            "agent_message_type": message_type,
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to store message in history: {e}")

                # Sync to USER_REQUESTS.md if user is whitelisted
                try:
                    from essence.chat.user_requests_sync import is_user_whitelisted

                    if is_user_whitelisted(user_id, "telegram"):
                        # Try to get username from message history
                        username = None
                        try:
                            history = get_message_history()
                            user_messages = history.get_messages(
                                platform="telegram", user_id=user_id, limit=1
                            )
                            if user_messages:
                                username = user_messages[0].get("username")
                        except Exception:
                            pass

                        sync_message_to_user_requests(
                            user_id=user_id,
                            chat_id=chat_id,
                            platform="telegram",
                            message_type=message_type.replace("_", " ").title(),
                            content=message,
                            message_id=message_id,
                            status="Responded"
                            if message_type in ["response", "progress"]
                            else "Pending",
                            username=username,
                        )
                except Exception as e:
                    logger.warning(f"Failed to sync message to USER_REQUESTS.md: {e}")

                return {
                    "success": True,
                    "platform": "telegram",
                    "message_id": message_id,
                    "error": None,
                }
            else:
                error_msg = result.get("description", "Unknown error")
                raise AgentCommunicationError(f"Telegram API error: {error_msg}")

    except ImportError:
        raise ChannelUnavailableError(
            "httpx library not available. Install it to use Telegram communication."
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return {
            "success": False,
            "platform": "telegram",
            "message_id": None,
            "error": str(e),
        }


def edit_message_to_user(
    user_id: str,
    chat_id: str,
    message_id: str,
    new_message: str,
    platform: CommunicationChannel = CommunicationChannel.AUTO,
    message_type: str = "text",
    require_service_stopped: bool = True,
) -> Dict[str, Any]:
    """
    Edit an existing message sent to a user via Telegram or Discord.

    **CRITICAL:** When using agent communication, the corresponding service
    (Telegram or Discord) MUST be stopped to prevent race conditions.

    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        message_id: ID of the message to edit
        new_message: New message text
        platform: Platform to use (default: AUTO - try Telegram first, fallback to Discord)
        message_type: Type of message
        require_service_stopped: If True, raise error if service is running

    Returns:
        Dictionary with result:
        - success: Whether message was edited successfully
        - platform: Platform used
        - message_id: Message ID (same as input)
        - error: Error message if failed

    Raises:
        ServiceRunningError: If service is running and require_service_stopped=True
        ChannelUnavailableError: If no communication channel is available
        AgentCommunicationError: For other communication errors
    """
    # Determine platform
    if platform == CommunicationChannel.AUTO:
        if _can_use_telegram(require_service_stopped):
            platform = CommunicationChannel.TELEGRAM
        elif _can_use_discord(require_service_stopped):
            platform = CommunicationChannel.DISCORD
        else:
            raise ChannelUnavailableError(
                "No communication channel available. Telegram and Discord services may be running "
                "or not configured. Disable services before using agent communication."
            )

    # Check service status before editing
    if require_service_stopped:
        is_stopped, error_message = verify_service_stopped_for_platform(platform)
        if not is_stopped:
            raise ServiceRunningError(error_message)

    # Edit message
    if platform == CommunicationChannel.TELEGRAM:
        return _edit_telegram_message(
            user_id, chat_id, message_id, new_message, message_type
        )
    elif platform == CommunicationChannel.DISCORD:
        return _edit_discord_message(
            user_id, chat_id, message_id, new_message, message_type
        )
    else:
        raise ValueError(f"Invalid platform: {platform}")


def _edit_telegram_message(
    user_id: str, chat_id: str, message_id: str, new_message: str, message_type: str
) -> Dict[str, Any]:
    """
    Edit a message via Telegram Bot API.

    Args:
        user_id: User ID
        chat_id: Chat ID
        message_id: Message ID to edit
        new_message: New message text
        message_type: Message type

    Returns:
        Result dictionary
    """
    try:
        import httpx

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            raise ChannelUnavailableError("TELEGRAM_BOT_TOKEN not configured")

        # Validate message
        validation = validate_message_for_platform(new_message, "telegram")
        if not validation["valid"]:
            logger.warning(f"Message validation failed: {validation['errors']}")
            if not validation["within_length_limit"]:
                new_message = new_message[:4093] + "..."

        # Edit message via Telegram Bot API
        url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "text": new_message,
            "parse_mode": "HTML",
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                # Update message history
                try:
                    get_message_history().add_message(
                        platform="telegram",
                        user_id=user_id,
                        chat_id=chat_id,
                        message_content=new_message,
                        message_type=message_type,
                        message_id=message_id,
                        raw_text=new_message,
                        formatted_text=new_message,
                        rendering_metadata={
                            "message_length": len(new_message),
                            "telegram_max_length": 4096,
                            "within_limit": len(new_message) <= 4096,
                            "sent_by_agent": True,
                            "agent_message_type": message_type,
                            "is_edit": True,
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to store edited message in history: {e}")

                # Sync to USER_REQUESTS.md if user is whitelisted
                try:
                    from essence.chat.user_requests_sync import is_user_whitelisted

                    if is_user_whitelisted(user_id, "telegram"):
                        from essence.chat.user_requests_sync import (
                            sync_message_to_user_requests,
                        )

                        username = None
                        try:
                            history = get_message_history()
                            user_messages = history.get_messages(
                                platform="telegram", user_id=user_id, limit=1
                            )
                            if user_messages:
                                username = user_messages[0].get("username")
                        except Exception:
                            pass

                        sync_message_to_user_requests(
                            user_id=user_id,
                            chat_id=chat_id,
                            platform="telegram",
                            message_type=message_type.replace("_", " ").title(),
                            content=new_message,
                            message_id=message_id,
                            status="Responded"
                            if message_type in ["response", "progress"]
                            else "Pending",
                            username=username,
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to sync edited message to USER_REQUESTS.md: {e}"
                    )

                return {
                    "success": True,
                    "platform": "telegram",
                    "message_id": message_id,
                    "error": None,
                }
            else:
                error_msg = result.get("description", "Unknown error")
                raise AgentCommunicationError(f"Telegram API error: {error_msg}")

    except ImportError:
        raise ChannelUnavailableError(
            "httpx library not available. Install it to use Telegram communication."
        )
    except Exception as e:
        logger.error(f"Failed to edit Telegram message: {e}")
        return {
            "success": False,
            "platform": "telegram",
            "message_id": message_id,
            "error": str(e),
        }


def _edit_discord_message(
    user_id: str, chat_id: str, message_id: str, new_message: str, message_type: str
) -> Dict[str, Any]:
    """
    Edit a message via Discord REST API.

    Args:
        user_id: User ID
        chat_id: Channel ID
        message_id: Message ID to edit
        new_message: New message text
        message_type: Message type

    Returns:
        Result dictionary
    """
    try:
        import httpx

        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not bot_token:
            raise ChannelUnavailableError("DISCORD_BOT_TOKEN not configured")

        # Validate message
        validation = validate_message_for_platform(new_message, "discord")
        if not validation["valid"]:
            logger.warning(f"Message validation failed: {validation['errors']}")
            if not validation["within_length_limit"]:
                new_message = new_message[:1997] + "..."

        # Edit message via Discord REST API
        url = f"https://discord.com/api/v10/channels/{chat_id}/messages/{message_id}"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }
        payload = {"content": new_message}

        with httpx.Client(timeout=10.0) as client:
            response = client.patch(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

        # Update message history
        try:
            get_message_history().add_message(
                platform="discord",
                user_id=user_id,
                chat_id=chat_id,
                message_content=new_message,
                message_type=message_type,
                message_id=message_id,
                raw_text=new_message,
                formatted_text=new_message,
                rendering_metadata={
                    "message_length": len(new_message),
                    "discord_max_length": 2000,
                    "within_limit": len(new_message) <= 2000,
                    "sent_by_agent": True,
                    "agent_message_type": message_type,
                    "is_edit": True,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to store edited message in history: {e}")

        # Sync to USER_REQUESTS.md if user is whitelisted
        try:
            from essence.chat.user_requests_sync import is_user_whitelisted

            if is_user_whitelisted(user_id, "discord"):
                from essence.chat.user_requests_sync import (
                    sync_message_to_user_requests,
                )

                username = None
                try:
                    history = get_message_history()
                    user_messages = history.get_messages(
                        platform="discord", user_id=user_id, limit=1
                    )
                    if user_messages:
                        username = user_messages[0].get("username")
                except Exception:
                    pass

                sync_message_to_user_requests(
                    user_id=user_id,
                    chat_id=chat_id,
                    platform="discord",
                    message_type=message_type.replace("_", " ").title(),
                    content=new_message,
                    message_id=message_id,
                    status="Responded"
                    if message_type in ["response", "progress"]
                    else "Pending",
                    username=username,
                )
        except Exception as e:
            logger.warning(f"Failed to sync edited message to USER_REQUESTS.md: {e}")

        return {
            "success": True,
            "platform": "discord",
            "message_id": message_id,
            "error": None,
        }

    except ImportError:
        raise ChannelUnavailableError(
            "httpx library not available. Install it to use Discord communication."
        )
    except Exception as e:
        logger.error(f"Failed to edit Discord message: {e}")
        return {
            "success": False,
            "platform": "discord",
            "message_id": message_id,
            "error": str(e),
        }


def _send_discord_message(
    user_id: str, chat_id: str, message: str, message_type: str
) -> Dict[str, Any]:
    """
    Send a message via Discord HTTP API.

    Uses Discord REST API directly to send messages.
    """
    try:
        import httpx

        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not bot_token:
            raise ChannelUnavailableError("DISCORD_BOT_TOKEN not configured")

        # Validate message
        validation = validate_message_for_platform(message, "discord")
        if not validation["valid"]:
            logger.warning(f"Message validation failed: {validation['errors']}")
            # Truncate if too long
            if not validation["within_length_limit"]:
                message = message[:1997] + "..."

        # Send message via Discord REST API
        url = f"https://discord.com/api/v10/channels/{chat_id}/messages"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }
        payload = {"content": message}

        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
        message_id = str(result.get("id", ""))

        # Store in message history
        try:
            get_message_history().add_message(
                platform="discord",
                user_id=user_id,
                chat_id=chat_id,
                message_content=message,
                message_type=message_type,
                message_id=message_id,
                raw_text=message,
                formatted_text=message,
                rendering_metadata={
                    "message_length": len(message),
                    "discord_max_length": 2000,
                    "within_limit": len(message) <= 2000,
                    "sent_by_agent": True,
                    "agent_message_type": message_type,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to store message in history: {e}")

        # Sync to USER_REQUESTS.md if user is whitelisted
        try:
            from essence.chat.user_requests_sync import is_user_whitelisted

            if is_user_whitelisted(user_id, "discord"):
                # Try to get username from message history
                username = None
                try:
                    history = get_message_history()
                    user_messages = history.get_messages(
                        platform="discord", user_id=user_id, limit=1
                    )
                    if user_messages:
                        username = user_messages[0].get("username")
                except Exception:
                    pass

                sync_message_to_user_requests(
                    user_id=user_id,
                    chat_id=chat_id,
                    platform="discord",
                    message_type=message_type.replace("_", " ").title(),
                    content=message,
                    message_id=message_id,
                    status="Responded"
                    if message_type in ["response", "progress"]
                    else "Pending",
                    username=username,
                )
        except Exception as e:
            logger.warning(f"Failed to sync message to USER_REQUESTS.md: {e}")

        return {
            "success": True,
            "platform": "discord",
            "message_id": message_id,
            "error": None,
        }

    except ImportError:
        raise ChannelUnavailableError(
            "httpx library not available. Install it to use Discord communication."
        )
    except Exception as e:
        logger.error(f"Failed to send Discord message: {e}")
        return {
            "success": False,
            "platform": "discord",
            "message_id": None,
            "error": str(e),
        }


# Helper functions for common agent communication patterns


def ask_for_clarification(
    user_id: str,
    chat_id: str,
    question: str,
    context: Optional[str] = None,
    platform: CommunicationChannel = CommunicationChannel.AUTO,
) -> Dict[str, Any]:
    """
    Ask user for clarification on a task or requirement.

    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        question: Question to ask the user
        context: Optional context about what needs clarification
        platform: Platform to use (default: AUTO)

    Returns:
        Result dictionary from send_message_to_user
    """
    message = f"❓ **Clarification Needed**\n\n{question}"
    if context:
        message += f"\n\n_Context: {context}_"

    return send_message_to_user(
        user_id=user_id,
        chat_id=chat_id,
        message=message,
        platform=platform,
        message_type="clarification",
    )


def request_help(
    user_id: str,
    chat_id: str,
    issue: str,
    blocker_description: Optional[str] = None,
    platform: CommunicationChannel = CommunicationChannel.AUTO,
) -> Dict[str, Any]:
    """
    Request help from user when agent encounters a blocker.

    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        issue: Description of the issue/blocker
        blocker_description: Optional detailed description of what's blocking
        platform: Platform to use (default: AUTO)

    Returns:
        Result dictionary from send_message_to_user
    """
    message = f"🆘 **Help Requested**\n\n{issue}"
    if blocker_description:
        message += f"\n\n_Details: {blocker_description}_"

    return send_message_to_user(
        user_id=user_id,
        chat_id=chat_id,
        message=message,
        platform=platform,
        message_type="help_request",
    )


def report_progress(
    user_id: str,
    chat_id: str,
    progress_message: str,
    completion_percentage: Optional[int] = None,
    platform: CommunicationChannel = CommunicationChannel.AUTO,
) -> Dict[str, Any]:
    """
    Report progress on a task to the user.

    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        progress_message: Progress update message
        completion_percentage: Optional completion percentage (0-100)
        platform: Platform to use (default: AUTO)

    Returns:
        Result dictionary from send_message_to_user
    """
    message = f"📊 **Progress Update**\n\n{progress_message}"
    if completion_percentage is not None:
        message += f"\n\n_Completion: {completion_percentage}%_"

    return send_message_to_user(
        user_id=user_id,
        chat_id=chat_id,
        message=message,
        platform=platform,
        message_type="progress",
    )


def ask_for_feedback(
    user_id: str,
    chat_id: str,
    feedback_question: str,
    context: Optional[str] = None,
    platform: CommunicationChannel = CommunicationChannel.AUTO,
) -> Dict[str, Any]:
    """
    Ask user for feedback on work completed or decisions made.

    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        feedback_question: Question to ask for feedback
        context: Optional context about what feedback is needed on
        platform: Platform to use (default: AUTO)

    Returns:
        Result dictionary from send_message_to_user
    """
    message = f"💬 **Feedback Requested**\n\n{feedback_question}"
    if context:
        message += f"\n\n_Context: {context}_"

    return send_message_to_user(
        user_id=user_id,
        chat_id=chat_id,
        message=message,
        platform=platform,
        message_type="feedback_request",
    )


def send_grouped_messages(
    user_id: str,
    chat_id: str,
    messages: List[str],
    message_types: Optional[List[str]] = None,
    platform: CommunicationChannel = CommunicationChannel.AUTO,
    require_service_stopped: bool = True,
    time_window: int = 30,
    max_length: int = 3500,
    max_messages: int = 5,
) -> Dict[str, Any]:
    """
    Send multiple messages, grouping them when possible.

    This function attempts to group multiple messages into a single message
    when they meet grouping criteria (time window, length, count). If grouping
    is not possible, sends messages in small groups (2-3 max).

    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        messages: List of message texts to send
        message_types: Optional list of message types (defaults to "text" for all)
        platform: Platform to use (default: AUTO)
        require_service_stopped: If True, raise error if service is running
        time_window: Time window in seconds for grouping (default: 30)
        max_length: Maximum length for grouped message (default: 3500)
        max_messages: Maximum messages to group (default: 5)

    Returns:
        Dictionary with result:
        - success: Whether all messages were sent successfully
        - platform: Platform used
        - message_ids: List of message IDs sent
        - grouped: Whether messages were grouped
        - error: Error message if failed
    """
    if not messages:
        return {
            "success": True,
            "platform": None,
            "message_ids": [],
            "grouped": False,
            "error": None,
        }

    if message_types is None:
        message_types = ["text"] * len(messages)

    # Determine platform
    if platform == CommunicationChannel.AUTO:
        if _can_use_telegram(require_service_stopped):
            platform = CommunicationChannel.TELEGRAM
        elif _can_use_discord(require_service_stopped):
            platform = CommunicationChannel.DISCORD
        else:
            raise ChannelUnavailableError(
                "No communication channel available. Telegram and Discord services may be running "
                "or not configured. Disable services before using agent communication."
            )

    # Check service status
    if require_service_stopped:
        is_stopped, error_message = verify_service_stopped_for_platform(platform)
        if not is_stopped:
            raise ServiceRunningError(error_message)

    # Try to group messages
    grouped = group_messages(
        messages, message_types, time_window, max_length, max_messages
    )

    if grouped.can_group and len(grouped.messages) == 1:
        # Send as single grouped message
        platform_str = (
            platform.value if isinstance(platform, CommunicationChannel) else platform
        )
        formatted = format_grouped_message(messages, message_types, platform_str)

        # Split if too long
        max_platform_length = (
            4096 if platform == CommunicationChannel.TELEGRAM else 2000
        )
        parts = split_if_too_long(formatted, max_platform_length, platform_str)

        message_ids = []
        for part in parts:
            result = send_message_to_user(
                user_id=user_id,
                chat_id=chat_id,
                message=part,
                platform=platform,
                message_type="grouped",
                require_service_stopped=require_service_stopped,
            )
            if result.get("success"):
                message_ids.append(result.get("message_id"))
            else:
                return {
                    "success": False,
                    "platform": platform.value
                    if isinstance(platform, CommunicationChannel)
                    else platform,
                    "message_ids": message_ids,
                    "grouped": True,
                    "error": result.get("error"),
                }

        return {
            "success": True,
            "platform": platform.value
            if isinstance(platform, CommunicationChannel)
            else platform,
            "message_ids": message_ids,
            "grouped": True,
            "error": None,
        }
    else:
        # Send in small groups (2-3 max) or individually
        message_ids = []
        chunk_size = 2  # Send 2-3 messages per group

        for i in range(0, len(messages), chunk_size):
            chunk = messages[i : i + chunk_size]
            chunk_types = message_types[i : i + chunk_size]

            if len(chunk) > 1:
                # Try to group this chunk
                chunk_grouped = group_messages(
                    chunk, chunk_types, time_window, max_length, max_messages
                )
                if chunk_grouped.can_group:
                    platform_str = (
                        platform.value
                        if isinstance(platform, CommunicationChannel)
                        else platform
                    )
                    formatted = format_grouped_message(chunk, chunk_types, platform_str)
                    result = send_message_to_user(
                        user_id=user_id,
                        chat_id=chat_id,
                        message=formatted,
                        platform=platform,
                        message_type="grouped",
                        require_service_stopped=require_service_stopped,
                    )
                    if result.get("success"):
                        message_ids.append(result.get("message_id"))
                    else:
                        return {
                            "success": False,
                            "platform": platform.value
                            if isinstance(platform, CommunicationChannel)
                            else platform,
                            "message_ids": message_ids,
                            "grouped": False,
                            "error": result.get("error"),
                        }
                else:
                    # Send individually
                    for msg, msg_type in zip(chunk, chunk_types):
                        result = send_message_to_user(
                            user_id=user_id,
                            chat_id=chat_id,
                            message=msg,
                            platform=platform,
                            message_type=msg_type,
                            require_service_stopped=require_service_stopped,
                        )
                        if result.get("success"):
                            message_ids.append(result.get("message_id"))
                        else:
                            return {
                                "success": False,
                                "platform": platform.value
                                if isinstance(platform, CommunicationChannel)
                                else platform,
                                "message_ids": message_ids,
                                "grouped": False,
                                "error": result.get("error"),
                            }
            else:
                # Single message
                result = send_message_to_user(
                    user_id=user_id,
                    chat_id=chat_id,
                    message=chunk[0],
                    platform=platform,
                    message_type=chunk_types[0],
                    require_service_stopped=require_service_stopped,
                )

            if result.get("success"):
                message_ids.append(result.get("message_id"))
            else:
                return {
                    "success": False,
                    "platform": platform.value
                    if isinstance(platform, CommunicationChannel)
                    else platform,
                    "message_ids": message_ids,
                    "grouped": False,
                    "error": result.get("error"),
                }

        return {
            "success": True,
            "platform": platform.value
            if isinstance(platform, CommunicationChannel)
            else platform,
            "message_ids": message_ids,
            "grouped": len(messages) > 1
            and any(
                group_messages(
                    messages[i : i + chunk_size],
                    message_types[i : i + chunk_size] if message_types else None,
                    time_window,
                    max_length,
                    max_messages,
                ).can_group
                for i in range(0, len(messages), chunk_size)
            ),
            "error": None,
        }
