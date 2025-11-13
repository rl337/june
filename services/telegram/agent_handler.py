"""Shared agent response handler for both Telegram and HTTP endpoints."""
import logging
from pathlib import Path
import os
from typing import Optional, Iterator, Tuple

from agent_response import (
    call_telegram_response_agent,
    format_agent_response_for_telegram,
    stream_telegram_response_agent
)

logger = logging.getLogger(__name__)


def find_agenticness_directory():
    """Find the agenticness directory from various possible locations."""
    telegram_dir = Path(__file__).parent.parent
    possible_paths = [
        Path("/app/agenticness"),  # Mounted volume in container
        Path("/home/rlee/dev/agenticness"),  # Absolute fallback (if running outside container)
        telegram_dir.parent.parent / "agenticness",  # Relative path (if running outside container)
        telegram_dir.parent / "agenticness",  # Another relative path
    ]
    
    logger.info(f"Searching for agenticness directory. Checking paths: {[str(p) for p in possible_paths]}")
    
    for path in possible_paths:
        path_str = str(path)
        exists = path.exists()
        script_path = path / "scripts" / "telegram_response_agent.sh"
        script_exists = script_path.exists()
        
        logger.info(f"Checking {path_str}: path.exists()={exists}, script.exists()={script_exists}")
        
        if exists and script_exists:
            logger.info(f"Found agenticness directory at: {path_str}")
            return path_str
    
    # If not found, log error with debug info
    logger.error("Could not find agenticness directory. Tried paths: " + ", ".join(str(p) for p in possible_paths))
    debug_info = []
    for path in possible_paths:
        path_str = str(path)
        debug_info.append(f"{path_str}: exists={os.path.exists(path_str)}")
        if os.path.exists(path_str):
            try:
                contents = os.listdir(path_str)
                debug_info.append(f"  contents: {contents[:5]}")
            except Exception as e:
                debug_info.append(f"  listdir error: {e}")
    logger.error("Debug info: " + "; ".join(debug_info))
    return None


def process_agent_message(
    user_message: str,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None
) -> dict:
    """
    Process a user message through the TelegramResponse agent.
    
    Args:
        user_message: The message from the user
        user_id: Telegram user ID for session identification (optional, but required for context preservation)
        chat_id: Telegram chat ID for session identification (optional, but required for context preservation)
        
    Returns:
        Dictionary with 'success' (bool), 'message' (str), and optionally 'error' (str)
    """
    try:
        # Find agenticness directory
        agenticness_dir = find_agenticness_directory()
        
        if agenticness_dir is None:
            return {
                "success": False,
                "error": "Agent system not properly configured",
                "message": "⚠️ I'm unable to process your message right now. The agent system is not properly configured."
            }
        
        # Call the agent with user_id and chat_id for session support
        response_data = call_telegram_response_agent(user_message, agenticness_dir, user_id, chat_id)
        
        # Format the response
        formatted_message = format_agent_response_for_telegram(response_data)
        
        # Telegram has a 4096 character limit, so truncate if needed
        if len(formatted_message) > 4096:
            formatted_message = formatted_message[:4090] + "\n\n... (message truncated)"
        
        return {
            "success": True,
            "message": formatted_message,
            "raw_response": response_data
        }
        
    except Exception as e:
        logger.error(f"Error processing agent message: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "❌ I encountered an error processing your message. Please try again."
        }


def stream_agent_message(
    user_message: str,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    line_timeout: float = 30.0,
    max_total_time: float = 300.0
) -> Iterator[Tuple[str, bool]]:
    """
    Stream agent responses as they arrive.
    
    Args:
        user_message: The message from the user
        user_id: Telegram user ID for session identification
        chat_id: Telegram chat ID for session identification
        line_timeout: Seconds to wait for a new JSON line before timing out
        max_total_time: Maximum total seconds for the entire operation
    
    Yields:
        Tuples of (message_text, is_final) where:
        - message_text: Human-readable text to send to Telegram
        - is_final: True if this is the final message, False for intermediate messages
    """
    try:
        # Find agenticness directory
        agenticness_dir = find_agenticness_directory()
        
        if agenticness_dir is None:
            yield ("⚠️ I'm unable to process your message right now. The agent system is not properly configured.", True)
            return
        
        # Stream responses from the agent
        for message, is_final in stream_telegram_response_agent(
            user_message,
            agenticness_dir,
            user_id,
            chat_id,
            line_timeout=line_timeout,
            max_total_time=max_total_time
        ):
            # Truncate if needed (Telegram has 4096 character limit)
            if message and len(message) > 4096:
                message = message[:4090] + "\n\n... (message truncated)"
            yield (message, is_final)
        
    except Exception as e:
        logger.error(f"Error streaming agent message: {e}", exc_info=True)
        yield ("❌ I encountered an error processing your message. Please try again.", True)



