"""Admin authentication module for Telegram bot."""
import logging

logger = logging.getLogger(__name__)


def get_db_connection() -> None:
    """
    Get PostgreSQL database connection.
    
    Note: PostgreSQL is not available. This function will raise an exception
    if called. All methods in this module handle this gracefully.
    
    Raises:
        RuntimeError: Always raised since PostgreSQL is not available for MVP
    """
    # PostgreSQL is not available - raise an exception that will be caught by callers
    raise RuntimeError("PostgreSQL is not available. Admin auth methods will return defaults.")


def is_admin(user_id: str) -> bool:
    """
    Check if a user is an admin.
    
    Note: PostgreSQL is not available, so this always returns False (fail open).
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        False (PostgreSQL not available)
    """
    # PostgreSQL is not available - always return False (fail open)
    logger.debug(f"PostgreSQL not available - cannot check admin status for user {user_id}")
    return False


def require_admin(user_id: str) -> bool:
    """
    Check if user is admin, raise exception if not.
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        True if user is admin
        
    Raises:
        PermissionError: If user is not an admin
    """
    if not is_admin(user_id):
        raise PermissionError(f"User {user_id} is not authorized to perform admin actions")
    return True


def add_admin(user_id: str) -> bool:
    """
    Add a user as admin.
    
    Note: PostgreSQL is not available, so this always returns False.
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        False (PostgreSQL not available)
    """
    logger.warning(f"PostgreSQL not available - cannot add admin user {user_id}")
    return False


def remove_admin(user_id: str) -> bool:
    """
    Remove a user from admin list.
    
    Note: PostgreSQL is not available, so this always returns False.
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        False (PostgreSQL not available)
    """
    logger.warning(f"PostgreSQL not available - cannot remove admin user {user_id}")
    return False


def list_admins() -> list[str]:
    """
    List all admin user IDs.
    
    Note: PostgreSQL is not available, so this always returns empty list.
    
    Returns:
        Empty list (PostgreSQL not available)
    """
    logger.debug("PostgreSQL not available - returning empty admin list")
    return []
