"""Conversation management module for admin dashboard."""
import os
import logging
import json
import psycopg2
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor
from datetime import datetime
from db_pool import get_db_pool

logger = logging.getLogger(__name__)


def get_conversations(
    page: int = 1,
    page_size: int = 20,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get list of conversations with pagination, search, and filtering.
    
    Args:
        page: Page number (1-indexed)
        page_size: Number of conversations per page
        user_id: Filter by user ID
        search: Search term for user_id or message content
        start_date: Filter conversations created after this date
        end_date: Filter conversations created before this date
        status: Filter by status (not used currently, reserved for future)
        
    Returns:
        Dictionary with conversations list, total count, page, and page_size
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build WHERE clause
            where_clauses = []
            params = []
            
            if user_id:
                where_clauses.append("c.user_id = %s")
                params.append(str(user_id))
            
            if search:
                # Search in user_id or message content
                where_clauses.append("""
                    (c.user_id ILIKE %s OR 
                     EXISTS (
                         SELECT 1 FROM messages m 
                         WHERE m.conversation_id = c.id 
                         AND m.content ILIKE %s
                     ))
                """)
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])
            
            if start_date:
                where_clauses.append("c.created_at >= %s")
                params.append(start_date)
            
            if end_date:
                where_clauses.append("c.created_at <= %s")
                params.append(end_date)
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            count_query = f"""
                SELECT COUNT(DISTINCT c.id) as total
                FROM conversations c
                WHERE {where_sql}
            """
            cursor.execute(count_query, params)
            total = cursor.fetchone()['total']
            
            # Get conversations with pagination
            offset = (page - 1) * page_size
            conversations_query = f"""
                SELECT 
                    c.id,
                    c.user_id,
                    c.session_id,
                    c.created_at,
                    c.updated_at,
                    c.metadata,
                    COUNT(DISTINCT m.id) as message_count,
                    MIN(m.created_at) as first_message_at,
                    MAX(m.created_at) as last_message_at
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE {where_sql}
                GROUP BY c.id, c.user_id, c.session_id, c.created_at, c.updated_at, c.metadata
                ORDER BY c.updated_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])
            cursor.execute(conversations_query, params)
            conversations = [dict(row) for row in cursor.fetchall()]
            
            return {
                "conversations": conversations,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
    except Exception as e:
        logger.error(f"Error getting conversations: {e}", exc_info=True)
        raise


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a conversation including all messages.
    
    Args:
        conversation_id: Conversation ID (UUID)
        
    Returns:
        Conversation details dictionary with messages or None if not found
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get conversation basic info
            cursor.execute("""
                SELECT 
                    c.id,
                    c.user_id,
                    c.session_id,
                    c.created_at,
                    c.updated_at,
                    c.metadata,
                    COUNT(DISTINCT m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.id = %s
                GROUP BY c.id, c.user_id, c.session_id, c.created_at, c.updated_at, c.metadata
            """, (conversation_id,))
            
            conversation = cursor.fetchone()
            if not conversation:
                return None
            
            conversation_dict = dict(conversation)
            
            # Get all messages for this conversation
            cursor.execute("""
                SELECT 
                    id,
                    role,
                    content,
                    created_at,
                    metadata
                FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at ASC
            """, (conversation_id,))
            messages = [dict(row) for row in cursor.fetchall()]
            conversation_dict['messages'] = messages
            
            return conversation_dict
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {e}", exc_info=True)
        raise


def search_conversations(
    query: str,
    page: int = 1,
    page_size: int = 20,
    user_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Search conversations by user, message content, or date.
    
    Args:
        query: Search query string
        page: Page number (1-indexed)
        page_size: Number of conversations per page
        user_id: Filter by user ID
        start_date: Filter conversations created after this date
        end_date: Filter conversations created before this date
        
    Returns:
        Dictionary with matching conversations list, total count, page, and page_size
    """
    return get_conversations(
        page=page,
        page_size=page_size,
        user_id=user_id,
        search=query,
        start_date=start_date,
        end_date=end_date
    )


def delete_conversation(conversation_id: str, actor_user_id: str) -> bool:
    """
    Delete a conversation and all its messages.
    
    Args:
        conversation_id: Conversation ID to delete
        actor_user_id: Admin user ID performing the action
        
    Returns:
        True if conversation was deleted
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Delete conversation (cascade will delete messages)
            cursor.execute("""
                DELETE FROM conversations WHERE id = %s
            """, (conversation_id,))
            
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True)
        return False


def get_conversation_statistics() -> Dict[str, Any]:
    """
    Get conversation statistics.
    
    Returns:
        Dictionary with conversation statistics
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Total conversations
            cursor.execute("""
                SELECT COUNT(*) as total_conversations
                FROM conversations
            """)
            total_conversations = cursor.fetchone()['total_conversations']
            
            # Active conversations (updated in last 7 days)
            cursor.execute("""
                SELECT COUNT(*) as active_conversations
                FROM conversations
                WHERE updated_at >= NOW() - INTERVAL '7 days'
            """)
            active_conversations = cursor.fetchone()['active_conversations']
            
            # Total messages
            cursor.execute("""
                SELECT COUNT(*) as total_messages
                FROM messages
            """)
            total_messages = cursor.fetchone()['total_messages']
            
            # Average conversation length (messages per conversation)
            cursor.execute("""
                SELECT 
                    AVG(message_count) as avg_length
                FROM (
                    SELECT 
                        conversation_id,
                        COUNT(*) as message_count
                    FROM messages
                    GROUP BY conversation_id
                ) subq
            """)
            avg_length_result = cursor.fetchone()
            avg_length = float(avg_length_result['avg_length']) if avg_length_result['avg_length'] else 0.0
            
            return {
                "total_conversations": total_conversations,
                "active_conversations": active_conversations,
                "total_messages": total_messages,
                "average_length": round(avg_length, 2)
            }
    except Exception as e:
        logger.error(f"Error getting conversation statistics: {e}", exc_info=True)
        raise
