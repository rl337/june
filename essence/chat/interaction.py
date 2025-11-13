"""
Shared base for human interaction services (Telegram, Discord, etc.).

Provides common endpoints and utilities for testing and health checks.
"""
import json
import logging
from typing import Optional, Callable, Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def setup_agent_message_endpoint(
    app: FastAPI,
    platform: str,
    process_agent_message_func: Callable,
    default_user_id: int = 999999,
    default_chat_id: int = 888888,
    agent_script_name: str = "telegram_response_agent.sh",
    agent_script_simple_name: str = "telegram_response_agent_simple.sh",
    max_message_length: int = 4096
) -> None:
    """
    Setup the /api/agent/message test endpoint for a human interaction service.
    
    This endpoint allows testing agent message processing without going through
    the actual chat platform (Telegram, Discord, etc.).
    
    Args:
        app: FastAPI application instance
        platform: Platform name (e.g., "telegram", "discord")
        process_agent_message_func: Function to process agent messages
            Signature: (message: str, user_id: Optional[int], chat_id: Optional[int], ...) -> Dict[str, Any]
        default_user_id: Default user ID for HTTP testing (default: 999999)
        default_chat_id: Default chat ID for HTTP testing (default: 888888)
        agent_script_name: Name of the session-aware agent script
        agent_script_simple_name: Name of the simple agent script (no session)
        max_message_length: Maximum message length for the platform
    """
    @app.post("/api/agent/message")
    async def agent_message_endpoint(request: Request):
        """HTTP endpoint to test agent responses without the chat platform.
        
        Request body:
            {
                "message": "Your message here",
                "user_id": 12345,  # Optional: for session support
                "chat_id": 67890   # Optional: for session support
            }
        
        Response:
            {
                "success": true/false,
                "message": "Agent response text",
                "error": "Error message if success is false"
            }
        """
        try:
            # Parse request body
            body = await request.json()
            user_message = body.get("message", "")
            user_id = body.get("user_id")  # Optional: for session support
            chat_id = body.get("chat_id")  # Optional: for session support
            
            if not user_message:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Missing 'message' field in request body"}
                )
            
            # Use default test values if not provided
            if user_id is None:
                user_id = default_user_id
            if chat_id is None:
                chat_id = default_chat_id
            
            # Process through agent
            # Check if process_agent_message_func accepts platform parameter
            import inspect
            sig = inspect.signature(process_agent_message_func)
            params = list(sig.parameters.keys())
            
            # Build kwargs based on function signature
            kwargs = {
                "user_message": user_message,
                "user_id": user_id,
                "chat_id": chat_id,
            }
            
            # Add platform-specific parameters if the function accepts them
            if "platform" in params:
                kwargs["platform"] = platform
            if "agent_script_name" in params:
                kwargs["agent_script_name"] = agent_script_name
            if "agent_script_simple_name" in params:
                kwargs["agent_script_simple_name"] = agent_script_simple_name
            if "max_message_length" in params:
                kwargs["max_message_length"] = max_message_length
            
            result = process_agent_message_func(**kwargs)
            
            if result.get("success"):
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message": result.get("message", "")
                    }
                )
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                        "message": result.get("message", "Error processing message")
                    }
                )
                
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Invalid JSON in request body"}
            )
        except Exception as e:
            logger.error(f"Error in agent message endpoint: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )


def setup_health_endpoint(
    app: FastAPI,
    service_name: str,
    required_env_vars: list[str],
    additional_checks: Optional[Callable[[], Dict[str, Any]]] = None
) -> None:
    """
    Setup a standard health check endpoint for a human interaction service.
    
    Args:
        app: FastAPI application instance
        service_name: Name of the service (e.g., "telegram-bot", "discord-bot")
        required_env_vars: List of required environment variable names
        additional_checks: Optional function to perform additional health checks
            Should return a dict with check results
    """
    @app.get("/health")
    async def health_check():
        """Health check endpoint for service monitoring.
        
        Returns:
            JSON response with service status and health check results
        """
        import os
        
        health_status = {
            "status": "healthy",
            "service": service_name,
            "checks": {}
        }
        overall_healthy = True
        http_status = 200
        
        # Check required environment variables
        missing_vars = []
        for var in required_env_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            health_status["checks"]["environment"] = {
                "status": "unhealthy",
                "missing_variables": missing_vars
            }
            overall_healthy = False
            http_status = 503
        else:
            health_status["checks"]["environment"] = {"status": "healthy"}
        
        # Run additional checks if provided
        if additional_checks:
            try:
                additional_results = additional_checks()
                health_status["checks"].update(additional_results)
                
                # Check if any additional check is unhealthy
                for check_name, check_result in additional_results.items():
                    if isinstance(check_result, dict) and check_result.get("status") == "unhealthy":
                        overall_healthy = False
                        http_status = 503
            except Exception as e:
                logger.error(f"Error in additional health checks: {e}", exc_info=True)
                health_status["checks"]["additional"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                overall_healthy = False
                http_status = 503
        
        if not overall_healthy:
            health_status["status"] = "unhealthy"
        
        return JSONResponse(content=health_status, status_code=http_status)

