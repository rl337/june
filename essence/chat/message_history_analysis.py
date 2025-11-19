"""
Message history analysis tools for agents and debugging.

Provides programmatic access to message history with analysis capabilities
for comparing expected vs actual message content and identifying rendering issues.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from essence.chat.message_history import MessageHistoryEntry, get_message_history

logger = logging.getLogger(__name__)


def get_recent_messages(
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    platform: Optional[str] = None,
    hours: int = 1,
    limit: Optional[int] = None,
) -> List[MessageHistoryEntry]:
    """
    Get recent messages within a time window.

    Convenience function for agents to query recent message history.

    Args:
        user_id: Filter by user ID (optional)
        chat_id: Filter by chat/channel ID (optional)
        platform: Filter by platform ("telegram" or "discord") (optional)
        hours: Number of hours to look back (default: 1)
        limit: Maximum number of results (optional)

    Returns:
        List of MessageHistoryEntry objects from the last N hours
    """
    history = get_message_history()
    cutoff_time = datetime.now() - timedelta(hours=hours)

    messages = history.get_messages(
        user_id=user_id,
        chat_id=chat_id,
        platform=platform,
        limit=None,  # Get all, then filter by time
    )

    # Filter by time
    recent = [msg for msg in messages if msg.timestamp >= cutoff_time]

    # Apply limit
    if limit:
        recent = recent[:limit]

    return recent


def analyze_rendering_issues(
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    platform: Optional[str] = None,
    hours: int = 24,
) -> Dict[str, Any]:
    """
    Analyze message history for rendering issues.

    Identifies potential rendering problems by comparing raw_text vs formatted_text,
    checking for truncation, and analyzing split messages.

    Args:
        user_id: Filter by user ID (optional)
        chat_id: Filter by chat/channel ID (optional)
        platform: Filter by platform (optional)
        hours: Number of hours to analyze (default: 24)

    Returns:
        Dictionary with analysis results including:
        - total_messages: Total messages analyzed
        - split_messages: Count of messages that were split
        - truncated_messages: Count of messages that were truncated
        - format_mismatches: Count of messages where raw_text != formatted_text
        - issues: List of specific issues found
    """
    messages = get_recent_messages(
        user_id=user_id, chat_id=chat_id, platform=platform, hours=hours
    )

    analysis = {
        "total_messages": len(messages),
        "split_messages": 0,
        "truncated_messages": 0,
        "format_mismatches": 0,
        "exceeded_limit": 0,
        "issues": [],
    }

    for msg in messages:
        metadata = msg.rendering_metadata or {}

        # Check for split messages
        if metadata.get("is_split"):
            analysis["split_messages"] += 1
            if metadata.get("total_parts", 0) > 2:
                analysis["issues"].append(
                    {
                        "type": "multiple_splits",
                        "message_id": msg.message_id,
                        "timestamp": msg.timestamp.isoformat(),
                        "total_parts": metadata.get("total_parts"),
                        "part_number": metadata.get("part_number"),
                    }
                )

        # Check for truncation
        if metadata.get("was_truncated"):
            analysis["truncated_messages"] += 1
            analysis["issues"].append(
                {
                    "type": "truncated",
                    "message_id": msg.message_id,
                    "timestamp": msg.timestamp.isoformat(),
                    "message_length": metadata.get("message_length"),
                    "max_length": metadata.get("telegram_max_length")
                    or metadata.get("discord_max_length"),
                }
            )

        # Check for format mismatches
        if msg.raw_text and msg.formatted_text and msg.raw_text != msg.formatted_text:
            analysis["format_mismatches"] += 1
            # Only flag if significant difference (more than just whitespace)
            if msg.raw_text.strip() != msg.formatted_text.strip():
                analysis["issues"].append(
                    {
                        "type": "format_mismatch",
                        "message_id": msg.message_id,
                        "timestamp": msg.timestamp.isoformat(),
                        "raw_length": len(msg.raw_text),
                        "formatted_length": len(msg.formatted_text),
                    }
                )

        # Check for messages exceeding platform limits
        if not metadata.get("within_limit", True):
            analysis["exceeded_limit"] += 1
            analysis["issues"].append(
                {
                    "type": "exceeded_limit",
                    "message_id": msg.message_id,
                    "timestamp": msg.timestamp.isoformat(),
                    "message_length": metadata.get("message_length"),
                    "max_length": metadata.get("telegram_max_length")
                    or metadata.get("discord_max_length"),
                }
            )

    return analysis


def compare_expected_vs_actual(
    expected_text: str,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    platform: Optional[str] = None,
    hours: int = 1,
) -> Optional[Dict[str, Any]]:
    """
    Compare expected message text with what was actually sent.

    Useful for debugging rendering issues - finds the most recent message that
    matches the expected text (or is similar) and compares it.

    Args:
        expected_text: The expected message text
        user_id: Filter by user ID (optional)
        chat_id: Filter by chat/channel ID (optional)
        platform: Filter by platform (optional)
        hours: Number of hours to look back (default: 1)

    Returns:
        Dictionary with comparison results, or None if no matching message found
    """
    messages = get_recent_messages(
        user_id=user_id, chat_id=chat_id, platform=platform, hours=hours
    )

    if not messages:
        return None

    # Find the most recent message that matches or is similar
    best_match = None
    best_similarity = 0.0

    for msg in messages:
        # Check if raw_text or message_content matches
        if msg.raw_text == expected_text or msg.message_content == expected_text:
            best_match = msg
            best_similarity = 1.0
            break

        # Calculate simple similarity (common substring ratio)
        if msg.raw_text:
            common_chars = sum(1 for a, b in zip(expected_text, msg.raw_text) if a == b)
            similarity = common_chars / max(len(expected_text), len(msg.raw_text))
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = msg

    if not best_match:
        return None

    comparison = {
        "expected_text": expected_text,
        "expected_length": len(expected_text),
        "actual_text": best_match.message_content,
        "actual_length": len(best_match.message_content),
        "raw_text": best_match.raw_text,
        "raw_length": len(best_match.raw_text) if best_match.raw_text else 0,
        "formatted_text": best_match.formatted_text,
        "formatted_length": len(best_match.formatted_text)
        if best_match.formatted_text
        else 0,
        "similarity": best_similarity,
        "timestamp": best_match.timestamp.isoformat(),
        "message_id": best_match.message_id,
        "rendering_metadata": best_match.rendering_metadata,
        "differences": [],
    }

    # Identify specific differences
    if best_match.raw_text and best_match.raw_text != expected_text:
        comparison["differences"].append(
            {
                "type": "raw_text_mismatch",
                "description": "Raw text differs from expected",
            }
        )

    if best_match.message_content != expected_text:
        comparison["differences"].append(
            {
                "type": "content_mismatch",
                "description": "Actual message content differs from expected",
            }
        )

    metadata = best_match.rendering_metadata or {}
    if metadata.get("was_truncated"):
        comparison["differences"].append(
            {
                "type": "truncated",
                "description": f"Message was truncated (length: {metadata.get('message_length')}, max: {metadata.get('telegram_max_length') or metadata.get('discord_max_length')})",
            }
        )

    if metadata.get("is_split"):
        comparison["differences"].append(
            {
                "type": "split",
                "description": f"Message was split into {metadata.get('total_parts')} parts",
            }
        )

    return comparison


def validate_message_for_platform(
    text: str, platform: str, parse_mode: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate message text against platform requirements.

    Checks if a message would be valid for the specified platform,
    including length limits, format requirements, etc.

    Args:
        text: Message text to validate
        platform: Platform name ("telegram" or "discord")
        parse_mode: Parse mode for Telegram ("HTML" or "Markdown") (optional)

    Returns:
        Dictionary with validation results:
        - valid: Whether message is valid
        - within_length_limit: Whether message is within length limit
        - length: Message length
        - max_length: Platform max length
        - warnings: List of warnings
        - errors: List of errors
    """
    result = {
        "valid": True,
        "within_length_limit": True,
        "length": len(text),
        "max_length": 4096 if platform == "telegram" else 2000,
        "warnings": [],
        "errors": [],
    }

    # Check length limits
    if result["length"] > result["max_length"]:
        result["valid"] = False
        result["within_length_limit"] = False
        result["errors"].append(
            f"Message exceeds {platform} limit: {result['length']} > {result['max_length']} characters"
        )
    elif result["length"] > result["max_length"] * 0.9:  # Warn if > 90% of limit
        result["warnings"].append(
            f"Message is close to {platform} limit: {result['length']}/{result['max_length']} characters"
        )

    # Platform-specific validations
    if platform == "telegram":
        # Use appropriate validator based on parse_mode
        from essence.chat.platform_validators import get_validator

        validator = get_validator(platform, parse_mode)
        is_valid_format, format_errors = validator.validate(text, lenient=False)
        if not is_valid_format:
            result["valid"] = False
            result["errors"].extend(format_errors)
        elif format_errors:
            result["warnings"].extend(format_errors)

        # Check for entities that might cause issues (HTML mode specific)
        if parse_mode == "HTML" and (
            "&" in text
            and "&amp;" not in text
            and "&lt;" not in text
            and "&gt;" not in text
        ):
            result["warnings"].append(
                "Unescaped '&' character may cause issues in HTML mode"
            )

    elif platform == "discord":
        # Use Discord validator
        from essence.chat.platform_validators import get_validator

        validator = get_validator(platform)
        is_valid_format, format_errors = validator.validate(text, lenient=False)
        if not is_valid_format:
            result["valid"] = False
            result["errors"].extend(format_errors)
        elif format_errors:
            result["warnings"].extend(format_errors)

    return result


def get_message_statistics(
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    platform: Optional[str] = None,
    hours: int = 24,
) -> Dict[str, Any]:
    """
    Get statistics about messages in a time window.

    Provides aggregated statistics useful for debugging and analysis.

    Args:
        user_id: Filter by user ID (optional)
        chat_id: Filter by chat/channel ID (optional)
        platform: Filter by platform (optional)
        hours: Number of hours to analyze (default: 24)

    Returns:
        Dictionary with statistics
    """
    messages = get_recent_messages(
        user_id=user_id, chat_id=chat_id, platform=platform, hours=hours
    )

    if not messages:
        return {
            "total_messages": 0,
            "by_platform": {},
            "by_type": {},
            "average_length": 0,
            "max_length": 0,
            "min_length": 0,
        }

    lengths = [len(msg.message_content) for msg in messages]

    stats = {
        "total_messages": len(messages),
        "by_platform": {},
        "by_type": {},
        "average_length": sum(lengths) / len(lengths) if lengths else 0,
        "max_length": max(lengths) if lengths else 0,
        "min_length": min(lengths) if lengths else 0,
    }

    # Count by platform
    for msg in messages:
        stats["by_platform"][msg.platform] = (
            stats["by_platform"].get(msg.platform, 0) + 1
        )
        stats["by_type"][msg.message_type] = (
            stats["by_type"].get(msg.message_type, 0) + 1
        )

    return stats
