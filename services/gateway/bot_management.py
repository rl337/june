"""Bot management module for admin dashboard."""
import os
import logging
import json
import psycopg2
import httpx
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor
from datetime import datetime, date
from db_pool import get_db_pool
from encryption_helpers import (
    encrypt_bot_token,
    decrypt_bot_token,
    ENCRYPTION_ENABLED
)

logger = logging.getLogger(__name__)


def get_bot_config() -> Optional[Dict[str, Any]]:
    """
    Get bot configuration.
    
    Returns:
        Bot configuration dictionary or None if not found
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    id,
                    bot_token,
                    webhook_url,
                    max_file_size_mb,
                    max_duration_seconds,
                    is_active,
                    last_activity,
                    created_at,
                    updated_at
                FROM bot_config
                ORDER BY created_at DESC
                LIMIT 1
            """)
            
            config = cursor.fetchone()
            if not config:
                # Return default config if none exists
                return {
                    "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
                    "webhook_url": os.getenv("TELEGRAM_WEBHOOK_URL", ""),
                    "max_file_size_mb": int(os.getenv("TELEGRAM_MAX_FILE_SIZE_MB", "50")),
                    "max_duration_seconds": int(os.getenv("TELEGRAM_MAX_DURATION_SECONDS", "60")),
                    "is_active": True,
                    "last_activity": None
                }
            
            config_dict = dict(config)
            
            # Decrypt bot_token if encrypted
            if ENCRYPTION_ENABLED and config_dict.get('bot_token'):
                try:
                    config_dict['bot_token'] = decrypt_bot_token(config_dict['bot_token'])
                except Exception as e:
                    logger.warning(f"Failed to decrypt bot_token (may be unencrypted): {e}")
                    # Continue with original value (backward compatibility)
            
            return config_dict
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting bot config: {e}", exc_info=True)
        raise


def update_bot_config(
    bot_token: Optional[str] = None,
    webhook_url: Optional[str] = None,
    max_file_size_mb: Optional[int] = None,
    max_duration_seconds: Optional[int] = None,
    is_active: Optional[bool] = None
) -> bool:
    """
    Update bot configuration.
    
    Args:
        bot_token: Telegram bot token
        webhook_url: Webhook URL
        max_file_size_mb: Maximum file size in MB
        max_duration_seconds: Maximum duration in seconds
        is_active: Whether bot is active
        
    Returns:
        True if config was updated
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Check if config exists
            cursor.execute("SELECT id FROM bot_config LIMIT 1")
            existing = cursor.fetchone()
            
            if existing:
                # Update existing config
                updates = []
                params = []
                
                if bot_token is not None:
                    updates.append("bot_token = %s")
                    # Encrypt bot_token if encryption is enabled
                    encrypted_token = encrypt_bot_token(bot_token) if ENCRYPTION_ENABLED else bot_token
                    params.append(encrypted_token)
                
                if webhook_url is not None:
                    updates.append("webhook_url = %s")
                    params.append(webhook_url)
                
                if max_file_size_mb is not None:
                    updates.append("max_file_size_mb = %s")
                    params.append(max_file_size_mb)
                
                if max_duration_seconds is not None:
                    updates.append("max_duration_seconds = %s")
                    params.append(max_duration_seconds)
                
                if is_active is not None:
                    updates.append("is_active = %s")
                    params.append(is_active)
                
                if updates:
                    updates.append("updated_at = NOW()")
                    query = f"UPDATE bot_config SET {', '.join(updates)}"
                    cursor.execute(query, params)
            else:
                # Create new config
                token_value = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
                if ENCRYPTION_ENABLED and token_value:
                    token_value = encrypt_bot_token(token_value)
                
                cursor.execute("""
                    INSERT INTO bot_config (
                        bot_token, webhook_url, max_file_size_mb,
                        max_duration_seconds, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    token_value,
                    webhook_url or os.getenv("TELEGRAM_WEBHOOK_URL", ""),
                    max_file_size_mb or int(os.getenv("TELEGRAM_MAX_FILE_SIZE_MB", "50")),
                    max_duration_seconds or int(os.getenv("TELEGRAM_MAX_DURATION_SECONDS", "60")),
                    is_active if is_active is not None else True
                ))
            
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error updating bot config: {e}", exc_info=True)
        return False


def get_bot_status() -> Dict[str, Any]:
    """
    Get bot status (online/offline, last activity).
    
    Returns:
        Dictionary with bot status information
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get bot config
            cursor.execute("""
                SELECT 
                    is_active,
                    last_activity,
                    updated_at
                FROM bot_config
                ORDER BY created_at DESC
                LIMIT 1
            """)
            
            config = cursor.fetchone()
            
            # Check Telegram service health (via health check endpoint)
            telegram_url = os.getenv("TELEGRAM_SERVICE_URL", "http://telegram:8080")
            health_status = "unknown"
            try:
                response = httpx.get(f"{telegram_url}/health", timeout=5.0)
                if response.status_code == 200:
                    health_data = response.json()
                    health_status = health_data.get("status", "unknown")
                else:
                    health_status = "unhealthy"
            except Exception as e:
                logger.warning(f"Failed to check Telegram service health: {e}")
                health_status = "unreachable"
            
            # Determine if bot is online
            is_online = health_status == "healthy" and (config and config.get("is_active", False) if config else False)
            
            return {
                "is_online": is_online,
                "is_active": config.get("is_active", False) if config else False,
                "health_status": health_status,
                "last_activity": config.get("last_activity").isoformat() if config and config.get("last_activity") else None,
                "last_updated": config.get("updated_at").isoformat() if config and config.get("updated_at") else None
            }
    except Exception as e:
        logger.error(f"Error getting bot status: {e}", exc_info=True)
        return {
            "is_online": False,
            "is_active": False,
            "health_status": "error",
            "last_activity": None,
            "last_updated": None
        }


def get_bot_statistics() -> Dict[str, Any]:
    """
    Get bot statistics (total messages, active conversations, error rate).
    
    Returns:
        Dictionary with bot statistics
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get total messages processed (from messages table)
            cursor.execute("""
                SELECT COUNT(*) as total_messages
                FROM messages
            """)
            total_messages = cursor.fetchone()['total_messages']
            
            # Get active conversations (conversations with activity in last 24 hours)
            cursor.execute("""
                SELECT COUNT(DISTINCT id) as active_conversations
                FROM conversations
                WHERE updated_at >= NOW() - INTERVAL '24 hours'
            """)
            active_conversations = cursor.fetchone()['active_conversations']
            
            # Get error count (from bot_statistics table, last 30 days)
            cursor.execute("""
                SELECT SUM(error_count) as total_errors
                FROM bot_statistics
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            """)
            error_result = cursor.fetchone()
            total_errors = error_result['total_errors'] or 0
            
            # Calculate error rate
            error_rate = (total_errors / total_messages * 100) if total_messages > 0 else 0.0
            
            # Get statistics from last 7 days
            cursor.execute("""
                SELECT 
                    date,
                    total_messages,
                    active_conversations,
                    error_count
                FROM bot_statistics
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY date DESC
            """)
            daily_stats = [dict(row) for row in cursor.fetchall()]
            
            return {
                "total_messages": total_messages,
                "active_conversations": active_conversations,
                "total_errors": total_errors,
                "error_rate": round(error_rate, 2),
                "daily_statistics": daily_stats
            }
    except Exception as e:
        logger.error(f"Error getting bot statistics: {e}", exc_info=True)
        return {
            "total_messages": 0,
            "active_conversations": 0,
            "total_errors": 0,
            "error_rate": 0.0,
            "daily_statistics": []
        }


def get_bot_commands() -> List[Dict[str, Any]]:
    """
    Get list of bot commands.
    
    Returns:
        List of bot command dictionaries
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    id,
                    command,
                    description,
                    is_active,
                    created_at,
                    updated_at
                FROM bot_commands
                ORDER BY command ASC
            """)
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting bot commands: {e}", exc_info=True)
        return []


def create_bot_command(command: str, description: str) -> Optional[str]:
    """
    Create a new bot command.
    
    Args:
        command: Command name (without /)
        description: Command description
        
    Returns:
        Command ID if created, None otherwise
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO bot_commands (command, description)
                VALUES (%s, %s)
                RETURNING id
            """, (command, description))
            
            result = cursor.fetchone()
            conn.commit()
            
            return str(result[0]) if result else None
        finally:
            conn.close()
    except psycopg2.IntegrityError:
        logger.warning(f"Bot command '{command}' already exists")
        return None
    except Exception as e:
        logger.error(f"Error creating bot command: {e}", exc_info=True)
        return None


def update_bot_command(command_id: str, description: Optional[str] = None, is_active: Optional[bool] = None) -> bool:
    """
    Update a bot command.
    
    Args:
        command_id: Command ID
        description: New description
        is_active: New active status
        
    Returns:
        True if command was updated
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if description is not None:
                updates.append("description = %s")
                params.append(description)
            
            if is_active is not None:
                updates.append("is_active = %s")
                params.append(is_active)
            
            if updates:
                updates.append("updated_at = NOW()")
                params.append(command_id)
                query = f"UPDATE bot_commands SET {', '.join(updates)} WHERE id = %s"
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0
            
            return False
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error updating bot command: {e}", exc_info=True)
        return False


def delete_bot_command(command_id: str) -> bool:
    """
    Delete a bot command.
    
    Args:
        command_id: Command ID
        
    Returns:
        True if command was deleted
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM bot_commands WHERE id = %s", (command_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error deleting bot command: {e}", exc_info=True)
        return False
