"""Shared agent response handler for chat services."""
import logging
from pathlib import Path
import os
from typing import Optional, Iterator, Tuple, List, Dict, Any

from .response import (
    call_chat_response_agent,
    format_agent_response,
    stream_chat_response_agent
)
from essence.chat.utils.tracing import get_tracer
from essence.chat.message_history import get_message_history
from essence.agents import (
    AgenticReasoner,
    ConversationContext,
    should_use_agentic_flow,
    Planner,
    Executor,
    Reflector,
    LLMClient,
    get_reasoning_cache,
)
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Global agentic reasoner instance (lazy initialization)
_agentic_reasoner: Optional[AgenticReasoner] = None


def _get_agentic_reasoner() -> Optional[AgenticReasoner]:
    """
    Get or create the global agentic reasoner instance.
    
    Returns:
        AgenticReasoner instance, or None if LLM is not available
    """
    global _agentic_reasoner
    
    if _agentic_reasoner is None:
        try:
            # Initialize LLM client (will fail gracefully if TensorRT-LLM is not available)
            llm_client = LLMClient()
            
            # Initialize components
            cache = get_reasoning_cache()
            planner = Planner(llm_client=llm_client, enable_cache=True, cache=cache)
            executor = Executor(available_tools={})  # No tools for chat handler (coding agent has tools)
            reflector = Reflector(llm_client=llm_client, enable_cache=True, cache=cache)
            
            # Create reasoner
            _agentic_reasoner = AgenticReasoner(
                planner=planner,
                executor=executor,
                reflector=reflector,
                llm_client=llm_client,
                enable_cache=True,
                cache=cache,
                enable_early_termination=True,
            )
            
            logger.info("Agentic reasoner initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize agentic reasoner: {e}. Will use direct flow only.")
            return None
    
    return _agentic_reasoner


def _build_conversation_context(
    user_id: Optional[int],
    chat_id: Optional[int],
    platform: str,
    user_message: str,
) -> ConversationContext:
    """
    Build a ConversationContext from user/chat IDs and message history.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        platform: Platform name
        user_message: Current user message
        
    Returns:
        ConversationContext instance
    """
    context = ConversationContext(
        user_id=str(user_id) if user_id else None,
        chat_id=str(chat_id) if chat_id else None,
    )
    
    # Get message history if available
    try:
        message_history = get_message_history()
        if user_id and chat_id:
            # Get recent messages for this conversation
            recent_messages = message_history.get_messages(
                user_id=str(user_id),
                chat_id=str(chat_id),
                platform=platform,
                limit=10  # Last 10 messages for context
            )
            
            # Convert to conversation history format
            context.message_history = [
                {
                    "role": "user" if msg.message_type == "text" else "assistant",
                    "content": msg.message_content,
                    "timestamp": msg.timestamp.isoformat(),
                }
                for msg in reversed(recent_messages)  # Oldest first
            ]
    except Exception as e:
        logger.debug(f"Could not retrieve message history: {e}")
        # Continue without history
    
    return context


def _format_agentic_response(result) -> Dict[str, Any]:
    """
    Format an agentic reasoning result for chat response.
    
    Args:
        result: ReasoningResult from agentic reasoner
        
    Returns:
        Dictionary compatible with chat response format
    """
    if result.success:
        return {
            "success": True,
            "message": result.final_response or "I've processed your request.",
            "raw_response": {
                "type": "agentic_reasoning",
                "iterations": result.iterations,
                "total_time": result.total_time,
                "plan": str(result.plan) if result.plan else None,
                "execution_results": [
                    {
                        "step_id": r.step_id,
                        "success": r.success,
                        "output": r.output,
                        "error": r.error,
                    }
                    for r in result.execution_results
                ] if result.execution_results else [],
                "reflection": {
                    "goal_achieved": result.reflection.goal_achieved if result.reflection else None,
                    "confidence": result.reflection.confidence if result.reflection else None,
                    "issues": result.reflection.issues_found if result.reflection else [],
                } if result.reflection else None,
            }
        }
    else:
        return {
            "success": False,
            "error": result.error or "Unknown error in agentic reasoning",
            "message": result.final_response or "❌ I encountered an error processing your request. Please try again.",
        }


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
            
            # Build conversation context
            context = _build_conversation_context(user_id, chat_id, platform, user_message)
            
            # Get message history for decision logic
            message_history = context.message_history or []
            
            # Decision logic: determine if we should use agentic flow
            use_agentic_flow = False
            reasoner = _get_agentic_reasoner()
            
            if reasoner:
                try:
                    use_agentic_flow = should_use_agentic_flow(
                        user_message=user_message,
                        message_history=message_history,
                        available_tools=None,  # No tools available in chat handler
                    )
                    span.set_attribute("agentic_flow_available", True)
                    span.set_attribute("use_agentic_flow", use_agentic_flow)
                except Exception as e:
                    logger.warning(f"Error in decision logic: {e}. Falling back to direct flow.")
                    use_agentic_flow = False
            
            # Use agentic flow if decision logic says so
            if use_agentic_flow and reasoner:
                try:
                    span.set_attribute("flow_type", "agentic")
                    logger.info(f"Using agentic reasoning flow for user {user_id}, chat {chat_id}")
                    
                    with tracer.start_as_current_span("agentic.reason") as reason_span:
                        reasoning_result = reasoner.reason(
                            user_message=user_message,
                            context=context,
                            available_tools=None,  # No tools in chat handler
                        )
                        reason_span.set_attribute("iterations", reasoning_result.iterations)
                        reason_span.set_attribute("total_time", reasoning_result.total_time)
                        reason_span.set_attribute("success", reasoning_result.success)
                    
                    # Format agentic response
                    response_data = _format_agentic_response(reasoning_result)
                    formatted_message = response_data.get("message", "I've processed your request.")
                    
                    # Truncate if needed
                    if len(formatted_message) > max_message_length:
                        formatted_message = formatted_message[:max_message_length-10] + "\n\n... (message truncated)"
                        span.set_attribute("truncated", True)
                    
                    span.set_attribute("response_length", len(formatted_message))
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    
                    return {
                        "success": response_data.get("success", True),
                        "message": formatted_message,
                        "raw_response": response_data.get("raw_response", {}),
                        "error": response_data.get("error"),
                    }
                except Exception as e:
                    logger.error(f"Error in agentic reasoning flow: {e}. Falling back to direct flow.", exc_info=True)
                    span.record_exception(e)
                    # Fall through to direct flow
            
            # Direct flow (existing implementation)
            span.set_attribute("flow_type", "direct")
            logger.debug(f"Using direct response flow for user {user_id}, chat {chat_id}")
            
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



