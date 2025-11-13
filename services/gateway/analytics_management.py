"""Analytics management module for admin dashboard."""
import os
import logging
import psycopg2
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from db_pool import get_db_pool

logger = logging.getLogger(__name__)


def get_user_analytics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get user analytics including user growth, active users, and retention.
    
    Args:
        start_date: Start date filter
        end_date: End date filter
        
    Returns:
        Dictionary with user analytics data
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build WHERE clause for date filtering
            where_clauses = []
            params = []
            
            if start_date:
                where_clauses.append("c.created_at >= %s")
                params.append(start_date)
            
            if end_date:
                where_clauses.append("c.created_at <= %s")
                params.append(end_date)
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Total users
            cursor.execute(f"""
                SELECT COUNT(DISTINCT user_id) as total_users
                FROM conversations c
                WHERE {where_sql}
            """, params)
            total_users = cursor.fetchone()['total_users']
            
            # Active users (users with activity in last 7 days)
            seven_days_ago = datetime.now() - timedelta(days=7)
            active_params = params.copy()
            active_where = where_clauses.copy()
            active_where.append("c.updated_at >= %s")
            active_params.append(seven_days_ago)
            active_where_sql = " AND ".join(active_where)
            
            cursor.execute(f"""
                SELECT COUNT(DISTINCT user_id) as active_users
                FROM conversations c
                WHERE {active_where_sql}
            """, active_params)
            active_users = cursor.fetchone()['active_users']
            
            # User growth over time (daily for last 30 days)
            growth_params = params.copy()
            growth_where = where_clauses.copy()
            thirty_days_ago = datetime.now() - timedelta(days=30)
            growth_where.append("c.created_at >= %s")
            growth_params.append(thirty_days_ago)
            growth_where_sql = " AND ".join(growth_where)
            
            cursor.execute(f"""
                SELECT 
                    DATE(c.created_at) as date,
                    COUNT(DISTINCT user_id) as new_users
                FROM conversations c
                WHERE {growth_where_sql}
                GROUP BY DATE(c.created_at)
                ORDER BY date ASC
            """, growth_params)
            user_growth = [dict(row) for row in cursor.fetchall()]
            
            # Active users over time (daily for last 30 days)
            cursor.execute(f"""
                SELECT 
                    DATE(c.updated_at) as date,
                    COUNT(DISTINCT user_id) as active_users
                FROM conversations c
                WHERE {growth_where_sql}
                GROUP BY DATE(c.updated_at)
                ORDER BY date ASC
            """, growth_params)
            active_users_over_time = [dict(row) for row in cursor.fetchall()]
            
            # User retention (users who returned after first visit)
            cursor.execute(f"""
                WITH first_visit AS (
                    SELECT user_id, MIN(created_at) as first_visit_date
                    FROM conversations
                    WHERE {where_sql}
                    GROUP BY user_id
                ),
                return_visits AS (
                    SELECT 
                        fv.user_id,
                        COUNT(DISTINCT DATE(c.created_at)) as visit_count
                    FROM first_visit fv
                    JOIN conversations c ON c.user_id = fv.user_id
                    WHERE c.created_at > fv.first_visit_date
                    GROUP BY fv.user_id
                )
                SELECT 
                    COUNT(CASE WHEN rv.visit_count > 0 THEN 1 END) as returning_users,
                    COUNT(fv.user_id) as total_users
                FROM first_visit fv
                LEFT JOIN return_visits rv ON rv.user_id = fv.user_id
            """, params)
            retention_data = cursor.fetchone()
            retention_rate = (retention_data['returning_users'] / retention_data['total_users'] * 100) if retention_data['total_users'] > 0 else 0
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "user_growth": user_growth,
                "active_users_over_time": active_users_over_time,
                "retention_rate": round(retention_rate, 2)
            }
    except Exception as e:
        logger.error(f"Error getting user analytics: {e}", exc_info=True)
        raise


def get_conversation_analytics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get conversation analytics including total conversations, average length, and peak usage.
    
    Args:
        start_date: Start date filter
        end_date: End date filter
        
    Returns:
        Dictionary with conversation analytics data
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build WHERE clause for date filtering
            where_clauses = []
            params = []
            
            if start_date:
                where_clauses.append("c.created_at >= %s")
                params.append(start_date)
            
            if end_date:
                where_clauses.append("c.created_at <= %s")
                params.append(end_date)
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Total conversations
            cursor.execute(f"""
                SELECT COUNT(*) as total_conversations
                FROM conversations c
                WHERE {where_sql}
            """, params)
            total_conversations = cursor.fetchone()['total_conversations']
            
            # Average conversation length (number of messages per conversation)
            cursor.execute(f"""
                SELECT 
                    AVG(message_count) as avg_length,
                    MIN(message_count) as min_length,
                    MAX(message_count) as max_length
                FROM (
                    SELECT 
                        c.id,
                        COUNT(m.id) as message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE {where_sql}
                    GROUP BY c.id
                ) as conv_lengths
            """, params)
            length_stats = cursor.fetchone()
            
            # Peak usage times (by hour of day)
            cursor.execute(f"""
                SELECT 
                    EXTRACT(HOUR FROM c.created_at) as hour,
                    COUNT(*) as conversation_count
                FROM conversations c
                WHERE {where_sql}
                GROUP BY EXTRACT(HOUR FROM c.created_at)
                ORDER BY hour ASC
            """, params)
            peak_usage = [dict(row) for row in cursor.fetchall()]
            
            # Conversations over time (daily)
            cursor.execute(f"""
                SELECT 
                    DATE(c.created_at) as date,
                    COUNT(*) as conversation_count
                FROM conversations c
                WHERE {where_sql}
                GROUP BY DATE(c.created_at)
                ORDER BY date ASC
            """, params)
            conversations_over_time = [dict(row) for row in cursor.fetchall()]
            
            return {
                "total_conversations": total_conversations,
                "average_length": round(float(length_stats['avg_length'] or 0), 2),
                "min_length": int(length_stats['min_length'] or 0),
                "max_length": int(length_stats['max_length'] or 0),
                "peak_usage_times": peak_usage,
                "conversations_over_time": conversations_over_time
            }
    except Exception as e:
        logger.error(f"Error getting conversation analytics: {e}", exc_info=True)
        raise


def get_bot_performance_analytics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get bot performance analytics including response times, error rates, and success rates.
    
    Args:
        start_date: Start date filter
        end_date: End date filter
        
    Returns:
        Dictionary with bot performance analytics data
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build WHERE clause for date filtering
            where_clauses = []
            params = []
            
            if start_date:
                where_clauses.append("m.created_at >= %s")
                params.append(start_date)
            
            if end_date:
                where_clauses.append("m.created_at <= %s")
                params.append(end_date)
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Total messages
            cursor.execute(f"""
                SELECT COUNT(*) as total_messages
                FROM messages m
                WHERE {where_sql}
            """, params)
            total_messages = cursor.fetchone()['total_messages']
            
            # Response times (for assistant messages)
            cursor.execute(f"""
                SELECT 
                    AVG(EXTRACT(EPOCH FROM (m.created_at - prev_msg.created_at))) as avg_response_time,
                    MIN(EXTRACT(EPOCH FROM (m.created_at - prev_msg.created_at))) as min_response_time,
                    MAX(EXTRACT(EPOCH FROM (m.created_at - prev_msg.created_at))) as max_response_time
                FROM messages m
                JOIN messages prev_msg ON prev_msg.conversation_id = m.conversation_id
                    AND prev_msg.role = 'user'
                    AND prev_msg.created_at < m.created_at
                    AND NOT EXISTS (
                        SELECT 1 FROM messages m2
                        WHERE m2.conversation_id = m.conversation_id
                        AND m2.role = 'user'
                        AND m2.created_at > prev_msg.created_at
                        AND m2.created_at < m.created_at
                    )
                WHERE m.role = 'assistant'
                AND {where_sql}
            """, params)
            response_time_stats = cursor.fetchone()
            
            # Error rate (messages with error content or failed status)
            cursor.execute(f"""
                SELECT 
                    COUNT(CASE WHEN m.content ILIKE '%error%' OR m.content ILIKE '%failed%' THEN 1 END) as error_count,
                    COUNT(*) as total_messages
                FROM messages m
                WHERE m.role = 'assistant'
                AND {where_sql}
            """, params)
            error_stats = cursor.fetchone()
            error_rate = (error_stats['error_count'] / error_stats['total_messages'] * 100) if error_stats['total_messages'] > 0 else 0
            
            # Success rate (inverse of error rate)
            success_rate = 100 - error_rate
            
            # Response times over time (daily average)
            cursor.execute(f"""
                SELECT 
                    DATE(m.created_at) as date,
                    AVG(EXTRACT(EPOCH FROM (m.created_at - prev_msg.created_at))) as avg_response_time
                FROM messages m
                JOIN messages prev_msg ON prev_msg.conversation_id = m.conversation_id
                    AND prev_msg.role = 'user'
                    AND prev_msg.created_at < m.created_at
                    AND NOT EXISTS (
                        SELECT 1 FROM messages m2
                        WHERE m2.conversation_id = m.conversation_id
                        AND m2.role = 'user'
                        AND m2.created_at > prev_msg.created_at
                        AND m2.created_at < m.created_at
                    )
                WHERE m.role = 'assistant'
                AND {where_sql}
                GROUP BY DATE(m.created_at)
                ORDER BY date ASC
            """, params)
            response_times_over_time = [dict(row) for row in cursor.fetchall()]
            
            return {
                "total_messages": total_messages,
                "average_response_time": round(float(response_time_stats['avg_response_time'] or 0), 2),
                "min_response_time": round(float(response_time_stats['min_response_time'] or 0), 2),
                "max_response_time": round(float(response_time_stats['max_response_time'] or 0), 2),
                "error_rate": round(error_rate, 2),
                "success_rate": round(success_rate, 2),
                "response_times_over_time": response_times_over_time
            }
    except Exception as e:
        logger.error(f"Error getting bot performance analytics: {e}", exc_info=True)
        raise


def get_system_usage_analytics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get system usage analytics including API calls, service usage, and resource utilization.
    
    Args:
        start_date: Start date filter
        end_date: End date filter
        
    Returns:
        Dictionary with system usage analytics data
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build WHERE clause for date filtering
            where_clauses = []
            params = []
            
            if start_date:
                where_clauses.append("m.created_at >= %s")
                params.append(start_date)
            
            if end_date:
                where_clauses.append("m.created_at <= %s")
                params.append(end_date)
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Total API calls (approximated by total messages)
            cursor.execute(f"""
                SELECT COUNT(*) as total_api_calls
                FROM messages m
                WHERE {where_sql}
            """, params)
            total_api_calls = cursor.fetchone()['total_api_calls']
            
            # Service usage breakdown (by message role/type)
            cursor.execute(f"""
                SELECT 
                    m.role,
                    COUNT(*) as usage_count
                FROM messages m
                WHERE {where_sql}
                GROUP BY m.role
            """, params)
            service_usage = [dict(row) for row in cursor.fetchall()]
            
            # API calls over time (daily)
            cursor.execute(f"""
                SELECT 
                    DATE(m.created_at) as date,
                    COUNT(*) as api_calls
                FROM messages m
                WHERE {where_sql}
                GROUP BY DATE(m.created_at)
                ORDER BY date ASC
            """, params)
            api_calls_over_time = [dict(row) for row in cursor.fetchall()]
            
            # Resource utilization (conversations per user)
            # Build separate WHERE clause for conversations
            conv_where_clauses = []
            conv_params = []
            
            if start_date:
                conv_where_clauses.append("c.created_at >= %s")
                conv_params.append(start_date)
            
            if end_date:
                conv_where_clauses.append("c.created_at <= %s")
                conv_params.append(end_date)
            
            conv_where_sql = " AND ".join(conv_where_clauses) if conv_where_clauses else "1=1"
            
            cursor.execute(f"""
                SELECT 
                    AVG(conv_count) as avg_conversations_per_user,
                    MAX(conv_count) as max_conversations_per_user
                FROM (
                    SELECT 
                        user_id,
                        COUNT(*) as conv_count
                    FROM conversations c
                    WHERE {conv_where_sql}
                    GROUP BY user_id
                ) as user_convs
            """, conv_params)
            resource_utilization = cursor.fetchone()
            
            return {
                "total_api_calls": total_api_calls,
                "service_usage": service_usage,
                "api_calls_over_time": api_calls_over_time,
                "average_conversations_per_user": round(float(resource_utilization['avg_conversations_per_user'] or 0), 2),
                "max_conversations_per_user": int(resource_utilization['max_conversations_per_user'] or 0)
            }
    except Exception as e:
        logger.error(f"Error getting system usage analytics: {e}", exc_info=True)
        raise
