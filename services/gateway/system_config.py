"""System configuration module for admin dashboard."""
import os
import logging
import json
import psycopg2
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor
from datetime import datetime
from db_pool import get_db_pool

logger = logging.getLogger(__name__)


def get_system_config() -> Dict[str, Any]:
    """
    Get current system configuration.
    
    Returns:
        Dictionary with system configuration organized by categories
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get the latest configuration
            cursor.execute("""
                SELECT config_data
                FROM system_config
                ORDER BY created_at DESC
                LIMIT 1
            """)
            
            result = cursor.fetchone()
            
            if not result:
                # Return default configuration from environment variables
                return _get_default_config()
            
            # Parse configuration data
            config_data = result['config_data']
            
            # If config_data is a string, parse it as JSON
            if isinstance(config_data, str):
                try:
                    config_data = json.loads(config_data)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse config_data as JSON, using defaults")
                    return _get_default_config()
            
            # Ensure config_data is a dict
            if not isinstance(config_data, dict):
                logger.warning("config_data is not a dict, using defaults")
                return _get_default_config()
            
            # Merge with defaults to ensure all categories and fields are present
            default_config = _get_default_config()
            config_by_category = {}
            
            for category in default_config:
                if category in config_data:
                    # Merge category config with defaults
                    config_by_category[category] = {
                        **default_config[category],
                        **config_data[category]
                    }
                else:
                    # Use default if category not in stored config
                    config_by_category[category] = default_config[category]
            
            return config_by_category
    except Exception as e:
        logger.error(f"Error getting system config: {e}", exc_info=True)
        # Return default config on error
        return _get_default_config()


def _get_default_config() -> Dict[str, Any]:
    """Get default system configuration from environment variables."""
    return {
        "model_settings": {
            "default_model": os.getenv("DEFAULT_LLM_MODEL", "qwen3-30b-a3b"),
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2048")),
            "context_length": int(os.getenv("LLM_CONTEXT_LENGTH", "8192")),
            "enable_streaming": os.getenv("LLM_ENABLE_STREAMING", "true").lower() == "true"
        },
        "service_settings": {
            "gateway_url": os.getenv("GATEWAY_URL", "http://localhost:8000"),
            "inference_api_url": os.getenv("INFERENCE_API_URL", "http://localhost:8001"),
            "stt_service_url": os.getenv("STT_SERVICE_URL", "http://localhost:8002"),
            "tts_service_url": os.getenv("TTS_SERVICE_URL", "http://localhost:8003"),
            "telegram_bot_url": os.getenv("TELEGRAM_BOT_URL", "http://localhost:8005")
        },
        "security_settings": {
            "jwt_secret": os.getenv("JWT_SECRET", ""),  # Don't expose actual secret
            "jwt_expiration_hours": int(os.getenv("JWT_EXPIRATION_HOURS", "24")),
            "enable_rate_limiting": os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true",
            "max_requests_per_minute": int(os.getenv("MAX_REQUESTS_PER_MINUTE", "60")),
            "require_https": os.getenv("REQUIRE_HTTPS", "false").lower() == "true"
        },
        "feature_flags": {
            "enable_voice_messages": os.getenv("ENABLE_VOICE_MESSAGES", "true").lower() == "true",
            "enable_rag": os.getenv("ENABLE_RAG", "true").lower() == "true",
            "enable_ab_testing": os.getenv("ENABLE_AB_TESTING", "false").lower() == "true",
            "enable_cost_tracking": os.getenv("ENABLE_COST_TRACKING", "true").lower() == "true",
            "enable_analytics": os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"
        }
    }


def validate_config(config: Dict[str, Any]) -> tuple:
    """
    Validate system configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Validate model_settings
        if "model_settings" in config:
            model = config["model_settings"]
            if "temperature" in model:
                temp = model["temperature"]
                if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                    return False, "Temperature must be between 0 and 2"
            if "max_tokens" in model:
                tokens = model["max_tokens"]
                if not isinstance(tokens, int) or tokens < 1 or tokens > 100000:
                    return False, "Max tokens must be between 1 and 100000"
            if "context_length" in model:
                ctx = model["context_length"]
                if not isinstance(ctx, int) or ctx < 1 or ctx > 100000:
                    return False, "Context length must be between 1 and 100000"
        
        # Validate service_settings URLs
        if "service_settings" in config:
            services = config["service_settings"]
            for key, url in services.items():
                if isinstance(url, str) and url and not url.startswith(("http://", "https://")):
                    return False, f"Service URL for {key} must start with http:// or https://"
        
        # Validate security_settings
        if "security_settings" in config:
            security = config["security_settings"]
            if "jwt_expiration_hours" in security:
                exp = security["jwt_expiration_hours"]
                if not isinstance(exp, int) or exp < 1 or exp > 8760:  # Max 1 year
                    return False, "JWT expiration must be between 1 and 8760 hours"
            if "max_requests_per_minute" in security:
                rate = security["max_requests_per_minute"]
                if not isinstance(rate, int) or rate < 1 or rate > 10000:
                    return False, "Max requests per minute must be between 1 and 10000"
        
        # Validate feature_flags are booleans
        if "feature_flags" in config:
            flags = config["feature_flags"]
            for key, value in flags.items():
                if not isinstance(value, bool):
                    return False, f"Feature flag {key} must be a boolean"
        
        return True, None
    except Exception as e:
        logger.error(f"Error validating config: {e}", exc_info=True)
        return False, f"Validation error: {str(e)}"


def update_system_config(
    config: Dict[str, Any],
    actor_user_id: str,
    category: Optional[str] = None
) -> bool:
    """
    Update system configuration.
    
    Args:
        config: Configuration dictionary (can be full config or category-specific)
        actor_user_id: Admin user ID performing the update
        category: Optional category name (if updating specific category)
        
    Returns:
        True if config was updated
    """
    try:
        # Validate configuration
        is_valid, error_msg = validate_config(config)
        if not is_valid:
            logger.error(f"Invalid configuration: {error_msg}")
            raise ValueError(error_msg)
        
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # If category is specified, merge with existing config
            if category:
                existing_config = get_system_config()
                if category not in existing_config:
                    existing_config[category] = {}
                existing_config[category].update(config.get(category, config))
                config = existing_config
            else:
                # Ensure all categories are present
                default_config = _get_default_config()
                for cat in default_config:
                    if cat not in config:
                        config[cat] = default_config[cat]
                    else:
                        # Merge with defaults
                        for key, value in default_config[cat].items():
                            if key not in config[cat]:
                                config[cat][key] = value
            
            # Store configuration
            cursor.execute("""
                INSERT INTO system_config (config_data, category, updated_by)
                VALUES (%s::jsonb, %s, %s)
            """, (json.dumps(config), category or 'all', str(actor_user_id)))
            
            conn.commit()
            
            # Log configuration change
            _log_config_change(actor_user_id, "update", config, category)
            
            return True
    except Exception as e:
        logger.error(f"Error updating system config: {e}", exc_info=True)
        raise


def get_config_history(
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get configuration history with pagination.
    
    Args:
        page: Page number (1-indexed)
        page_size: Number of records per page
        category: Optional category filter
        
    Returns:
        Dictionary with history list, total count, page, and page_size
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build WHERE clause
            where_clauses = []
            params = []
            
            if category:
                where_clauses.append("category = %s")
                params.append(category)
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*) as total
                FROM system_config
                WHERE {where_sql}
            """
            cursor.execute(count_query, params)
            total = cursor.fetchone()['total']
            
            # Get history with pagination
            offset = (page - 1) * page_size
            history_query = f"""
                SELECT 
                    id,
                    config_data,
                    category,
                    updated_by,
                    created_at,
                    updated_at
                FROM system_config
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])
            cursor.execute(history_query, params)
            history = [dict(row) for row in cursor.fetchall()]
            
            # Convert config_data to dict if it's a string
            for record in history:
                if isinstance(record.get('config_data'), str):
                    try:
                        record['config_data'] = json.loads(record['config_data'])
                    except json.JSONDecodeError:
                        pass
            
            return {
                "history": history,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
    except Exception as e:
        logger.error(f"Error getting config history: {e}", exc_info=True)
        raise


def _log_config_change(
    actor_user_id: str,
    action: str,
    config: Dict[str, Any],
    category: Optional[str] = None
):
    """Log configuration change to audit_logs."""
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs (action, actor_user_id, details)
                VALUES (%s, %s, %s::jsonb)
            """, (
                f"system_config_{action}",
                str(actor_user_id),
                json.dumps({
                    "category": category or "all",
                    "config_keys": list(config.keys()) if isinstance(config, dict) else []
                })
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"Error logging config change: {e}", exc_info=True)
        # Don't raise - audit logging failure shouldn't break config update
