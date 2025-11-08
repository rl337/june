"""Admin database operations for Telegram bot."""
import os
import logging
import psycopg2
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor
from datetime import datetime

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


def is_user_blocked(user_id: str) -> bool:
    """
    Check if a user is blocked.
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        True if user is blocked, False otherwise
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM blocked_users WHERE user_id = %s",
                (str(user_id),)
            )
            result = cursor.fetchone()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error checking if user {user_id} is blocked: {e}", exc_info=True)
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
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO blocked_users (user_id, blocked_by, reason)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET blocked_by = EXCLUDED.blocked_by,
                    reason = EXCLUDED.reason,
                    updated_at = NOW()
                RETURNING id
                """,
                (str(user_id), str(blocked_by), reason)
            )
            result = cursor.fetchone()
            conn.commit()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error blocking user {user_id}: {e}", exc_info=True)
        return False


def unblock_user(user_id: str) -> bool:
    """
    Unblock a user.
    
    Args:
        user_id: Telegram user ID to unblock
        
    Returns:
        True if user was unblocked, False if not found
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM blocked_users WHERE user_id = %s RETURNING id",
                (str(user_id),)
            )
            result = cursor.fetchone()
            conn.commit()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error unblocking user {user_id}: {e}", exc_info=True)
        return False


def get_blocked_users() -> List[Dict[str, Any]]:
    """
    Get list of all blocked users.
    
    Returns:
        List of blocked user dictionaries
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT user_id, blocked_by, reason, created_at, updated_at
                FROM blocked_users
                ORDER BY created_at DESC
                """
            )
            results = cursor.fetchall()
            return [dict(row) for row in results]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting blocked users: {e}", exc_info=True)
        return []


def clear_conversation(conversation_id: str) -> bool:
    """
    Clear all messages from a conversation.
    
    Args:
        conversation_id: Conversation UUID
        
    Returns:
        True if conversation was cleared, False otherwise
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Delete all messages in the conversation
            cursor.execute(
                "DELETE FROM messages WHERE conversation_id = %s",
                (conversation_id,)
            )
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count > 0
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error clearing conversation {conversation_id}: {e}", exc_info=True)
        return False


def clear_user_conversations(user_id: str) -> int:
    """
    Clear all conversations for a user.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Number of conversations cleared
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Get all conversation IDs for the user
            cursor.execute(
                "SELECT id FROM conversations WHERE user_id = %s",
                (str(user_id),)
            )
            conversation_ids = [row[0] for row in cursor.fetchall()]
            
            if not conversation_ids:
                return 0
            
            # Delete all messages in those conversations
            cursor.execute(
                "DELETE FROM messages WHERE conversation_id = ANY(%s)",
                (conversation_ids,)
            )
            deleted_count = cursor.rowcount
            
            # Optionally delete the conversations themselves
            cursor.execute(
                "DELETE FROM conversations WHERE user_id = %s",
                (str(user_id),)
            )
            conversation_count = cursor.rowcount
            
            conn.commit()
            return conversation_count
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error clearing conversations for user {user_id}: {e}", exc_info=True)
        return 0


def log_audit_action(
    action: str,
    actor_user_id: str,
    target_user_id: Optional[str] = None,
    target_conversation_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None
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
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            import json
            details_json = json.dumps(details) if details else None
            cursor.execute(
                """
                INSERT INTO audit_logs (
                    action, actor_user_id, target_user_id,
                    target_conversation_id, details, ip_address
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    action,
                    str(actor_user_id),
                    str(target_user_id) if target_user_id else None,
                    target_conversation_id,
                    details_json,
                    ip_address
                )
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error logging audit action {action}: {e}", exc_info=True)
        return False


def get_audit_logs(
    limit: int = 100,
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get audit logs.
    
    Args:
        limit: Maximum number of logs to return
        action: Filter by action type
        actor_user_id: Filter by actor user ID
        
    Returns:
        List of audit log dictionaries
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            query = """
                SELECT action, actor_user_id, target_user_id, target_conversation_id,
                       details, ip_address, created_at
                FROM audit_logs
                WHERE 1=1
            """
            params = []
            
            if action:
                query += " AND action = %s"
                params.append(action)
            
            if actor_user_id:
                query += " AND actor_user_id = %s"
                params.append(str(actor_user_id))
            
            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [dict(row) for row in results]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting audit logs: {e}", exc_info=True)
        return []
