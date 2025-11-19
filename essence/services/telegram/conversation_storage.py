"""
Conversation storage for managing conversation data and metadata.

Uses in-memory storage for MVP (PostgreSQL removed).
Provides methods to store and retrieve conversation information including
language preferences and prompt templates.
"""
import csv
import io
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# PostgreSQL removed for MVP - make imports optional
try:
    import psycopg2
    from psycopg2 import IntegrityError
    from psycopg2.extras import RealDictCursor

    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    IntegrityError = Exception
    RealDictCursor = None
    PSYCOPG2_AVAILABLE = False

logger = logging.getLogger(__name__)

# Default language preference
DEFAULT_LANGUAGE = "en"

# In-memory storage for MVP (PostgreSQL removed)
_in_memory_storage: Dict[tuple, Dict[str, Any]] = defaultdict(
    dict
)  # (user_id, chat_id) -> metadata dict
_in_memory_prompt_templates: Dict[
    tuple, Dict[str, Any]
] = {}  # (user_id, template_name) -> template dict


def get_db_connection() -> None:
    """
    Get PostgreSQL database connection.

    Note: PostgreSQL is not available for MVP. This function will raise an exception
    if called. All methods in ConversationStorage handle this gracefully.

    Raises:
        RuntimeError: Always raised since PostgreSQL is not available for MVP
    """
    # PostgreSQL is not available - raise an exception that will be caught by callers
    raise RuntimeError(
        "PostgreSQL is not available for MVP. ConversationStorage methods will return defaults."
    )


class ConversationStorage:
    """Storage class for conversation data and metadata."""

    @staticmethod
    def get_language_preference(user_id: str, chat_id: str) -> str:
        """
        Get language preference for a conversation.

        Uses in-memory storage (PostgreSQL removed for MVP).

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)

        Returns:
            Language code (ISO 639-1), defaults to "en" if not set
        """
        key = (str(user_id), str(chat_id))
        metadata = _in_memory_storage.get(key, {})
        language_preference = metadata.get("language_preference")

        if language_preference:
            logger.debug(
                f"Language preference for {user_id}/{chat_id}: {language_preference}"
            )
            return language_preference

        # Default to "en" if not found
        logger.debug(
            f"No language preference found for {user_id}/{chat_id}, defaulting to {DEFAULT_LANGUAGE}"
        )
        return DEFAULT_LANGUAGE

    @staticmethod
    def set_language_preference(user_id: str, chat_id: str, language_code: str) -> bool:
        """
        Set language preference for a conversation.

        Uses in-memory storage (PostgreSQL removed for MVP).

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            language_code: Language code (ISO 639-1) to store

        Returns:
            True if language preference was set successfully, False otherwise
        """
        # Normalize language code (lowercase)
        language_code = language_code.lower() if language_code else DEFAULT_LANGUAGE

        key = (str(user_id), str(chat_id))
        _in_memory_storage[key]["language_preference"] = language_code

        logger.info(f"Set language preference for {user_id}/{chat_id}: {language_code}")
        return True

    @staticmethod
    def get_user_preferences(user_id: str, chat_id: str) -> Dict[str, Any]:
        """
        Get user preferences (name, favorite_color, etc.) for a conversation.

        Uses in-memory storage (PostgreSQL removed for MVP).

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)

        Returns:
            Dictionary with user preferences (name, favorite_color, etc.), empty dict if not set
        """
        key = (str(user_id), str(chat_id))
        metadata = _in_memory_storage.get(key, {})

        # Extract user preferences from metadata
        preferences = {
            "name": metadata.get("user_name"),
            "favorite_color": metadata.get("favorite_color"),
        }
        # Remove None values
        preferences = {k: v for k, v in preferences.items() if v is not None}

        if preferences:
            logger.debug(f"User preferences for {user_id}/{chat_id}: {preferences}")
        else:
            logger.debug(f"No user preferences found for {user_id}/{chat_id}")

        return preferences

    @staticmethod
    def set_user_preferences(
        user_id: str,
        chat_id: str,
        name: Optional[str] = None,
        favorite_color: Optional[str] = None,
    ) -> bool:
        """
        Set user preferences (name, favorite_color) for a conversation.

        Uses in-memory storage (PostgreSQL removed for MVP).

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)
            name: Optional user name to store
            favorite_color: Optional favorite color to store

        Returns:
            True if preferences were set successfully, False otherwise
        """
        key = (str(user_id), str(chat_id))

        # Update user preferences (only set provided values)
        if name is not None:
            _in_memory_storage[key]["user_name"] = name.strip() if name else None
        if favorite_color is not None:
            _in_memory_storage[key]["favorite_color"] = (
                favorite_color.strip() if favorite_color else None
            )

        logger.info(
            f"Set user preferences for {user_id}/{chat_id}: name={name}, favorite_color={favorite_color}"
        )
        return True

    @staticmethod
    def get_conversation_analytics(user_id: str, chat_id: str) -> Dict[str, Any]:
        """
        Get analytics metrics for a specific conversation.

        Uses in-memory storage (PostgreSQL removed for MVP).
        For MVP, returns empty analytics.

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID (maps to session_id in database)

        Returns:
            Dictionary with analytics metrics (empty for MVP)
        """
        # PostgreSQL not available for MVP - return empty analytics
        logger.debug(
            f"PostgreSQL not available - returning empty analytics for {user_id}/{chat_id}"
        )
        return {
            "conversation_id": None,
            "message_count": 0,
            "user_message_count": 0,
            "assistant_message_count": 0,
            "average_response_time_seconds": 0.0,
            "engagement_score": 0.0,
            "first_message_at": None,
            "last_message_at": None,
        }

    @staticmethod
    def get_dashboard_analytics(
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated analytics across all conversations (dashboard view).

        Uses in-memory storage (PostgreSQL removed for MVP).
        For MVP, returns empty analytics.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with aggregated metrics (empty for MVP)
        """
        # PostgreSQL not available for MVP - return empty analytics
        logger.debug(f"PostgreSQL not available - returning empty dashboard analytics")
        return {
            "total_conversations": 0,
            "total_messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "average_response_time_seconds": 0.0,
            "active_users": 0,
        }

    @staticmethod
    def generate_analytics_report(
        format: str = "json",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
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
            dashboard_data = ConversationStorage.get_dashboard_analytics(
                start_date, end_date
            )

            if format.lower() == "csv":
                # Generate CSV report
                output = io.StringIO()
                writer = csv.writer(output)

                # Header
                writer.writerow(["Metric", "Value"])
                writer.writerow(
                    [
                        "Total Conversations",
                        dashboard_data.get("total_conversations", 0),
                    ]
                )
                writer.writerow(
                    ["Total Messages", dashboard_data.get("total_messages", 0)]
                )
                writer.writerow(
                    ["User Messages", dashboard_data.get("user_messages", 0)]
                )
                writer.writerow(
                    ["Assistant Messages", dashboard_data.get("assistant_messages", 0)]
                )
                writer.writerow(
                    [
                        "Average Response Time (seconds)",
                        dashboard_data.get("average_response_time_seconds", 0.0),
                    ]
                )
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
            return (
                json.dumps(error_report)
                if format.lower() != "csv"
                else f"Error,{str(e)}"
            )

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
        open_braces = template_text.count("{")
        close_braces = template_text.count("}")

        if open_braces != close_braces:
            return (
                False,
                f"Unbalanced braces: {open_braces} opening, {close_braces} closing",
            )

        # Check for valid variable syntax and no nested braces
        import re

        # Pattern to match {variable} where variable is alphanumeric + underscore
        variable_pattern = r"\{([a-zA-Z0-9_]+)\}"
        matches = re.findall(variable_pattern, template_text)

        # Check for nested braces (e.g., {{variable}})
        if re.search(r"\{\{|\}\}", template_text):
            return False, "Nested braces are not allowed"

        # Check for invalid variable names (non-alphanumeric/underscore)
        invalid_vars = re.findall(r"\{([^}]+)\}", template_text)
        for var in invalid_vars:
            if not re.match(r"^[a-zA-Z0-9_]+$", var):
                return (
                    False,
                    f"Invalid variable name: '{var}'. Variables must contain only alphanumeric characters and underscores",
                )

        return True, None

    @staticmethod
    def create_prompt_template(
        name: str,
        template_text: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        description: Optional[str] = None,
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
        is_valid, error_msg = ConversationStorage.validate_prompt_template(
            template_text
        )
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
                    (name, template_text, user_id, conversation_id, description),
                )

                template_id = cursor.fetchone()[0]
                conn.commit()
                logger.info(
                    f"Created prompt template: {template_id} (name={name}, user_id={user_id}, conversation_id={conversation_id})"
                )
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
                    (template_id,),
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
    def get_prompt_template_for_user(
        user_id: str, name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a user-specific prompt template.

        Uses in-memory storage (PostgreSQL removed for MVP).
        For MVP, returns None (no custom templates stored).

        Args:
            user_id: User ID
            name: Optional template name (if None, gets first active template for user)

        Returns:
            Template dictionary or None if not found
        """
        # For MVP, prompt templates are not stored in-memory
        # Return None to use default prompts
        logger.debug(
            f"Prompt templates not available in MVP (in-memory storage). Returning None for user {user_id}"
        )
        return None

    @staticmethod
    def get_prompt_template_for_conversation(
        user_id: str, chat_id: str, name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a conversation-specific prompt template, with fallback to user template.

        Uses in-memory storage (PostgreSQL removed for MVP).
        For MVP, returns None (no custom templates stored).

        Args:
            user_id: User ID
            chat_id: Chat ID (session_id in database)
            name: Optional template name

        Returns:
            Template dictionary or None if not found
        """
        # For MVP, prompt templates are not stored in-memory
        # Return None to use default prompts
        logger.debug(
            f"Prompt templates not available in MVP (in-memory storage). Returning None for {user_id}/{chat_id}"
        )
        return None

    @staticmethod
    def list_prompt_templates(
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        is_active: Optional[bool] = None,
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
        is_active: Optional[bool] = None,
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
            is_valid, error_msg = ConversationStorage.validate_prompt_template(
                template_text
            )
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
                    "DELETE FROM prompt_templates WHERE id = %s", (template_id,)
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
        end_date: Optional[datetime] = None,
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
                    (str(user_id), str(chat_id)),
                )
                conversation = cursor.fetchone()

                if not conversation:
                    raise ValueError(
                        f"Conversation not found for user_id={user_id}, chat_id={chat_id}"
                    )

                conversation_id = conversation["id"]

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
                    params,
                )
                messages = cursor.fetchall()

                # Prepare conversation data
                conversation_data = {
                    "conversation_id": str(conversation["id"]),
                    "user_id": conversation["user_id"],
                    "chat_id": conversation["session_id"],
                    "created_at": conversation["created_at"].isoformat()
                    if conversation["created_at"]
                    else None,
                    "updated_at": conversation["updated_at"].isoformat()
                    if conversation["updated_at"]
                    else None,
                    "metadata": conversation["metadata"]
                    if conversation["metadata"]
                    else {},
                    "message_count": len(messages),
                    "messages": [
                        {
                            "role": msg["role"],
                            "content": msg["content"],
                            "created_at": msg["created_at"].isoformat()
                            if msg["created_at"]
                            else None,
                            "metadata": msg["metadata"] if msg["metadata"] else {},
                        }
                        for msg in messages
                    ],
                }

                # Export in requested format
                if format.lower() == "json":
                    return json.dumps(
                        conversation_data, indent=2, ensure_ascii=False
                    ).encode("utf-8")

                elif format.lower() == "txt":
                    # Generate plain text export
                    output = io.StringIO()
                    output.write(f"Conversation Export\n")
                    output.write(f"{'=' * 50}\n\n")
                    output.write(
                        f"Conversation ID: {conversation_data['conversation_id']}\n"
                    )
                    output.write(f"User ID: {conversation_data['user_id']}\n")
                    output.write(f"Chat ID: {conversation_data['chat_id']}\n")
                    output.write(f"Created: {conversation_data['created_at']}\n")
                    output.write(f"Updated: {conversation_data['updated_at']}\n")
                    output.write(
                        f"Message Count: {conversation_data['message_count']}\n"
                    )
                    if conversation_data["metadata"]:
                        output.write(
                            f"Metadata: {json.dumps(conversation_data['metadata'], indent=2)}\n"
                        )
                    output.write(f"\n{'=' * 50}\n")
                    output.write(f"Messages\n")
                    output.write(f"{'=' * 50}\n\n")

                    for msg in conversation_data["messages"]:
                        role_display = msg["role"].upper()
                        timestamp = msg["created_at"] if msg["created_at"] else "N/A"
                        output.write(f"[{timestamp}] {role_display}:\n")
                        output.write(f"{msg['content']}\n")
                        if msg["metadata"]:
                            output.write(
                                f"Metadata: {json.dumps(msg['metadata'], indent=2)}\n"
                            )
                        output.write(f"\n{'-' * 50}\n\n")

                    return output.getvalue().encode("utf-8")

                elif format.lower() == "pdf":
                    # Generate PDF export
                    try:
                        from reportlab.lib.enums import TA_CENTER, TA_LEFT
                        from reportlab.lib.pagesizes import letter
                        from reportlab.lib.styles import (
                            ParagraphStyle,
                            getSampleStyleSheet,
                        )
                        from reportlab.lib.units import inch
                        from reportlab.pdfbase import pdfmetrics
                        from reportlab.pdfbase.ttfonts import TTFont
                        from reportlab.platypus import (
                            PageBreak,
                            Paragraph,
                            SimpleDocTemplate,
                            Spacer,
                        )
                    except ImportError:
                        raise ImportError(
                            "reportlab is required for PDF export. Install it with: pip install reportlab"
                        )

                    buffer = io.BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=letter)
                    story = []
                    styles = getSampleStyleSheet()

                    # Title
                    title_style = ParagraphStyle(
                        "CustomTitle",
                        parent=styles["Heading1"],
                        fontSize=16,
                        textColor="#000000",
                        spaceAfter=30,
                        alignment=TA_CENTER,
                    )
                    story.append(Paragraph("Conversation Export", title_style))
                    story.append(Spacer(1, 0.2 * inch))

                    # Conversation info
                    info_style = styles["Normal"]
                    story.append(
                        Paragraph(
                            f"<b>Conversation ID:</b> {conversation_data['conversation_id']}",
                            info_style,
                        )
                    )
                    story.append(
                        Paragraph(
                            f"<b>User ID:</b> {conversation_data['user_id']}",
                            info_style,
                        )
                    )
                    story.append(
                        Paragraph(
                            f"<b>Chat ID:</b> {conversation_data['chat_id']}",
                            info_style,
                        )
                    )
                    story.append(
                        Paragraph(
                            f"<b>Created:</b> {conversation_data['created_at']}",
                            info_style,
                        )
                    )
                    story.append(
                        Paragraph(
                            f"<b>Updated:</b> {conversation_data['updated_at']}",
                            info_style,
                        )
                    )
                    story.append(
                        Paragraph(
                            f"<b>Message Count:</b> {conversation_data['message_count']}",
                            info_style,
                        )
                    )
                    if conversation_data["metadata"]:
                        story.append(
                            Paragraph(
                                f"<b>Metadata:</b> {json.dumps(conversation_data['metadata'])}",
                                info_style,
                            )
                        )
                    story.append(Spacer(1, 0.3 * inch))

                    # Messages
                    story.append(Paragraph("<b>Messages</b>", styles["Heading2"]))
                    story.append(Spacer(1, 0.2 * inch))

                    for msg in conversation_data["messages"]:
                        role_display = msg["role"].upper()
                        timestamp = msg["created_at"] if msg["created_at"] else "N/A"

                        # Message header
                        header_style = ParagraphStyle(
                            "MessageHeader",
                            parent=styles["Normal"],
                            fontSize=10,
                            textColor="#666666",
                            spaceAfter=6,
                        )
                        story.append(
                            Paragraph(
                                f"<b>[{timestamp}] {role_display}:</b>", header_style
                            )
                        )

                        # Message content (escape HTML)
                        content = (
                            msg["content"]
                            .replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        )
                        # Replace newlines with <br/>
                        content = content.replace("\n", "<br/>")
                        story.append(Paragraph(content, info_style))

                        if msg["metadata"]:
                            metadata_text = (
                                json.dumps(msg["metadata"])
                                .replace("&", "&amp;")
                                .replace("<", "&lt;")
                                .replace(">", "&gt;")
                            )
                            story.append(
                                Paragraph(
                                    f"<i>Metadata: {metadata_text}</i>", info_style
                                )
                            )

                        story.append(Spacer(1, 0.15 * inch))

                    doc.build(story)
                    buffer.seek(0)
                    return buffer.read()

                else:
                    raise ValueError(
                        f"Unsupported export format: {format}. Supported formats: json, txt, pdf"
                    )

            finally:
                conn.close()
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(
                f"Error exporting conversation for {user_id}/{chat_id}: {e}",
                exc_info=True,
            )
            raise

    # ==================== A/B Testing Methods ====================

    @staticmethod
    def create_ab_test(
        name: str,
        variants: List[Dict[str, Any]],
        description: Optional[str] = None,
        traffic_split: float = 1.0,
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
                    (name, description, json.dumps(variants), traffic_split),
                )
                test_id = cursor.fetchone()[0]
                conn.commit()
                logger.info(f"Created A/B test: {test_id} (name={name})")
                return str(test_id)
            except IntegrityError as e:
                conn.rollback()
                logger.error(
                    f"A/B test name already exists or constraint violation: {e}"
                )
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

        Uses in-memory storage (PostgreSQL removed for MVP).
        For MVP, returns None (AB tests not supported).

        Args:
            test_id: Test ID (UUID string)

        Returns:
            Test dictionary or None if not found
        """
        # PostgreSQL not available for MVP - AB tests not supported
        logger.debug(
            f"PostgreSQL not available - AB tests not supported for MVP, returning None for test {test_id}"
        )
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
                    if isinstance(test_dict["variants"], str):
                        test_dict["variants"] = json.loads(test_dict["variants"])
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
        is_active: Optional[bool] = None,
    ) -> bool:
        """
        Update an A/B test.

        Uses in-memory storage (PostgreSQL removed for MVP).
        For MVP, returns False (AB tests not supported).

        Args:
            test_id: Test ID (UUID string)
            description: Optional new description
            variants: Optional new variants list
            traffic_split: Optional new traffic split
            is_active: Optional new active status

        Returns:
            True if successful, False otherwise (always False for MVP)
        """
        # PostgreSQL not available for MVP - AB tests not supported
        logger.debug(
            f"PostgreSQL not available - AB tests not supported for MVP, cannot update test {test_id}"
        )
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
        test_id: str, conversation_id: str, force_variant: Optional[str] = None
    ) -> Optional[str]:
        """
        Assign a variant to a conversation for an A/B test.

        Uses in-memory storage (PostgreSQL removed for MVP).
        For MVP, returns None (AB tests not supported).

        Args:
            test_id: Test ID (UUID string)
            conversation_id: Conversation ID (UUID string)
            force_variant: Optional variant name to force assignment (for testing)

        Returns:
            Variant name assigned, or None if assignment failed (always None for MVP)
        """
        # PostgreSQL not available for MVP - AB tests not supported
        logger.debug(
            f"PostgreSQL not available - AB tests not supported for MVP, cannot assign variant for test {test_id}"
        )
        return None

    @staticmethod
    def record_ab_metric(
        test_id: str,
        variant_name: str,
        metric_type: str,
        metric_value: Optional[float] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Record a metric for an A/B test variant.

        Uses in-memory storage (PostgreSQL removed for MVP).
        For MVP, returns False (AB tests not supported).

        Args:
            test_id: Test ID (UUID string)
            variant_name: Variant name
            metric_type: Metric type (e.g., 'response_time', 'tokens', 'satisfaction', 'error')
            metric_value: Optional numeric metric value
            conversation_id: Optional conversation ID
            metadata: Optional additional metadata

        Returns:
            True if successful, False otherwise (always False for MVP)
        """
        # PostgreSQL not available for MVP - AB tests not supported
        logger.debug(
            f"PostgreSQL not available - AB tests not supported for MVP, cannot record metric for test {test_id}"
        )
        return False

    @staticmethod
    def get_ab_metrics(
        test_id: str,
        variant_name: Optional[str] = None,
        metric_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
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
                    if isinstance(metric_dict.get("metadata"), str):
                        metric_dict["metadata"] = json.loads(metric_dict["metadata"])
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

            variants = test["variants"]
            if isinstance(variants, str):
                variants = json.loads(variants)

            variant_names = [v.get("name") for v in variants]

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
                        (test_id, variant_name),
                    )
                    metrics = cursor.fetchall()

                    # Calculate statistics
                    variant_stats = {
                        "variant_name": variant_name,
                        "total_metrics": sum(m["count"] for m in metrics),
                        "metrics_by_type": {},
                    }

                    # Group by metric type
                    for metric in metrics:
                        metric_type = metric["metric_type"]
                        if metric_type not in variant_stats["metrics_by_type"]:
                            variant_stats["metrics_by_type"][metric_type] = {
                                "count": 0,
                                "sum": 0.0,
                                "values": [],
                            }
                        variant_stats["metrics_by_type"][metric_type][
                            "count"
                        ] += metric["count"]
                        if metric["metric_value"] is not None:
                            variant_stats["metrics_by_type"][metric_type]["sum"] += (
                                metric["metric_value"] * metric["count"]
                            )
                            variant_stats["metrics_by_type"][metric_type][
                                "values"
                            ].extend([metric["metric_value"]] * metric["count"])

                    # Calculate averages
                    for metric_type, data in variant_stats["metrics_by_type"].items():
                        if data["count"] > 0 and data["sum"] > 0:
                            data["average"] = data["sum"] / data["count"]
                        else:
                            data["average"] = 0.0

                    # Calculate error rate
                    error_count = sum(
                        m["count"]
                        for m in metrics
                        if m["metric_type"] == "error"
                        and m["metric_value"]
                        and m["metric_value"] > 0
                    )
                    total_requests = variant_stats["total_metrics"]
                    variant_stats["error_rate"] = (
                        (error_count / total_requests * 100)
                        if total_requests > 0
                        else 0.0
                    )

                    statistics[variant_name] = variant_stats

                return {
                    "test_id": test_id,
                    "test_name": test.get("name"),
                    "variants": statistics,
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
        user_id: str, chat_id: str, ab_test_id: Optional[str] = None
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
                    (str(user_id), str(chat_id)),
                )
                result = cursor.fetchone()

                if result:
                    conversation_id = str(result["id"])
                else:
                    # Create conversation
                    cursor.execute(
                        """
                        INSERT INTO conversations (user_id, session_id)
                        VALUES (%s, %s)
                        RETURNING id
                        """,
                        (str(user_id), str(chat_id)),
                    )
                    conversation_id = str(cursor.fetchone()[0])
                    conn.commit()
            finally:
                conn.close()

            result = {
                "conversation_id": conversation_id,
                "variant_name": None,
                "variant_config": None,
            }

            # A/B testing: Assign variant if test is provided
            if ab_test_id and conversation_id:
                variant_name = ConversationStorage.assign_ab_variant(
                    ab_test_id, conversation_id
                )
                if variant_name:
                    # Get variant configuration
                    test = ConversationStorage.get_ab_test(ab_test_id)
                    if test:
                        variants = test.get("variants", [])
                        if isinstance(variants, str):
                            variants = json.loads(variants)
                        variant_config = next(
                            (v for v in variants if v.get("name") == variant_name), None
                        )
                        if variant_config:
                            logger.info(
                                f"Using A/B test variant {variant_name} for conversation {conversation_id}"
                            )
                            result["variant_name"] = variant_name
                            result["variant_config"] = variant_config

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
        error: Optional[Exception] = None,
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
                ab_test_id,
                variant_name,
                "response_time",
                metric_value=response_time,
                conversation_id=conversation_id,
            )

            # Record error if occurred
            if error:
                ConversationStorage.record_ab_metric(
                    ab_test_id,
                    variant_name,
                    "error",
                    metric_value=1.0,
                    conversation_id=conversation_id,
                    metadata={"error": str(error)},
                )
            else:
                # Record success (error=0)
                ConversationStorage.record_ab_metric(
                    ab_test_id,
                    variant_name,
                    "error",
                    metric_value=0.0,
                    conversation_id=conversation_id,
                )

            # Estimate tokens (rough estimate: ~4 chars per token)
            if response_text:
                estimated_tokens = len(response_text) / 4
                ConversationStorage.record_ab_metric(
                    ab_test_id,
                    variant_name,
                    "tokens",
                    metric_value=estimated_tokens,
                    conversation_id=conversation_id,
                )

            return True
        except (RuntimeError, psycopg2.OperationalError) as e:
            # PostgreSQL not available - return default
            logger.debug(f"PostgreSQL not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Error recording LLM response metrics: {e}", exc_info=True)
            return False
