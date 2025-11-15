"""
Conversation storage for managing conversation data and metadata.

Provides methods to store and retrieve conversation information including
language preferences stored in the conversations.metadata JSONB field.
Also provides analytics and reporting capabilities.
"""
import os
import logging
import psycopg2
from psycopg2 import IntegrityError
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timedelta
import csv
import io

logger = logging.getLogger(__name__)

# Default language preference
DEFAULT_LANGUAGE = "en"


def get_db_connection():
    """
    Get PostgreSQL database connection.
    
    Note: PostgreSQL is not available. This function will raise an exception
    if called. All methods in ConversationStorage handle this gracefully.
    """
    # PostgreSQL is not available - raise an exception that will be caught by callers
    raise RuntimeError("PostgreSQL is not available. ConversationStorage methods will return defaults.")


class ConversationStorage:
    """Storage class for conversation data and metadata."""
    
    @staticmethod
    def get_language_preference(user_id: str, chat_id: str) -> str:
        """
        Get language preference for a conversation.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            
        Returns:
            Language code (ISO 639-1), defaults to "en" if not set
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                # Query conversation by user_id and session_id (chat_id)
                cursor.execute(
                    """
                    SELECT metadata
                    FROM conversations
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(user_id), str(chat_id))
                )
                result = cursor.fetchone()
                
                if result and result['metadata']:
                    metadata = result['metadata']
                    # Handle both dict and JSON string
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    elif not isinstance(metadata, dict):
                        metadata = {}
                    
                    language_preference = metadata.get('language_preference')
                    if language_preference:
                        logger.debug(f"Language preference for {user_id}/{chat_id}: {language_preference}")
                        return language_preference
                
                # Default to "en" if not found
                logger.debug(f"No language preference found for {user_id}/{chat_id}, defaulting to {DEFAULT_LANGUAGE}")
                return DEFAULT_LANGUAGE
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available for language preference check: {e}")
            return DEFAULT_LANGUAGE
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting language preference for {user_id}/{chat_id}: {e}", exc_info=True)
            # Return default on error
            return DEFAULT_LANGUAGE
    
    @staticmethod
    def set_language_preference(user_id: str, chat_id: str, language_code: str) -> bool:
        """
        Set language preference for a conversation.
        
        Stores the language preference in the conversations.metadata JSONB field.
        If the conversation doesn't exist, it will be created.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            language_code: Language code (ISO 639-1) to store
            
        Returns:
            True if language preference was set successfully, False otherwise
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # First, check if conversation exists
                cursor.execute(
                    """
                    SELECT id, metadata
                    FROM conversations
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(user_id), str(chat_id))
                )
                result = cursor.fetchone()
                
                # Normalize language code (lowercase)
                language_code = language_code.lower() if language_code else DEFAULT_LANGUAGE
                
                if result:
                    # Conversation exists - update metadata
                    conversation_id = result['id']
                    metadata = result['metadata'] or {}
                    
                    # Handle both dict and JSON string
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    elif not isinstance(metadata, dict):
                        metadata = {}
                    
                    # Update language preference
                    metadata['language_preference'] = language_code
                    
                    # Update conversation metadata
                    cursor.execute(
                        """
                        UPDATE conversations
                        SET metadata = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (json.dumps(metadata), conversation_id)
                    )
                    conn.commit()
                    logger.info(f"Updated language preference for {user_id}/{chat_id}: {language_code}")
                    return True
                else:
                    # Conversation doesn't exist - create it with metadata
                    cursor.execute(
                        """
                        INSERT INTO conversations (user_id, session_id, metadata)
                        VALUES (%s, %s, %s)
                        """,
                        (str(user_id), str(chat_id), json.dumps({'language_preference': language_code}))
                    )
                    conn.commit()
                    logger.info(f"Created conversation with language preference for {user_id}/{chat_id}: {language_code}")
                    return True
                    
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return False (preference not saved)
            logger.debug(f"PostgreSQL not available for setting language preference: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting language preference for {user_id}/{chat_id}: {e}", exc_info=True)
            return False
    
    @staticmethod
    def get_user_preferences(user_id: str, chat_id: str) -> Dict[str, Any]:
        """
        Get user preferences (name, favorite_color, etc.) for a conversation.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            
        Returns:
            Dictionary with user preferences (name, favorite_color, etc.), empty dict if not set
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                # Query conversation by user_id and session_id (chat_id)
                cursor.execute(
                    """
                    SELECT metadata
                    FROM conversations
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(user_id), str(chat_id))
                )
                result = cursor.fetchone()
                
                if result and result['metadata']:
                    metadata = result['metadata']
                    # Handle both dict and JSON string
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    elif not isinstance(metadata, dict):
                        metadata = {}
                    
                    # Extract user preferences from metadata
                    preferences = {
                        'name': metadata.get('user_name'),
                        'favorite_color': metadata.get('favorite_color')
                    }
                    # Remove None values
                    preferences = {k: v for k, v in preferences.items() if v is not None}
                    
                    if preferences:
                        logger.debug(f"User preferences for {user_id}/{chat_id}: {preferences}")
                    return preferences
                
                # Return empty dict if not found
                logger.debug(f"No user preferences found for {user_id}/{chat_id}")
                return {}
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting user preferences for {user_id}/{chat_id}: {e}", exc_info=True)
            # Return empty dict on error
            return {}
    
    @staticmethod
    def set_user_preferences(user_id: str, chat_id: str, name: Optional[str] = None, favorite_color: Optional[str] = None) -> bool:
        """
        Set user preferences (name, favorite_color) for a conversation.
        
        Stores the preferences in the conversations.metadata JSONB field.
        If the conversation doesn't exist, it will be created.
        Only updates the provided fields, leaving others unchanged.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            name: Optional user name to store
            favorite_color: Optional favorite color to store
            
        Returns:
            True if preferences were set successfully, False otherwise
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # First, check if conversation exists
                cursor.execute(
                    """
                    SELECT id, metadata
                    FROM conversations
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(user_id), str(chat_id))
                )
                result = cursor.fetchone()
                
                if result:
                    # Conversation exists - update metadata
                    conversation_id = result['id']
                    metadata = result['metadata'] or {}
                    
                    # Handle both dict and JSON string
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    elif not isinstance(metadata, dict):
                        metadata = {}
                    
                    # Update user preferences (only set provided values)
                    if name is not None:
                        metadata['user_name'] = name.strip() if name else None
                    if favorite_color is not None:
                        metadata['favorite_color'] = favorite_color.strip() if favorite_color else None
                    
                    # Update conversation metadata
                    cursor.execute(
                        """
                        UPDATE conversations
                        SET metadata = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (json.dumps(metadata), conversation_id)
                    )
                    conn.commit()
                    logger.info(f"Updated user preferences for {user_id}/{chat_id}: name={name}, favorite_color={favorite_color}")
                    return True
                else:
                    # Conversation doesn't exist - create it with metadata
                    metadata = {}
                    if name is not None:
                        metadata['user_name'] = name.strip() if name else None
                    if favorite_color is not None:
                        metadata['favorite_color'] = favorite_color.strip() if favorite_color else None
                    
                    cursor.execute(
                        """
                        INSERT INTO conversations (user_id, session_id, metadata)
                        VALUES (%s, %s, %s)
                        """,
                        (str(user_id), str(chat_id), json.dumps(metadata))
                    )
                    conn.commit()
                    logger.info(f"Created conversation with user preferences for {user_id}/{chat_id}: name={name}, favorite_color={favorite_color}")
                    return True
                    
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting user preferences for {user_id}/{chat_id}: {e}", exc_info=True)
            return False
    
    @staticmethod
    def get_conversation_analytics(user_id: str, chat_id: str) -> Dict[str, Any]:
        """
        Get analytics metrics for a specific conversation.
        
        Calculates:
        - Message counts (total, user, assistant)
        - Average response time (time between user messages and assistant responses)
        - User engagement score (based on message frequency and response patterns)
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            
        Returns:
            Dictionary with analytics metrics
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Get conversation ID
                cursor.execute(
                    """
                    SELECT id
                    FROM conversations
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(user_id), str(chat_id))
                )
                result = cursor.fetchone()
                
                if not result:
                    return {
                        "conversation_id": None,
                        "message_count": 0,
                        "user_message_count": 0,
                        "assistant_message_count": 0,
                        "average_response_time_seconds": 0.0,
                        "engagement_score": 0.0,
                        "first_message_at": None,
                        "last_message_at": None
                    }
                
                conversation_id = result['id']
                
                # Get all messages for this conversation, ordered by time
                cursor.execute(
                    """
                    SELECT role, content, created_at
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY created_at ASC
                    """,
                    (conversation_id,)
                )
                messages = cursor.fetchall()
                
                if not messages:
                    return {
                        "conversation_id": str(conversation_id),
                        "message_count": 0,
                        "user_message_count": 0,
                        "assistant_message_count": 0,
                        "average_response_time_seconds": 0.0,
                        "engagement_score": 0.0,
                        "first_message_at": None,
                        "last_message_at": None
                    }
                
                # Calculate metrics
                message_count = len(messages)
                user_message_count = sum(1 for m in messages if m['role'] == 'user')
                assistant_message_count = sum(1 for m in messages if m['role'] == 'assistant')
                
                # Calculate response times
                response_times = []
                last_user_message_time = None
                
                for msg in messages:
                    msg_time = msg['created_at']
                    if isinstance(msg_time, str):
                        msg_time = datetime.fromisoformat(msg_time.replace('Z', '+00:00'))
                    
                    if msg['role'] == 'user':
                        last_user_message_time = msg_time
                    elif msg['role'] == 'assistant' and last_user_message_time:
                        response_time = (msg_time - last_user_message_time).total_seconds()
                        if response_time > 0:  # Only count positive response times
                            response_times.append(response_time)
                
                avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
                
                # Calculate engagement score (0-100)
                # Based on: message frequency, response patterns, conversation length
                first_message_time = messages[0]['created_at']
                last_message_time = messages[-1]['created_at']
                
                if isinstance(first_message_time, str):
                    first_message_time = datetime.fromisoformat(first_message_time.replace('Z', '+00:00'))
                if isinstance(last_message_time, str):
                    last_message_time = datetime.fromisoformat(last_message_time.replace('Z', '+00:00'))
                
                conversation_duration = (last_message_time - first_message_time).total_seconds()
                if conversation_duration > 0:
                    message_frequency = message_count / (conversation_duration / 3600)  # messages per hour
                    response_ratio = assistant_message_count / user_message_count if user_message_count > 0 else 0
                    engagement_score = min(100, (message_frequency * 10 + response_ratio * 30 + min(message_count / 10, 1) * 60))
                else:
                    engagement_score = 0.0
                
                return {
                    "conversation_id": str(conversation_id),
                    "message_count": message_count,
                    "user_message_count": user_message_count,
                    "assistant_message_count": assistant_message_count,
                    "average_response_time_seconds": round(avg_response_time, 2),
                    "engagement_score": round(engagement_score, 2),
                    "first_message_at": messages[0]['created_at'].isoformat() if messages else None,
                    "last_message_at": messages[-1]['created_at'].isoformat() if messages else None
                }
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting conversation analytics for {user_id}/{chat_id}: {e}", exc_info=True)
            return {
                "error": str(e),
                "conversation_id": None,
                "message_count": 0,
                "user_message_count": 0,
                "assistant_message_count": 0,
                "average_response_time_seconds": 0.0,
                "engagement_score": 0.0
            }
    
    @staticmethod
    def get_dashboard_analytics(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated analytics across all conversations (dashboard view).
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with aggregated metrics
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Build date filter
                date_filter = ""
                params = []
                if start_date or end_date:
                    conditions = []
                    if start_date:
                        conditions.append("m.created_at >= %s")
                        params.append(start_date)
                    if end_date:
                        conditions.append("m.created_at <= %s")
                        params.append(end_date)
                    if conditions:
                        date_filter = "WHERE " + " AND ".join(conditions)
                
                # Get total conversations
                cursor.execute(
                    f"""
                    SELECT COUNT(DISTINCT c.id) as total_conversations
                    FROM conversations c
                    {date_filter.replace('m.', 'c.') if date_filter else ''}
                    """,
                    params
                )
                total_conversations = cursor.fetchone()['total_conversations']
                
                # Get total messages
                cursor.execute(
                    f"""
                    SELECT COUNT(*) as total_messages,
                           COUNT(*) FILTER (WHERE role = 'user') as user_messages,
                           COUNT(*) FILTER (WHERE role = 'assistant') as assistant_messages
                    FROM messages m
                    JOIN conversations c ON m.conversation_id = c.id
                    {date_filter}
                    """,
                    params
                )
                msg_result = cursor.fetchone()
                total_messages = msg_result['total_messages'] or 0
                user_messages = msg_result['user_messages'] or 0
                assistant_messages = msg_result['assistant_messages'] or 0
                
                # Get average response time across all conversations
                cursor.execute(
                    f"""
                    WITH user_messages AS (
                        SELECT conversation_id, created_at as user_time,
                               ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY created_at) as rn
                        FROM messages
                        WHERE role = 'user'
                    ),
                    assistant_messages AS (
                        SELECT conversation_id, created_at as assistant_time,
                               ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY created_at) as rn
                        FROM messages
                        WHERE role = 'assistant'
                    )
                    SELECT AVG(EXTRACT(EPOCH FROM (am.assistant_time - um.user_time))) as avg_response_time
                    FROM user_messages um
                    JOIN assistant_messages am ON um.conversation_id = am.conversation_id AND um.rn = am.rn
                    JOIN conversations c ON um.conversation_id = c.id
                    {date_filter.replace('m.', 'um.') if date_filter else ''}
                    WHERE am.assistant_time > um.user_time
                    """,
                    params
                )
                avg_response_result = cursor.fetchone()
                avg_response_time = avg_response_result['avg_response_time'] or 0.0
                
                # Get active users (users with messages in date range)
                cursor.execute(
                    f"""
                    SELECT COUNT(DISTINCT c.user_id) as active_users
                    FROM conversations c
                    JOIN messages m ON m.conversation_id = c.id
                    {date_filter.replace('m.', 'm.') if date_filter else ''}
                    """,
                    params
                )
                active_users = cursor.fetchone()['active_users'] or 0
                
                return {
                    "total_conversations": total_conversations,
                    "total_messages": total_messages,
                    "user_messages": user_messages,
                    "assistant_messages": assistant_messages,
                    "average_response_time_seconds": round(float(avg_response_time), 2),
                    "active_users": active_users,
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None
                }
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting dashboard analytics: {e}", exc_info=True)
            return {
                "error": str(e),
                "total_conversations": 0,
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "average_response_time_seconds": 0.0,
                "active_users": 0
            }
    
    @staticmethod
    def generate_analytics_report(
        format: str = "json",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> str:
        """
        Generate analytics report in JSON or CSV format.
        
        Args:
            format: Report format - "json" or "csv"
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Report as string (JSON or CSV)
        """
        try:
            dashboard_data = ConversationStorage.get_dashboard_analytics(start_date, end_date)
            
            if format.lower() == "csv":
                # Generate CSV report
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Header
                writer.writerow(["Metric", "Value"])
                writer.writerow(["Total Conversations", dashboard_data.get("total_conversations", 0)])
                writer.writerow(["Total Messages", dashboard_data.get("total_messages", 0)])
                writer.writerow(["User Messages", dashboard_data.get("user_messages", 0)])
                writer.writerow(["Assistant Messages", dashboard_data.get("assistant_messages", 0)])
                writer.writerow(["Average Response Time (seconds)", dashboard_data.get("average_response_time_seconds", 0.0)])
                writer.writerow(["Active Users", dashboard_data.get("active_users", 0)])
                if start_date:
                    writer.writerow(["Start Date", start_date.isoformat()])
                if end_date:
                    writer.writerow(["End Date", end_date.isoformat()])
                
                return output.getvalue()
            else:
                # Generate JSON report
                return json.dumps(dashboard_data, indent=2)
                
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error generating analytics report: {e}", exc_info=True)
            error_report = {"error": str(e)}
            return json.dumps(error_report) if format.lower() != "csv" else f"Error,{str(e)}"
    
    @staticmethod
    def validate_prompt_template(template_text: str) -> tuple[bool, Optional[str]]:
        """
        Validate prompt template syntax.
        
        Checks for:
        - Balanced braces
        - Valid variable syntax (alphanumeric + underscore)
        - No nested braces
        
        Args:
            template_text: Template text to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not template_text:
            return False, "Template text cannot be empty"
        
        # Check for balanced braces
        open_braces = template_text.count('{')
        close_braces = template_text.count('}')
        
        if open_braces != close_braces:
            return False, f"Unbalanced braces: {open_braces} opening, {close_braces} closing"
        
        # Check for valid variable syntax and no nested braces
        import re
        # Pattern to match {variable} where variable is alphanumeric + underscore
        variable_pattern = r'\{([a-zA-Z0-9_]+)\}'
        matches = re.findall(variable_pattern, template_text)
        
        # Check for nested braces (e.g., {{variable}})
        if re.search(r'\{\{|\}\}', template_text):
            return False, "Nested braces are not allowed"
        
        # Check for invalid variable names (non-alphanumeric/underscore)
        invalid_vars = re.findall(r'\{([^}]+)\}', template_text)
        for var in invalid_vars:
            if not re.match(r'^[a-zA-Z0-9_]+$', var):
                return False, f"Invalid variable name: '{var}'. Variables must contain only alphanumeric characters and underscores"
        
        return True, None
    
    @staticmethod
    def create_prompt_template(
        name: str,
        template_text: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a new prompt template.
        
        Args:
            name: Template name/identifier
            template_text: Template content with {variable} placeholders
            user_id: Optional user ID for per-user templates
            conversation_id: Optional conversation ID for per-conversation templates (requires user_id)
            description: Optional description
            
        Returns:
            Template ID (UUID string) if successful, None otherwise
        """
        # Validate template syntax
        is_valid, error_msg = ConversationStorage.validate_prompt_template(template_text)
        if not is_valid:
            logger.error(f"Invalid template syntax: {error_msg}")
            return None
        
        # Validate conversation_id requires user_id
        if conversation_id and not user_id:
            logger.error("conversation_id requires user_id to be set")
            return None
        
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                
                # Insert template
                cursor.execute(
                    """
                    INSERT INTO prompt_templates (name, template_text, user_id, conversation_id, description)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (name, template_text, user_id, conversation_id, description)
                )
                
                template_id = cursor.fetchone()[0]
                conn.commit()
                logger.info(f"Created prompt template: {template_id} (name={name}, user_id={user_id}, conversation_id={conversation_id})")
                return str(template_id)
                
            except IntegrityError as e:
                conn.rollback()
                logger.error(f"Template already exists or constraint violation: {e}")
                return None
            except (RuntimeError, psycopg2.OperationalError) as e:
                # PostgreSQL not available - return default
                logger.debug(f"PostgreSQL not available: {e}")
                return False
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error creating prompt template: {e}", exc_info=True)
            return None
    
    @staticmethod
    def get_prompt_template(template_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a prompt template by ID.
        
        Args:
            template_id: Template ID (UUID string)
            
        Returns:
            Template dictionary or None if not found
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(
                    """
                    SELECT id, name, template_text, user_id, conversation_id, description, is_active, created_at, updated_at
                    FROM prompt_templates
                    WHERE id = %s
                    """,
                    (template_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    return dict(result)
                return None
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting prompt template: {e}", exc_info=True)
            return None
    
    @staticmethod
    def get_prompt_template_for_user(user_id: str, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a user-specific prompt template.
        
        Args:
            user_id: User ID
            name: Optional template name (if None, gets first active template for user)
            
        Returns:
            Template dictionary or None if not found
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                if name:
                    cursor.execute(
                        """
                        SELECT id, name, template_text, user_id, conversation_id, description, is_active, created_at, updated_at
                        FROM prompt_templates
                        WHERE user_id = %s AND name = %s AND is_active = TRUE
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (user_id, name)
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, name, template_text, user_id, conversation_id, description, is_active, created_at, updated_at
                        FROM prompt_templates
                        WHERE user_id = %s AND is_active = TRUE
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (user_id,)
                    )
                
                result = cursor.fetchone()
                if result:
                    return dict(result)
                return None
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting user prompt template: {e}", exc_info=True)
            return None
    
    @staticmethod
    def get_prompt_template_for_conversation(user_id: str, chat_id: str, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a conversation-specific prompt template, with fallback to user template.
        
        Args:
            user_id: User ID
            chat_id: Chat ID (session_id in database)
            name: Optional template name
            
        Returns:
            Template dictionary or None if not found
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # First, try to get conversation-specific template
                # Get conversation ID from user_id and chat_id
                cursor.execute(
                    """
                    SELECT id
                    FROM conversations
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(user_id), str(chat_id))
                )
                conv_result = cursor.fetchone()
                
                if conv_result:
                    conversation_id = conv_result['id']
                    
                    if name:
                        cursor.execute(
                            """
                            SELECT id, name, template_text, user_id, conversation_id, description, is_active, created_at, updated_at
                            FROM prompt_templates
                            WHERE user_id = %s AND conversation_id = %s AND name = %s AND is_active = TRUE
                            ORDER BY created_at DESC
                            LIMIT 1
                            """,
                            (user_id, conversation_id, name)
                        )
                    else:
                        cursor.execute(
                            """
                            SELECT id, name, template_text, user_id, conversation_id, description, is_active, created_at, updated_at
                            FROM prompt_templates
                            WHERE user_id = %s AND conversation_id = %s AND is_active = TRUE
                            ORDER BY created_at DESC
                            LIMIT 1
                            """,
                            (user_id, conversation_id)
                        )
                    
                    result = cursor.fetchone()
                    if result:
                        return dict(result)
                
                # Fallback to user template
                return ConversationStorage.get_prompt_template_for_user(user_id, name)
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting conversation prompt template: {e}", exc_info=True)
            # Fallback to user template on error
            return ConversationStorage.get_prompt_template_for_user(user_id, name)
    
    @staticmethod
    def list_prompt_templates(
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        List prompt templates with optional filters.
        
        Args:
            user_id: Optional filter by user ID
            conversation_id: Optional filter by conversation ID
            is_active: Optional filter by active status
            
        Returns:
            List of template dictionaries
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Build query with filters
                query = """
                    SELECT id, name, template_text, user_id, conversation_id, description, is_active, created_at, updated_at
                    FROM prompt_templates
                    WHERE 1=1
                """
                params = []
                
                if user_id is not None:
                    query += " AND user_id = %s"
                    params.append(user_id)
                
                if conversation_id is not None:
                    query += " AND conversation_id = %s"
                    params.append(conversation_id)
                
                if is_active is not None:
                    query += " AND is_active = %s"
                    params.append(is_active)
                
                query += " ORDER BY created_at DESC"
                
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                return [dict(row) for row in results]
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error listing prompt templates: {e}", exc_info=True)
            return []
    
    @staticmethod
    def update_prompt_template(
        template_id: str,
        template_text: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Update a prompt template.
        
        Args:
            template_id: Template ID (UUID string)
            template_text: Optional new template text
            description: Optional new description
            is_active: Optional new active status
            
        Returns:
            True if successful, False otherwise
        """
        # Validate template syntax if template_text is provided
        if template_text:
            is_valid, error_msg = ConversationStorage.validate_prompt_template(template_text)
            if not is_valid:
                logger.error(f"Invalid template syntax: {error_msg}")
                return False
        
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                
                # Build update query dynamically
                updates = []
                params = []
                
                if template_text is not None:
                    updates.append("template_text = %s")
                    params.append(template_text)
                
                if description is not None:
                    updates.append("description = %s")
                    params.append(description)
                
                if is_active is not None:
                    updates.append("is_active = %s")
                    params.append(is_active)
                
                if not updates:
                    logger.warning("No fields to update")
                    return False
                
                updates.append("updated_at = NOW()")
                params.append(template_id)
                
                query = f"""
                    UPDATE prompt_templates
                    SET {', '.join(updates)}
                    WHERE id = %s
                """
                
                cursor.execute(query, params)
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Updated prompt template: {template_id}")
                    return True
                else:
                    logger.warning(f"Template not found: {template_id}")
                    return False
                
            except (RuntimeError, psycopg2.OperationalError) as e:
                # PostgreSQL not available - return default
                logger.debug(f"PostgreSQL not available: {e}")
                return False
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating prompt template: {e}", exc_info=True)
            return False
    
    @staticmethod
    def delete_prompt_template(template_id: str) -> bool:
        """
        Delete a prompt template.
        
        Args:
            template_id: Template ID (UUID string)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM prompt_templates WHERE id = %s",
                    (template_id,)
                )
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Deleted prompt template: {template_id}")
                    return True
                else:
                    logger.warning(f"Template not found: {template_id}")
                    return False
                
            except (RuntimeError, psycopg2.OperationalError) as e:
                # PostgreSQL not available - return default
                logger.debug(f"PostgreSQL not available: {e}")
                return False
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting prompt template: {e}", exc_info=True)
            return False
    
    @staticmethod
    def export_conversation(
        user_id: str,
        chat_id: str,
        format: str = "json",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> bytes:
        """
        Export conversation to JSON, TXT, or PDF format.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            format: Export format - "json", "txt", or "pdf"
            start_date: Optional start date filter for messages
            end_date: Optional end date filter for messages
            
        Returns:
            Exported conversation data as bytes
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Get conversation
                cursor.execute(
                    """
                    SELECT id, user_id, session_id, created_at, updated_at, metadata
                    FROM conversations
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(user_id), str(chat_id))
                )
                conversation = cursor.fetchone()
                
                if not conversation:
                    raise ValueError(f"Conversation not found for user_id={user_id}, chat_id={chat_id}")
                
                conversation_id = conversation['id']
                
                # Build date filter for messages
                date_filter = ""
                params = [conversation_id]
                if start_date or end_date:
                    conditions = []
                    if start_date:
                        conditions.append("created_at >= %s")
                        params.append(start_date)
                    if end_date:
                        conditions.append("created_at <= %s")
                        params.append(end_date)
                    if conditions:
                        date_filter = "AND " + " AND ".join(conditions)
                
                # Get messages
                cursor.execute(
                    f"""
                    SELECT role, content, created_at, metadata
                    FROM messages
                    WHERE conversation_id = %s
                    {date_filter}
                    ORDER BY created_at ASC
                    """,
                    params
                )
                messages = cursor.fetchall()
                
                # Prepare conversation data
                conversation_data = {
                    "conversation_id": str(conversation['id']),
                    "user_id": conversation['user_id'],
                    "chat_id": conversation['session_id'],
                    "created_at": conversation['created_at'].isoformat() if conversation['created_at'] else None,
                    "updated_at": conversation['updated_at'].isoformat() if conversation['updated_at'] else None,
                    "metadata": conversation['metadata'] if conversation['metadata'] else {},
                    "message_count": len(messages),
                    "messages": [
                        {
                            "role": msg['role'],
                            "content": msg['content'],
                            "created_at": msg['created_at'].isoformat() if msg['created_at'] else None,
                            "metadata": msg['metadata'] if msg['metadata'] else {}
                        }
                        for msg in messages
                    ]
                }
                
                # Export in requested format
                if format.lower() == "json":
                    return json.dumps(conversation_data, indent=2, ensure_ascii=False).encode('utf-8')
                
                elif format.lower() == "txt":
                    # Generate plain text export
                    output = io.StringIO()
                    output.write(f"Conversation Export\n")
                    output.write(f"{'=' * 50}\n\n")
                    output.write(f"Conversation ID: {conversation_data['conversation_id']}\n")
                    output.write(f"User ID: {conversation_data['user_id']}\n")
                    output.write(f"Chat ID: {conversation_data['chat_id']}\n")
                    output.write(f"Created: {conversation_data['created_at']}\n")
                    output.write(f"Updated: {conversation_data['updated_at']}\n")
                    output.write(f"Message Count: {conversation_data['message_count']}\n")
                    if conversation_data['metadata']:
                        output.write(f"Metadata: {json.dumps(conversation_data['metadata'], indent=2)}\n")
                    output.write(f"\n{'=' * 50}\n")
                    output.write(f"Messages\n")
                    output.write(f"{'=' * 50}\n\n")
                    
                    for msg in conversation_data['messages']:
                        role_display = msg['role'].upper()
                        timestamp = msg['created_at'] if msg['created_at'] else "N/A"
                        output.write(f"[{timestamp}] {role_display}:\n")
                        output.write(f"{msg['content']}\n")
                        if msg['metadata']:
                            output.write(f"Metadata: {json.dumps(msg['metadata'], indent=2)}\n")
                        output.write(f"\n{'-' * 50}\n\n")
                    
                    return output.getvalue().encode('utf-8')
                
                elif format.lower() == "pdf":
                    # Generate PDF export
                    try:
                        from reportlab.lib.pagesizes import letter
                        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                        from reportlab.lib.units import inch
                        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
                        from reportlab.lib.enums import TA_LEFT, TA_CENTER
                        from reportlab.pdfbase import pdfmetrics
                        from reportlab.pdfbase.ttfonts import TTFont
                    except ImportError:
                        raise ImportError("reportlab is required for PDF export. Install it with: pip install reportlab")
                    
                    buffer = io.BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=letter)
                    story = []
                    styles = getSampleStyleSheet()
                    
                    # Title
                    title_style = ParagraphStyle(
                        'CustomTitle',
                        parent=styles['Heading1'],
                        fontSize=16,
                        textColor='#000000',
                        spaceAfter=30,
                        alignment=TA_CENTER
                    )
                    story.append(Paragraph("Conversation Export", title_style))
                    story.append(Spacer(1, 0.2 * inch))
                    
                    # Conversation info
                    info_style = styles['Normal']
                    story.append(Paragraph(f"<b>Conversation ID:</b> {conversation_data['conversation_id']}", info_style))
                    story.append(Paragraph(f"<b>User ID:</b> {conversation_data['user_id']}", info_style))
                    story.append(Paragraph(f"<b>Chat ID:</b> {conversation_data['chat_id']}", info_style))
                    story.append(Paragraph(f"<b>Created:</b> {conversation_data['created_at']}", info_style))
                    story.append(Paragraph(f"<b>Updated:</b> {conversation_data['updated_at']}", info_style))
                    story.append(Paragraph(f"<b>Message Count:</b> {conversation_data['message_count']}", info_style))
                    if conversation_data['metadata']:
                        story.append(Paragraph(f"<b>Metadata:</b> {json.dumps(conversation_data['metadata'])}", info_style))
                    story.append(Spacer(1, 0.3 * inch))
                    
                    # Messages
                    story.append(Paragraph("<b>Messages</b>", styles['Heading2']))
                    story.append(Spacer(1, 0.2 * inch))
                    
                    for msg in conversation_data['messages']:
                        role_display = msg['role'].upper()
                        timestamp = msg['created_at'] if msg['created_at'] else "N/A"
                        
                        # Message header
                        header_style = ParagraphStyle(
                            'MessageHeader',
                            parent=styles['Normal'],
                            fontSize=10,
                            textColor='#666666',
                            spaceAfter=6
                        )
                        story.append(Paragraph(f"<b>[{timestamp}] {role_display}:</b>", header_style))
                        
                        # Message content (escape HTML)
                        content = msg['content'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        # Replace newlines with <br/>
                        content = content.replace('\n', '<br/>')
                        story.append(Paragraph(content, info_style))
                        
                        if msg['metadata']:
                            metadata_text = json.dumps(msg['metadata']).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                            story.append(Paragraph(f"<i>Metadata: {metadata_text}</i>", info_style))
                        
                        story.append(Spacer(1, 0.15 * inch))
                    
                    doc.build(story)
                    buffer.seek(0)
                    return buffer.read()
                
                else:
                    raise ValueError(f"Unsupported export format: {format}. Supported formats: json, txt, pdf")
                
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error exporting conversation for {user_id}/{chat_id}: {e}", exc_info=True)
            raise
    
    # ==================== A/B Testing Methods ====================
    
    @staticmethod
    def create_ab_test(
        name: str,
        variants: List[Dict[str, Any]],
        description: Optional[str] = None,
        traffic_split: float = 1.0
    ) -> Optional[str]:
        """
        Create a new A/B test configuration.
        
        Args:
            name: Unique test name
            variants: List of variant configs, each with 'name', 'model', 'temperature', 'system_prompt'
            description: Optional test description
            traffic_split: Fraction of traffic to include (0.0-1.0)
            
        Returns:
            Test ID (UUID string) if successful, None otherwise
        """
        if not variants or len(variants) < 2:
            logger.error("A/B test must have at least 2 variants")
            return None
        
        if not (0.0 <= traffic_split <= 1.0):
            logger.error("traffic_split must be between 0.0 and 1.0")
            return None
        
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO ab_tests (name, description, variants, traffic_split)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (name, description, json.dumps(variants), traffic_split)
                )
                test_id = cursor.fetchone()[0]
                conn.commit()
                logger.info(f"Created A/B test: {test_id} (name={name})")
                return str(test_id)
            except IntegrityError as e:
                conn.rollback()
                logger.error(f"A/B test name already exists or constraint violation: {e}")
                return None
            except (RuntimeError, psycopg2.OperationalError) as e:
                # PostgreSQL not available - return default
                logger.debug(f"PostgreSQL not available: {e}")
                return False
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error creating A/B test: {e}", exc_info=True)
            return None
    
    @staticmethod
    def get_ab_test(test_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an A/B test by ID.
        
        Args:
            test_id: Test ID (UUID string)
            
        Returns:
            Test dictionary or None if not found
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(
                    """
                    SELECT id, name, description, variants, traffic_split, is_active, created_at, updated_at
                    FROM ab_tests
                    WHERE id = %s
                    """,
                    (test_id,)
                )
                result = cursor.fetchone()
                if result:
                    test_dict = dict(result)
                    # Parse variants JSON
                    if isinstance(test_dict['variants'], str):
                        test_dict['variants'] = json.loads(test_dict['variants'])
                    return test_dict
                return None
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting A/B test: {e}", exc_info=True)
            return None
    
    @staticmethod
    def list_ab_tests(active_only: bool = False) -> List[Dict[str, Any]]:
        """
        List all A/B tests.
        
        Args:
            active_only: If True, only return active tests
            
        Returns:
            List of test dictionaries
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                if active_only:
                    cursor.execute(
                        """
                        SELECT id, name, description, variants, traffic_split, is_active, created_at, updated_at
                        FROM ab_tests
                        WHERE is_active = TRUE
                        ORDER BY created_at DESC
                        """
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, name, description, variants, traffic_split, is_active, created_at, updated_at
                        FROM ab_tests
                        ORDER BY created_at DESC
                        """
                    )
                results = cursor.fetchall()
                tests = []
                for row in results:
                    test_dict = dict(row)
                    # Parse variants JSON
                    if isinstance(test_dict['variants'], str):
                        test_dict['variants'] = json.loads(test_dict['variants'])
                    tests.append(test_dict)
                return tests
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error listing A/B tests: {e}", exc_info=True)
            return []
    
    @staticmethod
    def update_ab_test(
        test_id: str,
        description: Optional[str] = None,
        variants: Optional[List[Dict[str, Any]]] = None,
        traffic_split: Optional[float] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Update an A/B test.
        
        Args:
            test_id: Test ID (UUID string)
            description: Optional new description
            variants: Optional new variants list
            traffic_split: Optional new traffic split
            is_active: Optional new active status
            
        Returns:
            True if successful, False otherwise
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
                
                if variants is not None:
                    if len(variants) < 2:
                        logger.error("A/B test must have at least 2 variants")
                        return False
                    updates.append("variants = %s")
                    params.append(json.dumps(variants))
                
                if traffic_split is not None:
                    if not (0.0 <= traffic_split <= 1.0):
                        logger.error("traffic_split must be between 0.0 and 1.0")
                        return False
                    updates.append("traffic_split = %s")
                    params.append(traffic_split)
                
                if is_active is not None:
                    updates.append("is_active = %s")
                    params.append(is_active)
                
                if not updates:
                    logger.warning("No fields to update")
                    return False
                
                updates.append("updated_at = NOW()")
                params.append(test_id)
                
                query = f"""
                    UPDATE ab_tests
                    SET {', '.join(updates)}
                    WHERE id = %s
                """
                cursor.execute(query, params)
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Updated A/B test: {test_id}")
                    return True
                else:
                    logger.warning(f"A/B test not found: {test_id}")
                    return False
            except (RuntimeError, psycopg2.OperationalError) as e:
                # PostgreSQL not available - return default
                logger.debug(f"PostgreSQL not available: {e}")
                return False
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating A/B test: {e}", exc_info=True)
            return False
    
    @staticmethod
    def deactivate_ab_test(test_id: str) -> bool:
        """
        Deactivate an A/B test.
        
        Args:
            test_id: Test ID (UUID string)
            
        Returns:
            True if successful, False otherwise
        """
        return ConversationStorage.update_ab_test(test_id, is_active=False)
    
    @staticmethod
    def assign_ab_variant(
        test_id: str,
        conversation_id: str,
        force_variant: Optional[str] = None
    ) -> Optional[str]:
        """
        Assign a variant to a conversation for an A/B test.
        Uses hash-based distribution for consistent assignment.
        
        Args:
            test_id: Test ID (UUID string)
            conversation_id: Conversation ID (UUID string)
            force_variant: Optional variant name to force assignment (for testing)
            
        Returns:
            Variant name assigned, or None if assignment failed
        """
        try:
            # Get test configuration
            test = ConversationStorage.get_ab_test(test_id)
            if not test or not test.get('is_active'):
                logger.warning(f"A/B test {test_id} not found or not active")
                return None
            
            variants = test['variants']
            if isinstance(variants, str):
                variants = json.loads(variants)
            
            if not variants:
                logger.error(f"No variants configured for test {test_id}")
                return None
            
            # Check if already assigned
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(
                    """
                    SELECT variant_name
                    FROM ab_test_assignments
                    WHERE ab_test_id = %s AND conversation_id = %s
                    """,
                    (test_id, conversation_id)
                )
                existing = cursor.fetchone()
                if existing:
                    logger.debug(f"Conversation {conversation_id} already assigned to variant {existing['variant_name']}")
                    return existing['variant_name']
                
                # Assign variant using hash-based distribution
                if force_variant:
                    # Verify force_variant exists
                    variant_names = [v.get('name') for v in variants]
                    if force_variant not in variant_names:
                        logger.error(f"Force variant {force_variant} not found in test variants")
                        return None
                    selected_variant = force_variant
                else:
                    # Hash-based consistent assignment
                    import hashlib
                    hash_input = f"{test_id}:{conversation_id}".encode('utf-8')
                    hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
                    selected_variant = variants[hash_value % len(variants)]['name']
                
                # Apply traffic split
                if test.get('traffic_split', 1.0) < 1.0:
                    # Use hash to determine if conversation should be included
                    hash_input = f"{test_id}:{conversation_id}:split".encode('utf-8')
                    hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
                    split_hash = (hash_value % 10000) / 10000.0
                    if split_hash > test['traffic_split']:
                        logger.debug(f"Conversation {conversation_id} excluded from test due to traffic_split")
                        return None
                
                # Record assignment
                cursor.execute(
                    """
                    INSERT INTO ab_test_assignments (ab_test_id, conversation_id, variant_name)
                    VALUES (%s, %s, %s)
                    """,
                    (test_id, conversation_id, selected_variant)
                )
                conn.commit()
                logger.info(f"Assigned conversation {conversation_id} to variant {selected_variant} for test {test_id}")
                return selected_variant
            except psycopg2.IntegrityError:
                conn.rollback()
                # Race condition - another process assigned it, fetch the existing assignment
                cursor.execute(
                    """
                    SELECT variant_name
                    FROM ab_test_assignments
                    WHERE ab_test_id = %s AND conversation_id = %s
                    """,
                    (test_id, conversation_id)
                )
                existing = cursor.fetchone()
                if existing:
                    return existing['variant_name']
                return None
            except (RuntimeError, psycopg2.OperationalError) as e:
                # PostgreSQL not available - return default
                logger.debug(f"PostgreSQL not available: {e}")
                return False
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error assigning A/B variant: {e}", exc_info=True)
            return None
    
    @staticmethod
    def record_ab_metric(
        test_id: str,
        variant_name: str,
        metric_type: str,
        metric_value: Optional[float] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Record a metric for an A/B test variant.
        
        Args:
            test_id: Test ID (UUID string)
            variant_name: Variant name
            metric_type: Metric type (e.g., 'response_time', 'tokens', 'satisfaction', 'error')
            metric_value: Optional numeric metric value
            conversation_id: Optional conversation ID
            metadata: Optional additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO ab_test_metrics (ab_test_id, variant_name, conversation_id, metric_type, metric_value, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (test_id, variant_name, conversation_id, metric_type, metric_value, json.dumps(metadata or {}))
                )
                conn.commit()
                logger.debug(f"Recorded metric {metric_type}={metric_value} for variant {variant_name} in test {test_id}")
                return True
            except (RuntimeError, psycopg2.OperationalError) as e:
                # PostgreSQL not available - return default
                logger.debug(f"PostgreSQL not available: {e}")
                return False
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error recording A/B metric: {e}", exc_info=True)
            return False
    
    @staticmethod
    def get_ab_metrics(
        test_id: str,
        variant_name: Optional[str] = None,
        metric_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get metrics for an A/B test.
        
        Args:
            test_id: Test ID (UUID string)
            variant_name: Optional filter by variant
            metric_type: Optional filter by metric type
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of metric dictionaries
        """
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                query = """
                    SELECT variant_name, metric_type, metric_value, conversation_id, metadata, recorded_at
                    FROM ab_test_metrics
                    WHERE ab_test_id = %s
                """
                params = [test_id]
                
                if variant_name:
                    query += " AND variant_name = %s"
                    params.append(variant_name)
                
                if metric_type:
                    query += " AND metric_type = %s"
                    params.append(metric_type)
                
                if start_date:
                    query += " AND recorded_at >= %s"
                    params.append(start_date)
                
                if end_date:
                    query += " AND recorded_at <= %s"
                    params.append(end_date)
                
                query += " ORDER BY recorded_at DESC"
                
                cursor.execute(query, params)
                results = cursor.fetchall()
                metrics = []
                for row in results:
                    metric_dict = dict(row)
                    # Parse metadata JSON
                    if isinstance(metric_dict.get('metadata'), str):
                        metric_dict['metadata'] = json.loads(metric_dict['metadata'])
                    metrics.append(metric_dict)
                return metrics
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting A/B metrics: {e}", exc_info=True)
            return []
    
    @staticmethod
    def get_ab_statistics(test_id: str) -> Dict[str, Any]:
        """
        Get statistical analysis for an A/B test.
        
        Args:
            test_id: Test ID (UUID string)
            
        Returns:
            Dictionary with statistics per variant
        """
        try:
            # Get test configuration
            test = ConversationStorage.get_ab_test(test_id)
            if not test:
                return {"error": "Test not found"}
            
            variants = test['variants']
            if isinstance(variants, str):
                variants = json.loads(variants)
            
            variant_names = [v.get('name') for v in variants]
            
            # Get metrics for each variant
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                statistics = {}
                for variant_name in variant_names:
                    # Get all metrics for this variant
                    cursor.execute(
                        """
                        SELECT metric_type, metric_value, COUNT(*) as count
                        FROM ab_test_metrics
                        WHERE ab_test_id = %s AND variant_name = %s
                        GROUP BY metric_type, metric_value
                        """,
                        (test_id, variant_name)
                    )
                    metrics = cursor.fetchall()
                    
                    # Calculate statistics
                    variant_stats = {
                        "variant_name": variant_name,
                        "total_metrics": sum(m['count'] for m in metrics),
                        "metrics_by_type": {}
                    }
                    
                    # Group by metric type
                    for metric in metrics:
                        metric_type = metric['metric_type']
                        if metric_type not in variant_stats['metrics_by_type']:
                            variant_stats['metrics_by_type'][metric_type] = {
                                "count": 0,
                                "sum": 0.0,
                                "values": []
                            }
                        variant_stats['metrics_by_type'][metric_type]['count'] += metric['count']
                        if metric['metric_value'] is not None:
                            variant_stats['metrics_by_type'][metric_type]['sum'] += metric['metric_value'] * metric['count']
                            variant_stats['metrics_by_type'][metric_type]['values'].extend([metric['metric_value']] * metric['count'])
                    
                    # Calculate averages
                    for metric_type, data in variant_stats['metrics_by_type'].items():
                        if data['count'] > 0 and data['sum'] > 0:
                            data['average'] = data['sum'] / data['count']
                        else:
                            data['average'] = 0.0
                    
                    # Calculate error rate
                    error_count = sum(
                        m['count'] for m in metrics
                        if m['metric_type'] == 'error' and m['metric_value'] and m['metric_value'] > 0
                    )
                    total_requests = variant_stats['total_metrics']
                    variant_stats['error_rate'] = (error_count / total_requests * 100) if total_requests > 0 else 0.0
                    
                    statistics[variant_name] = variant_stats
                
                return {
                    "test_id": test_id,
                    "test_name": test.get('name'),
                    "variants": statistics
                }
            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting A/B statistics: {e}", exc_info=True)
            return {"error": str(e)}
    
    @staticmethod
    def get_ab_test_variant_config(
        user_id: str,
        chat_id: str,
        ab_test_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get A/B test variant configuration for a conversation.
        
        This method:
        1. Gets or creates conversation to get conversation_id
        2. Assigns A/B test variant if ab_test_id is provided
        3. Returns variant configuration to apply
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            ab_test_id: Optional A/B test ID to enable A/B testing
            
        Returns:
            Dictionary with:
            - conversation_id: Conversation ID
            - variant_name: Assigned variant name (if A/B testing)
            - variant_config: Variant configuration dict with model, temperature, system_prompt
            - messages_override: Modified messages list with system prompt override (if applicable)
            Or None if error
        """
        try:
            # Get or create conversation to get conversation_id
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(
                    """
                    SELECT id
                    FROM conversations
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(user_id), str(chat_id))
                )
                result = cursor.fetchone()
                
                if result:
                    conversation_id = str(result['id'])
                else:
                    # Create conversation
                    cursor.execute(
                        """
                        INSERT INTO conversations (user_id, session_id)
                        VALUES (%s, %s)
                        RETURNING id
                        """,
                        (str(user_id), str(chat_id))
                    )
                    conversation_id = str(cursor.fetchone()[0])
                    conn.commit()
            finally:
                conn.close()
            
            result = {
                'conversation_id': conversation_id,
                'variant_name': None,
                'variant_config': None
            }
            
            # A/B testing: Assign variant if test is provided
            if ab_test_id and conversation_id:
                variant_name = ConversationStorage.assign_ab_variant(ab_test_id, conversation_id)
                if variant_name:
                    # Get variant configuration
                    test = ConversationStorage.get_ab_test(ab_test_id)
                    if test:
                        variants = test.get('variants', [])
                        if isinstance(variants, str):
                            variants = json.loads(variants)
                        variant_config = next(
                            (v for v in variants if v.get('name') == variant_name),
                            None
                        )
                        if variant_config:
                            logger.info(f"Using A/B test variant {variant_name} for conversation {conversation_id}")
                            result['variant_name'] = variant_name
                            result['variant_config'] = variant_config
            
            return result
            
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error getting A/B test variant config: {e}", exc_info=True)
            return None
    
    @staticmethod
    def record_llm_response_metrics(
        ab_test_id: str,
        variant_name: str,
        conversation_id: str,
        response_time: float,
        response_text: Optional[str] = None,
        error: Optional[Exception] = None
    ) -> bool:
        """
        Record metrics for an LLM response in an A/B test.
        
        Args:
            ab_test_id: A/B test ID
            variant_name: Variant name
            conversation_id: Conversation ID
            response_time: Response time in seconds
            response_text: Optional response text (for token estimation)
            error: Optional error that occurred
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Record response time
            ConversationStorage.record_ab_metric(
                ab_test_id, variant_name, 'response_time',
                metric_value=response_time,
                conversation_id=conversation_id
            )
            
            # Record error if occurred
            if error:
                ConversationStorage.record_ab_metric(
                    ab_test_id, variant_name, 'error',
                    metric_value=1.0,
                    conversation_id=conversation_id,
                    metadata={'error': str(error)}
                )
            else:
                # Record success (error=0)
                ConversationStorage.record_ab_metric(
                    ab_test_id, variant_name, 'error',
                    metric_value=0.0,
                    conversation_id=conversation_id
                )
            
            # Estimate tokens (rough estimate: ~4 chars per token)
            if response_text:
                estimated_tokens = len(response_text) / 4
                ConversationStorage.record_ab_metric(
                    ab_test_id, variant_name, 'tokens',
                    metric_value=estimated_tokens,
                    conversation_id=conversation_id
                )
            
            return True
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error recording LLM response metrics: {e}", exc_info=True)
            return False
