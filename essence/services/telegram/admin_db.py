"""Admin database operations for Telegram bot."""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# PostgreSQL is not available - all database operations are disabled
# All functions return safe defaults (fail open)


def is_user_blocked(user_id: str) -> bool:
    """
    Check if a user is blocked.

    Args:
        user_id: Telegram user ID as string

    Returns:
        True if user is blocked, False otherwise

    Note: PostgreSQL is not available, so this always returns False (fail open).
    """
    # PostgreSQL is not available - always return False (fail open)
    # No database connection attempted - just return False
    return False


def block_user(user_id: str, blocked_by: str, reason: Optional[str] = None) -> bool:
    """
    Block a user from using the bot.

    Args:
        user_id: Telegram user ID to block
        blocked_by: Admin user ID who is blocking
        reason: Optional reason for blocking

    Returns:
        True if user was blocked, False if already blocked

    Note: PostgreSQL is not available - always returns False.
    """
    logger.warning(f"PostgreSQL not available - cannot block user {user_id}")
    return False


def unblock_user(user_id: str) -> bool:
    """
    Unblock a user.

    Args:
        user_id: Telegram user ID to unblock

    Returns:
        True if user was unblocked, False if not found

    Note: PostgreSQL is not available - always returns False.
    """
    logger.warning(f"PostgreSQL not available - cannot unblock user {user_id}")
    return False


def get_blocked_users() -> List[Dict[str, Any]]:
    """
    Get list of all blocked users.

    Returns:
        List of blocked user dictionaries

    Note: PostgreSQL is not available - always returns empty list.
    """
    logger.debug("PostgreSQL not available - returning empty blocked users list")
    return []


def clear_conversation(conversation_id: str) -> bool:
    """
    Clear all messages from a conversation.

    Args:
        conversation_id: Conversation UUID

    Returns:
        True if conversation was cleared, False otherwise

    Note: PostgreSQL is not available - always returns False.
    """
    logger.warning(
        f"PostgreSQL not available - cannot clear conversation {conversation_id}"
    )
    return False


def clear_user_conversations(user_id: str) -> int:
    """
    Clear all conversations for a user.

    Args:
        user_id: Telegram user ID

    Returns:
        Number of conversations cleared

    Note: PostgreSQL is not available - always returns 0.
    """
    logger.warning(
        f"PostgreSQL not available - cannot clear conversations for user {user_id}"
    )
    return 0


def log_audit_action(
    action: str,
    actor_user_id: str,
    target_user_id: Optional[str] = None,
    target_conversation_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> bool:
    """
    Log an admin action to audit log.

    Args:
        action: Action name (e.g., 'user_blocked', 'conversation_cleared')
        actor_user_id: Admin user ID who performed the action
        target_user_id: Target user ID (if applicable)
        target_conversation_id: Target conversation ID (if applicable)
        details: Additional action details as dict
        ip_address: IP address of the actor

    Returns:
        True if audit log was created

    Note: PostgreSQL is not available - always returns False (logs to logger instead).
    """
    logger.info(
        f"Audit log (PostgreSQL unavailable): action={action}, actor={actor_user_id}, target={target_user_id}, conversation={target_conversation_id}"
    )
    return False


def get_audit_logs(
    limit: int = 100, action: Optional[str] = None, actor_user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get audit logs.

    Args:
        limit: Maximum number of logs to return
        action: Filter by action type
        actor_user_id: Filter by actor user ID

    Returns:
        List of audit log dictionaries

    Note: PostgreSQL is not available - always returns empty list.
    """
    logger.debug("PostgreSQL not available - returning empty audit logs list")
    return []
