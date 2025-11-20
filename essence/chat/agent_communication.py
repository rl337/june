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

    # Check service status
    if platform == CommunicationChannel.TELEGRAM:
        if require_service_stopped and check_telegram_service_running():
            raise ServiceRunningError(
                "Telegram service is running. Disable it before using agent communication "
                "to prevent race conditions. Run: docker compose stop telegram"
            )
        return _send_telegram_message(user_id, chat_id, message, message_type)
    elif platform == CommunicationChannel.DISCORD:
        if require_service_stopped and check_discord_service_running():
            raise ServiceRunningError(
                "Discord service is running. Disable it before using agent communication "
                "to prevent race conditions. Run: docker compose stop discord"
            )
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
                                platform="telegram",
                                user_id=user_id,
                                limit=1
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
                            status="Responded" if message_type in ["response", "progress"] else "Pending",
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
                        platform="discord",
                        user_id=user_id,
                        limit=1
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
                    status="Responded" if message_type in ["response", "progress"] else "Pending",
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
