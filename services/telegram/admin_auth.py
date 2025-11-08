"""Admin authentication module for Telegram bot."""
import os
import logging
import psycopg2
from typing import Optional
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


def get_db_connection():
    """Get PostgreSQL database connection."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "conversations")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    
    conn_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
    if db_password:
        conn_string += f" password={db_password}"
    
    return psycopg2.connect(conn_string)


def is_admin(user_id: str) -> bool:
    """
    Check if a user is an admin.
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        True if user is admin, False otherwise
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM admin_users WHERE user_id = %s",
                (str(user_id),)
            )
            result = cursor.fetchone()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}", exc_info=True)
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
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        True if admin was added, False if already exists
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO admin_users (user_id)
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING
                RETURNING id
                """,
                (str(user_id),)
            )
            result = cursor.fetchone()
            conn.commit()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error adding admin user {user_id}: {e}", exc_info=True)
        return False


def remove_admin(user_id: str) -> bool:
    """
    Remove a user from admin list.
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        True if admin was removed, False if not found
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM admin_users WHERE user_id = %s RETURNING id",
                (str(user_id),)
            )
            result = cursor.fetchone()
            conn.commit()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error removing admin user {user_id}: {e}", exc_info=True)
        return False


def list_admins() -> list[str]:
    """
    List all admin user IDs.
    
    Returns:
        List of admin user IDs
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM admin_users ORDER BY created_at")
            results = cursor.fetchall()
            return [row[0] for row in results]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error listing admins: {e}", exc_info=True)
        return []
