"""
Todorama Integration for User Interaction Tasks

Handles creating and managing todorama tasks for user interactions via Telegram/Discord.
Replaces the USER_MESSAGES.md file-based approach with todorama task management.
"""
import logging
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Try to import todorama MCP client
try:
    # We'll use MCP todorama service via the MCP client
    # For now, we'll create a wrapper that can be called
    TODORAMA_AVAILABLE = True
except ImportError:
    TODORAMA_AVAILABLE = False
    logger.warning("Todorama MCP client not available - falling back to file-based approach")


def create_user_interaction_task(
    user_id: str,
    chat_id: str,
    platform: str,
    content: str,
    message_id: Optional[str] = None,
    username: Optional[str] = None,
) -> Optional[int]:
    """
    Create a todorama task for a user interaction.
    
    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        platform: Platform ("telegram" or "discord")
        content: Message content
        message_id: Optional platform message ID
        username: Optional username
        
    Returns:
        Task ID if created successfully, None otherwise
    """
    try:
        # Import here to avoid circular dependencies
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        
        # Get project ID from environment (default: 1 for june project)
        project_id = int(os.getenv("TODORAMA_PROJECT_ID", "1"))
        agent_id = os.getenv("TODORAMA_AGENT_ID", "cursor-agent")
        
        # Format task title
        username_str = f"@{username} " if username else ""
        title = f"User Interaction: {platform.capitalize()} - {username_str}({user_id})"
        
        # Format task instruction with full context
        instruction = f"""User message from {platform.capitalize()}:
- User: {username_str}(user_id: {user_id})
- Chat ID: {chat_id}
- Message ID: {message_id or 'N/A'}
- Platform: {platform.capitalize()}
- Content: {content}

Please process this user interaction and respond appropriately."""
        
        verification = f"""Verify response by:
1. Agent has processed the user message
2. Agent has sent a response via {platform.capitalize()}
3. Task can be marked as complete"""
        
        # Create task via MCP todorama
        # Note: This requires MCP todorama service to be available
        # For now, we'll use a subprocess call or direct MCP client
        
        # TODO: Implement actual MCP todorama client call
        # For now, return None to indicate we need to implement this
        logger.warning("Todorama task creation not yet implemented - needs MCP client integration")
        return None
        
    except Exception as e:
        logger.error(f"Failed to create todorama task for user interaction: {e}", exc_info=True)
        return None


def complete_user_interaction_task(task_id: int, notes: Optional[str] = None) -> bool:
    """
    Mark a user interaction task as complete in todorama.
    
    Args:
        task_id: Task ID to complete
        notes: Optional completion notes
        
    Returns:
        True if completed successfully, False otherwise
    """
    try:
        agent_id = os.getenv("TODORAMA_AGENT_ID", "cursor-agent")
        
        # TODO: Implement actual MCP todorama client call
        logger.warning("Todorama task completion not yet implemented - needs MCP client integration")
        return False
        
    except Exception as e:
        logger.error(f"Failed to complete todorama task {task_id}: {e}", exc_info=True)
        return False


def get_user_interaction_tasks(user_id: Optional[str] = None, platform: Optional[str] = None) -> list[Dict[str, Any]]:
    """
    Get user interaction tasks from todorama.
    
    Args:
        user_id: Optional user ID to filter by
        platform: Optional platform to filter by
        
    Returns:
        List of task dictionaries
    """
    try:
        # TODO: Implement actual MCP todorama client call
        logger.warning("Todorama task query not yet implemented - needs MCP client integration")
        return []
        
    except Exception as e:
        logger.error(f"Failed to query todorama tasks: {e}", exc_info=True)
        return []
