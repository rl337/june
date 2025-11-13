"""
Cost tracking for STT, TTS, and LLM usage.

Tracks costs per user and conversation, calculates costs in real-time using pricing tables,
and provides cost query and billing report functionality.
"""
import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


def get_db_connection():
    """Get PostgreSQL database connection."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "conversations")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    
    conn_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
    if db_password:
        conn_string += f" password={db_password}"
    
    return psycopg2.connect(conn_string)


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
    }
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


def calculate_stt_cost(audio_duration_seconds: float, pricing: Optional[Dict[str, float]] = None) -> float:
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


def calculate_tts_cost(audio_duration_seconds: float, pricing: Optional[Dict[str, float]] = None) -> float:
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
    pricing: Optional[Dict[str, float]] = None
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
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Record a cost entry in the database.
    
    Args:
        service: Service name ('stt', 'tts', or 'llm')
        user_id: User ID
        conversation_id: Optional conversation ID
        cost: Cost in USD
        metadata: Optional metadata dictionary
        
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO cost_tracking (service, user_id, conversation_id, cost, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (service, str(user_id), conversation_id, cost, json.dumps(metadata or {}))
            )
            conn.commit()
            logger.debug(f"Recorded cost: {service} for user {user_id}, cost=${cost:.6f}")
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error recording cost: {e}", exc_info=True)
        return False


def get_user_costs(
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get cost summary for a user.
    
    Args:
        user_id: User ID
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        Dictionary with cost summary
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build date filter
            date_filter = ""
            params = [str(user_id)]
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
            
            # Get total costs by service
            cursor.execute(
                f"""
                SELECT 
                    service,
                    COUNT(*) as usage_count,
                    SUM(cost) as total_cost,
                    AVG(cost) as avg_cost
                FROM cost_tracking
                WHERE user_id = %s {date_filter}
                GROUP BY service
                ORDER BY service
                """,
                params
            )
            service_costs = cursor.fetchall()
            
            # Get total cost
            cursor.execute(
                f"""
                SELECT SUM(cost) as total_cost
                FROM cost_tracking
                WHERE user_id = %s {date_filter}
                """,
                params
            )
            total_result = cursor.fetchone()
            total_cost = float(total_result['total_cost']) if total_result['total_cost'] else 0.0
            
            return {
                "user_id": user_id,
                "total_cost": round(total_cost, 6),
                "services": {
                    row['service']: {
                        "usage_count": row['usage_count'],
                        "total_cost": round(float(row['total_cost']), 6),
                        "avg_cost": round(float(row['avg_cost']), 6)
                    }
                    for row in service_costs
                },
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting user costs: {e}", exc_info=True)
        return {
            "user_id": user_id,
            "total_cost": 0.0,
            "services": {},
            "error": str(e)
        }


def get_conversation_costs(
    conversation_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get cost summary for a conversation.
    
    Args:
        conversation_id: Conversation ID
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        Dictionary with cost summary
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build date filter
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
            
            # Get total costs by service
            cursor.execute(
                f"""
                SELECT 
                    service,
                    COUNT(*) as usage_count,
                    SUM(cost) as total_cost,
                    AVG(cost) as avg_cost
                FROM cost_tracking
                WHERE conversation_id = %s {date_filter}
                GROUP BY service
                ORDER BY service
                """,
                params
            )
            service_costs = cursor.fetchall()
            
            # Get total cost
            cursor.execute(
                f"""
                SELECT SUM(cost) as total_cost
                FROM cost_tracking
                WHERE conversation_id = %s {date_filter}
                """,
                params
            )
            total_result = cursor.fetchone()
            total_cost = float(total_result['total_cost']) if total_result['total_cost'] else 0.0
            
            return {
                "conversation_id": conversation_id,
                "total_cost": round(total_cost, 6),
                "services": {
                    row['service']: {
                        "usage_count": row['usage_count'],
                        "total_cost": round(float(row['total_cost']), 6),
                        "avg_cost": round(float(row['avg_cost']), 6)
                    }
                    for row in service_costs
                },
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting conversation costs: {e}", exc_info=True)
        return {
            "conversation_id": conversation_id,
            "total_cost": 0.0,
            "services": {},
            "error": str(e)
        }


def get_conversation_id_from_user_chat(user_id: str, chat_id: str) -> Optional[str]:
    """
    Get conversation ID from user_id and chat_id.
    
    Args:
        user_id: User ID
        chat_id: Chat ID (session_id in database)
        
    Returns:
        Conversation ID (UUID string) or None if not found
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
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
                return str(result[0])
            return None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting conversation ID: {e}", exc_info=True)
        return None


def generate_billing_report(
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Generate a detailed billing report for a user.
    
    Args:
        user_id: User ID
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        Dictionary with detailed billing report
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build date filter
            date_filter = ""
            params = [str(user_id)]
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
            
            # Get detailed cost entries
            cursor.execute(
                f"""
                SELECT 
                    id,
                    service,
                    conversation_id,
                    cost,
                    metadata,
                    created_at
                FROM cost_tracking
                WHERE user_id = %s {date_filter}
                ORDER BY created_at DESC
                """,
                params
            )
            entries = cursor.fetchall()
            
            # Get summary by service
            cursor.execute(
                f"""
                SELECT 
                    service,
                    COUNT(*) as usage_count,
                    SUM(cost) as total_cost,
                    MIN(cost) as min_cost,
                    MAX(cost) as max_cost,
                    AVG(cost) as avg_cost
                FROM cost_tracking
                WHERE user_id = %s {date_filter}
                GROUP BY service
                ORDER BY service
                """,
                params
            )
            service_summary = cursor.fetchall()
            
            # Get total cost
            cursor.execute(
                f"""
                SELECT SUM(cost) as total_cost
                FROM cost_tracking
                WHERE user_id = %s {date_filter}
                """,
                params
            )
            total_result = cursor.fetchone()
            total_cost = float(total_result['total_cost']) if total_result['total_cost'] else 0.0
            
            return {
                "user_id": user_id,
                "total_cost": round(total_cost, 6),
                "period": {
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None
                },
                "service_breakdown": {
                    row['service']: {
                        "usage_count": row['usage_count'],
                        "total_cost": round(float(row['total_cost']), 6),
                        "min_cost": round(float(row['min_cost']), 6),
                        "max_cost": round(float(row['max_cost']), 6),
                        "avg_cost": round(float(row['avg_cost']), 6)
                    }
                    for row in service_summary
                },
                "entries": [
                    {
                        "id": str(entry['id']),
                        "service": entry['service'],
                        "conversation_id": str(entry['conversation_id']) if entry['conversation_id'] else None,
                        "cost": round(float(entry['cost']), 6),
                        "metadata": entry['metadata'] if entry['metadata'] else {},
                        "created_at": entry['created_at'].isoformat() if entry['created_at'] else None
                    }
                    for entry in entries
                ],
                "entry_count": len(entries)
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error generating billing report: {e}", exc_info=True)
        return {
            "user_id": user_id,
            "total_cost": 0.0,
            "error": str(e)
        }
