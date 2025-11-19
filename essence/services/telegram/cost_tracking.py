"""
Cost tracking for STT, TTS, and LLM usage.

Tracks costs per user and conversation, calculates costs in real-time using pricing tables,
and provides cost query and billing report functionality.

Note: PostgreSQL is not available, so all database operations return defaults.
Cost calculation functions still work, but cost recording is disabled.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_db_connection() -> None:
    """
    Get PostgreSQL database connection.

    Note: PostgreSQL is not available. This function will raise an exception
    if called. All methods in this module handle this gracefully.

    Raises:
        RuntimeError: Always raised since PostgreSQL is not available for MVP
    """
    # PostgreSQL is not available - raise an exception that will be caught by callers
    raise RuntimeError(
        "PostgreSQL is not available. Cost tracking methods will return defaults."
    )


# Pricing tables (cost per unit)
# These can be configured via environment variables or database
DEFAULT_PRICING = {
    "stt": {
        "per_minute": 0.006,  # $0.006 per minute of audio
        "per_character": 0.0,  # No per-character cost for STT
    },
    "tts": {
        "per_minute": 0.015,  # $0.015 per minute of audio
        "per_character": 0.0,  # No per-character cost for TTS
    },
    "llm": {
        "per_token_input": 0.00001,  # $0.00001 per input token
        "per_token_output": 0.00003,  # $0.00003 per output token
        "per_character": 0.0,  # Fallback: estimate from characters if tokens not available
    },
}


def get_pricing(service: str) -> Dict[str, float]:
    """
    Get pricing for a service.

    Args:
        service: Service name ('stt', 'tts', or 'llm')

    Returns:
        Dictionary with pricing information
    """
    # Try to get from environment variables first
    env_key = f"{service.upper()}_PRICING"
    pricing_json = os.getenv(env_key)
    if pricing_json:
        try:
            return json.loads(pricing_json)
        except json.JSONDecodeError:
            logger.warning(f"Invalid pricing JSON for {service}, using defaults")

    # Fall back to defaults
    return DEFAULT_PRICING.get(service, {})


def calculate_stt_cost(
    audio_duration_seconds: float, pricing: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate STT cost based on audio duration.

    Args:
        audio_duration_seconds: Audio duration in seconds
        pricing: Optional pricing dictionary (uses default if not provided)

    Returns:
        Cost in USD
    """
    if pricing is None:
        pricing = get_pricing("stt")

    duration_minutes = audio_duration_seconds / 60.0
    cost = duration_minutes * pricing.get("per_minute", 0.0)

    return round(cost, 6)  # Round to 6 decimal places


def calculate_tts_cost(
    audio_duration_seconds: float, pricing: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate TTS cost based on audio duration.

    Args:
        audio_duration_seconds: Audio duration in seconds
        pricing: Optional pricing dictionary (uses default if not provided)

    Returns:
        Cost in USD
    """
    if pricing is None:
        pricing = get_pricing("tts")

    duration_minutes = audio_duration_seconds / 60.0
    cost = duration_minutes * pricing.get("per_minute", 0.0)

    return round(cost, 6)


def calculate_llm_cost(
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    input_characters: Optional[int] = None,
    output_characters: Optional[int] = None,
    pricing: Optional[Dict[str, float]] = None,
) -> float:
    """
    Calculate LLM cost based on tokens or characters.

    Args:
        input_tokens: Number of input tokens (preferred)
        output_tokens: Number of output tokens (preferred)
        input_characters: Number of input characters (fallback if tokens not available)
        output_characters: Number of output characters (fallback if tokens not available)
        pricing: Optional pricing dictionary (uses default if not provided)

    Returns:
        Cost in USD
    """
    if pricing is None:
        pricing = get_pricing("llm")

    cost = 0.0

    # Use tokens if available (preferred)
    if input_tokens is not None:
        cost += input_tokens * pricing.get("per_token_input", 0.0)
    elif input_characters is not None:
        # Estimate tokens from characters (rough estimate: ~4 chars per token)
        estimated_tokens = input_characters / 4.0
        cost += estimated_tokens * pricing.get("per_token_input", 0.0)

    if output_tokens is not None:
        cost += output_tokens * pricing.get("per_token_output", 0.0)
    elif output_characters is not None:
        # Estimate tokens from characters (rough estimate: ~4 chars per token)
        estimated_tokens = output_characters / 4.0
        cost += estimated_tokens * pricing.get("per_token_output", 0.0)

    return round(cost, 6)


def record_cost(
    service: str,
    user_id: str,
    conversation_id: Optional[str] = None,
    cost: float = 0.0,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Record a cost entry in the database.

    Note: PostgreSQL is not available, so this always returns False (cost not tracked).

    Args:
        service: Service name ('stt', 'tts', or 'llm')
        user_id: User ID
        conversation_id: Optional conversation ID
        cost: Cost in USD
        metadata: Optional metadata dictionary

    Returns:
        False (PostgreSQL not available)
    """
    logger.debug(
        f"PostgreSQL not available - cannot record cost: {service} for user {user_id}, cost=${cost:.6f}"
    )
    return False


def get_user_costs(
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Get cost summary for a user.

    Note: PostgreSQL is not available, so this always returns empty cost summary.

    Args:
        user_id: User ID
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        Dictionary with empty cost summary
    """
    logger.debug(
        f"PostgreSQL not available - returning empty cost summary for user {user_id}"
    )
    return {
        "user_id": user_id,
        "total_cost": 0.0,
        "services": {},
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }


def get_conversation_costs(
    conversation_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Get cost summary for a conversation.

    Note: PostgreSQL is not available, so this always returns empty cost summary.

    Args:
        conversation_id: Conversation ID
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        Dictionary with empty cost summary
    """
    logger.debug(
        f"PostgreSQL not available - returning empty cost summary for conversation {conversation_id}"
    )
    return {
        "conversation_id": conversation_id,
        "total_cost": 0.0,
        "services": {},
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }


def get_conversation_id_from_user_chat(user_id: str, chat_id: str) -> Optional[str]:
    """
    Get conversation ID from user_id and chat_id.

    Note: PostgreSQL is not available, so this always returns None.

    Args:
        user_id: User ID
        chat_id: Chat ID (session_id in database)

    Returns:
        None (PostgreSQL not available)
    """
    logger.debug(
        f"PostgreSQL not available - cannot get conversation ID for user {user_id}, chat {chat_id}"
    )
    return None


def generate_billing_report(
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Generate a detailed billing report for a user.

    Note: PostgreSQL is not available, so this always returns empty billing report.

    Args:
        user_id: User ID
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        Dictionary with empty billing report
    """
    logger.debug(
        f"PostgreSQL not available - returning empty billing report for user {user_id}"
    )
    return {
        "user_id": user_id,
        "total_cost": 0.0,
        "period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "service_breakdown": {},
        "entries": [],
        "entry_count": 0,
    }
