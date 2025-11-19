"""
Decision Logic for Agentic Flow

Determines when to use agentic reasoning flow vs direct response.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def should_use_agentic_flow(
    user_message: str,
    message_history: Optional[List[Dict[str, Any]]] = None,
    available_tools: Optional[List[Any]] = None,
    complexity_threshold: int = 200,
) -> bool:
    """
    Determine if agentic flow should be used for a request.

    Args:
        user_message: The user's message/request
        message_history: Optional conversation history
        available_tools: Optional list of available tools
        complexity_threshold: Message length threshold for complexity (default: 200)

    Returns:
        True if agentic flow should be used, False for direct response
    """
    # Check for explicit keywords requesting reasoning
    agentic_keywords = ["plan", "step", "reason", "think", "break down", "how to"]
    if any(keyword in user_message.lower() for keyword in agentic_keywords):
        logger.debug("Agentic flow: explicit reasoning keyword detected")
        return True

    # Check complexity indicators
    if len(user_message) > complexity_threshold:
        logger.debug(
            f"Agentic flow: message length ({len(user_message)}) exceeds threshold ({complexity_threshold})"
        )
        return True

    # Check if tools are likely needed
    tool_keywords = [
        "file",
        "code",
        "write",
        "create",
        "modify",
        "execute",
        "run",
        "implement",
    ]
    if any(keyword in user_message.lower() for keyword in tool_keywords):
        logger.debug("Agentic flow: tool keywords detected")
        return True

    # Check conversation history for complexity
    if message_history and len(message_history) > 3:
        logger.debug(
            f"Agentic flow: multi-turn conversation ({len(message_history)} messages)"
        )
        return True

    # Check if tools are available and request might need them
    if available_tools and len(available_tools) > 0:
        # If tools are available and message suggests tool usage, use agentic flow
        tool_indicators = ["with", "using", "via", "tool", "function", "method"]
        if any(indicator in user_message.lower() for indicator in tool_indicators):
            logger.debug("Agentic flow: tool indicators detected with available tools")
            return True

    # Default: use direct response for simple requests
    logger.debug("Direct response: simple request, no agentic flow needed")
    return False


def estimate_request_complexity(
    user_message: str,
    message_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Estimate the complexity of a request.

    Args:
        user_message: The user's message
        message_history: Optional conversation history

    Returns:
        Complexity level: "simple", "moderate", or "complex"
    """
    complexity_score = 0

    # Length-based scoring
    if len(user_message) > 500:
        complexity_score += 3
    elif len(user_message) > 200:
        complexity_score += 2
    elif len(user_message) > 100:
        complexity_score += 1

    # Keyword-based scoring
    complex_keywords = [
        "multiple",
        "several",
        "complex",
        "advanced",
        "sophisticated",
        "comprehensive",
    ]
    moderate_keywords = [
        "create",
        "modify",
        "update",
        "analyze",
        "process",
        "implement",
    ]

    complexity_score += sum(
        2 for keyword in complex_keywords if keyword in user_message.lower()
    )
    complexity_score += sum(
        1 for keyword in moderate_keywords if keyword in user_message.lower()
    )

    # Conversation history scoring
    if message_history:
        if len(message_history) > 5:
            complexity_score += 2
        elif len(message_history) > 2:
            complexity_score += 1

    # Determine complexity level
    if complexity_score >= 5:
        return "complex"
    elif complexity_score >= 2:
        return "moderate"
    else:
        return "simple"
