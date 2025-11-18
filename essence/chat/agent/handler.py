"""Shared agent response handler for chat services."""
import logging
from pathlib import Path
import os
from typing import Optional, Iterator, Tuple

from .response import (
    call_chat_response_agent,
    format_agent_response,
    stream_chat_response_agent
)
from essence.chat.utils.tracing import get_tracer
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def find_agenticness_directory(script_name: str = "telegram_response_agent.sh") -> Optional[str]:
    """
    Find the agenticness directory from various possible locations.
    
    Args:
        script_name: Name of the script file to look for (default: "telegram_response_agent.sh")
        
    Returns:
        Path to the agenticness directory as a string, or None if not found
    """
    service_dir = Path(__file__).parent.parent.parent
    possible_paths = [
        Path("/app/agenticness"),  # Mounted volume in container
        Path("/home/rlee/dev/agenticness"),  # Absolute fallback (if running outside container)
        service_dir.parent / "agenticness",  # Relative path (if running outside container)
        service_dir / "agenticness",  # Another relative path
    ]
    
    logger.info(f"Searching for agenticness directory. Checking paths: {[str(p) for p in possible_paths]}")
    
    for path in possible_paths:
        path_str = str(path)
        exists = path.exists()
        script_path = path / "scripts" / script_name
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
    chat_id: Optional[int] = None,
    platform: str = "telegram",
    agent_script_name: str = "telegram_response_agent.sh",
    agent_script_simple_name: str = "telegram_response_agent_simple.sh",
    max_message_length: int = 4096
) -> dict:
    """
    Process a user message through the chat response agent.
    
    Args:
        user_message: The message from the user
        user_id: User ID for session identification (optional, but required for context preservation)
        chat_id: Chat ID for session identification (optional, but required for context preservation)
        platform: Platform name (telegram, discord, etc.)
        agent_script_name: Name of the session-aware agent script
        agent_script_simple_name: Name of the simple agent script (no session)
        max_message_length: Maximum message length for the platform
        
    Returns:
        Dictionary with 'success' (bool), 'message' (str), and optionally 'error' (str)
    """
    with tracer.start_as_current_span("agent.process_message") as span:
        try:
            span.set_attribute("platform", platform)
            span.set_attribute("user_id", str(user_id) if user_id else "unknown")
            span.set_attribute("chat_id", str(chat_id) if chat_id else "unknown")
            span.set_attribute("message_length", len(user_message) if user_message else 0)
            span.set_attribute("agent_script_name", agent_script_name)
            
            # Find agenticness directory
            agenticness_dir = find_agenticness_directory(agent_script_name)
            
            if agenticness_dir is None:
                span.set_attribute("agent_available", False)
                span.set_status(trace.Status(trace.StatusCode.ERROR, "Agent system not properly configured"))
                return {
                    "success": False,
                    "error": "Agent system not properly configured",
                    "message": "⚠️ I'm unable to process your message right now. The agent system is not properly configured."
                }
            
            span.set_attribute("agent_available", True)
            span.set_attribute("agenticness_dir", agenticness_dir)
            
            # Call the agent with user_id and chat_id for session support
            with tracer.start_as_current_span("agent.call_response_agent") as call_span:
                call_span.set_attribute("user_id", str(user_id) if user_id else "unknown")
                call_span.set_attribute("chat_id", str(chat_id) if chat_id else "unknown")
                call_span.set_attribute("platform", platform)
                try:
                    response_data = call_chat_response_agent(
                        user_message, 
                        agenticness_dir, 
                        user_id, 
                        chat_id,
                        agent_script_name=agent_script_name,
                        agent_script_simple_name=agent_script_simple_name,
                        platform=platform
                    )
                    call_span.set_status(trace.Status(trace.StatusCode.OK))
                except Exception as e:
                    call_span.record_exception(e)
                    call_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise
            
            # Format the response
            with tracer.start_as_current_span("agent.format_response") as format_span:
                format_span.set_attribute("max_length", max_message_length)
                formatted_message = format_agent_response(response_data, max_length=max_message_length)
                
                # Truncate if needed
                if len(formatted_message) > max_message_length:
                    formatted_message = formatted_message[:max_message_length-10] + "\n\n... (message truncated)"
                    format_span.set_attribute("truncated", True)
                
                format_span.set_attribute("formatted_length", len(formatted_message))
                format_span.set_status(trace.Status(trace.StatusCode.OK))
            
            span.set_attribute("response_length", len(formatted_message))
            span.set_status(trace.Status(trace.StatusCode.OK))
            
            return {
                "success": True,
                "message": formatted_message,
                "raw_response": response_data
            }
            
        except Exception as e:
            logger.error(f"Error processing agent message: {e}", exc_info=True)
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
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
    max_total_time: float = 300.0,
    platform: str = "telegram",
    agent_script_name: str = "telegram_response_agent.sh",
    agent_script_simple_name: str = "telegram_response_agent_simple.sh",
    max_message_length: int = 4096
) -> Iterator[Tuple[str, bool]]:
    """
    Stream agent responses as they arrive.
    
    Args:
        user_message: The message from the user
        user_id: User ID for session identification
        chat_id: Chat ID for session identification
        line_timeout: Seconds to wait for a new JSON line before timing out
        max_total_time: Maximum total seconds for the entire operation
        platform: Platform name (telegram, discord, etc.)
        agent_script_name: Name of the session-aware agent script
        agent_script_simple_name: Name of the simple agent script (no session)
        max_message_length: Maximum message length for the platform
    
    Yields:
        Tuples of (message_text, is_final, message_type) where:
        - message_text: Human-readable text to send to the chat platform
        - is_final: True if this is the final message, False for intermediate messages
        - message_type: Type of message ("assistant" for incremental chunks, "result" for final result, None for errors)
    """
    with tracer.start_as_current_span("agent.stream_message") as span:
        try:
            span.set_attribute("platform", platform)
            span.set_attribute("user_id", str(user_id) if user_id else "unknown")
            span.set_attribute("chat_id", str(chat_id) if chat_id else "unknown")
            span.set_attribute("message_length", len(user_message) if user_message else 0)
            span.set_attribute("line_timeout", line_timeout)
            span.set_attribute("max_total_time", max_total_time)
            span.set_attribute("agent_script_name", agent_script_name)
            
            # Find agenticness directory
            agenticness_dir = find_agenticness_directory(agent_script_name)
            
            if agenticness_dir is None:
                span.set_attribute("agent_available", False)
                span.set_status(trace.Status(trace.StatusCode.ERROR, "Agent system not properly configured"))
                yield ("⚠️ I'm unable to process your message right now. The agent system is not properly configured.", True, None)
                return
            
            span.set_attribute("agent_available", True)
            span.set_attribute("agenticness_dir", agenticness_dir)
            
            chunk_count = 0
            # Stream responses from the agent
            for message, is_final, message_type in stream_chat_response_agent(
                user_message,
                agenticness_dir,
                user_id,
                chat_id,
                line_timeout=line_timeout,
                max_total_time=max_total_time,
                agent_script_name=agent_script_name,
                agent_script_simple_name=agent_script_simple_name,
                platform=platform
            ):
                chunk_count += 1
                span.set_attribute("chunk_count", chunk_count)
                span.set_attribute("is_final", is_final)
                span.set_attribute("message_type", message_type or "unknown")
                
                # Truncate if needed
                if message and len(message) > max_message_length:
                    message = message[:max_message_length-10] + "\n\n... (message truncated)"
                    span.set_attribute("message_truncated", True)
                
                if message:
                    span.set_attribute("message_length", len(message))
                
                yield (message, is_final, message_type)
            
            span.set_attribute("total_chunks", chunk_count)
            span.set_status(trace.Status(trace.StatusCode.OK))
        
        except Exception as e:
            logger.error(f"Error streaming agent message: {e}", exc_info=True)
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            yield ("❌ I encountered an error processing your message. Please try again.", True, None)



