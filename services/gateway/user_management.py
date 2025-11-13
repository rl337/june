"""User management module for admin dashboard."""
import os
import logging
import json
import psycopg2
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor
from datetime import datetime
from db_pool import get_db_pool

logger = logging.getLogger(__name__)


def get_users(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get list of users with pagination, search, and filtering.
    
    Args:
        page: Page number (1-indexed)
        page_size: Number of users per page
        search: Search term for user_id
        status: Filter by status ('active', 'blocked', 'suspended')
        
    Returns:
        Dictionary with users list, total count, page, and page_size
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build WHERE clause
            where_clauses = []
            params = []
            
            if search:
                where_clauses.append("c.user_id ILIKE %s")
                params.append(f"%{search}%")
            
            if status == "blocked":
                where_clauses.append("EXISTS (SELECT 1 FROM blocked_users WHERE user_id = c.user_id)")
            elif status == "active":
                where_clauses.append("NOT EXISTS (SELECT 1 FROM blocked_users WHERE user_id = c.user_id)")
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            count_query = f"""
                SELECT COUNT(DISTINCT c.user_id) as total
                FROM conversations c
                WHERE {where_sql}
            """
            cursor.execute(count_query, params)
            total = cursor.fetchone()['total']
            
            # Get users with pagination
            offset = (page - 1) * page_size
            users_query = f"""
                SELECT DISTINCT
                    c.user_id,
                    COUNT(DISTINCT c.id) as conversation_count,
                    MIN(c.created_at) as first_seen,
                    MAX(c.updated_at) as last_active,
                    COUNT(DISTINCT m.id) as message_count,
                    CASE 
                        WHEN EXISTS (SELECT 1 FROM blocked_users WHERE user_id = c.user_id) 
                        THEN 'blocked'
                        WHEN EXISTS (SELECT 1 FROM admin_users WHERE user_id = c.user_id)
                        THEN 'admin'
                        ELSE 'active'
                    END as status
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE {where_sql}
                GROUP BY c.user_id
                ORDER BY MAX(c.updated_at) DESC
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])
            cursor.execute(users_query, params)
            users = [dict(row) for row in cursor.fetchall()]
            
            return {
                "users": users,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
    except Exception as e:
        logger.error(f"Error getting users: {e}", exc_info=True)
        raise


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a user.
    
    Args:
        user_id: User ID
        
    Returns:
        User details dictionary or None if not found
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get user basic info
            cursor.execute("""
                SELECT DISTINCT
                    c.user_id,
                    COUNT(DISTINCT c.id) as conversation_count,
                    MIN(c.created_at) as first_seen,
                    MAX(c.updated_at) as last_active,
                    COUNT(DISTINCT m.id) as message_count,
                    CASE 
                        WHEN EXISTS (SELECT 1 FROM blocked_users WHERE user_id = c.user_id) 
                        THEN 'blocked'
                        WHEN EXISTS (SELECT 1 FROM admin_users WHERE user_id = c.user_id)
                        THEN 'admin'
                        ELSE 'active'
                    END as status
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.user_id = %s
                GROUP BY c.user_id
            """, (str(user_id),))
            
            user = cursor.fetchone()
            if not user:
                return None
            
            user_dict = dict(user)
            
            # Get blocked user info if blocked
            if user_dict['status'] == 'blocked':
                cursor.execute("""
                    SELECT blocked_by, reason, created_at, updated_at
                    FROM blocked_users
                    WHERE user_id = %s
                """, (str(user_id),))
                blocked_info = cursor.fetchone()
                if blocked_info:
                    user_dict['blocked_info'] = dict(blocked_info)
            
            # Get admin info if admin
            if user_dict['status'] == 'admin':
                cursor.execute("""
                    SELECT created_at
                    FROM admin_users
                    WHERE user_id = %s
                """, (str(user_id),))
                admin_info = cursor.fetchone()
                if admin_info:
                    user_dict['admin_info'] = dict(admin_info)
            
            # Get recent conversations
            cursor.execute("""
                SELECT id, session_id, created_at, updated_at, metadata
                FROM conversations
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT 10
            """, (str(user_id),))
            conversations = [dict(row) for row in cursor.fetchall()]
            user_dict['recent_conversations'] = conversations
            
            return user_dict
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}", exc_info=True)
        raise


def create_user(user_id: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """
    Create a new user (creates a placeholder conversation).
    
    Note: Users are typically created automatically when they first interact.
    This function creates a placeholder conversation to register the user.
    
    Args:
        user_id: User ID
        metadata: Optional user metadata
        
    Returns:
        True if user was created
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Create a placeholder conversation to register the user
            cursor.execute("""
                INSERT INTO conversations (user_id, session_id, metadata)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT DO NOTHING
            """, (str(user_id), f"admin_created_{datetime.now().isoformat()}", 
                  json.dumps(metadata) if metadata else None))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}", exc_info=True)
        return False


def update_user_status(user_id: str, status: str, actor_user_id: str, reason: Optional[str] = None) -> bool:
    """
    Update user status (active, blocked, suspended).
    
    Args:
        user_id: User ID to update
        status: New status ('active', 'blocked', 'suspended')
        actor_user_id: Admin user ID performing the action
        reason: Optional reason for status change
        
    Returns:
        True if status was updated
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            if status == 'blocked':
                # Block user
                cursor.execute("""
                    INSERT INTO blocked_users (user_id, blocked_by, reason)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET blocked_by = EXCLUDED.blocked_by,
                        reason = EXCLUDED.reason,
                        updated_at = NOW()
                """, (str(user_id), str(actor_user_id), reason))
            elif status == 'active':
                # Unblock user
                cursor.execute("""
                    DELETE FROM blocked_users WHERE user_id = %s
                """, (str(user_id),))
            # Note: 'suspended' can be implemented as a special case of blocked
            # or as a separate table if needed
            
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error updating user status {user_id}: {e}", exc_info=True)
        return False


def delete_user(user_id: str, actor_user_id: str) -> bool:
    """
    Delete a user and all their data.
    
    Args:
        user_id: User ID to delete
        actor_user_id: Admin user ID performing the action
        
    Returns:
        True if user was deleted
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Delete all conversations (cascade will delete messages)
            cursor.execute("""
                DELETE FROM conversations WHERE user_id = %s
            """, (str(user_id),))
            
            # Delete from blocked_users if present
            cursor.execute("""
                DELETE FROM blocked_users WHERE user_id = %s
            """, (str(user_id),))
            
            # Note: We don't delete from admin_users here - that should be done separately
            
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        return False


def get_user_statistics() -> Dict[str, Any]:
    """
    Get user statistics.
    
    Returns:
        Dictionary with user statistics
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Total users
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as total_users
                FROM conversations
            """)
            total_users = cursor.fetchone()['total_users']
            
            # Active users (users with activity in last 30 days)
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as active_users
                FROM conversations
                WHERE updated_at >= NOW() - INTERVAL '30 days'
            """)
            active_users = cursor.fetchone()['active_users']
            
            # New users (users created in last 30 days)
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as new_users
                FROM conversations
                WHERE created_at >= NOW() - INTERVAL '30 days'
            """)
            new_users = cursor.fetchone()['new_users']
            
            # Blocked users
            cursor.execute("""
                SELECT COUNT(*) as blocked_users
                FROM blocked_users
            """)
            blocked_users = cursor.fetchone()['blocked_users']
            
            # Admin users
            cursor.execute("""
                SELECT COUNT(*) as admin_users
                FROM admin_users
            """)
            admin_users = cursor.fetchone()['admin_users']
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "new_users": new_users,
                "blocked_users": blocked_users,
                "admin_users": admin_users
            }
    except Exception as e:
        logger.error(f"Error getting user statistics: {e}", exc_info=True)
        raise
