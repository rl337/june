"""
Telegram Bot Service - Voice-to-Text-to-Voice integration.

Receives voice messages from Telegram users, transcribes them using STT,
processes through LLM, converts response to speech using TTS, and sends back.
"""
import asyncio
import logging
import os
import signal
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from prometheus_client import generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
import time

from inference_core import config, setup_logging

# Initialize tracing early
try:
    from essence.chat.utils.tracing import setup_tracing, get_tracer
    from opentelemetry import trace
    setup_tracing(service_name="june-telegram")
    tracer = get_tracer(__name__)
except ImportError:
    tracer = None
    trace = None

# Import shared metrics
from essence.services.shared_metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    GRPC_REQUESTS_TOTAL,
    GRPC_REQUEST_DURATION_SECONDS,
    VOICE_MESSAGES_PROCESSED_TOTAL,
    VOICE_PROCESSING_DURATION_SECONDS,
    STT_TRANSCRIPTION_DURATION_SECONDS,
    TTS_SYNTHESIS_DURATION_SECONDS,
    LLM_GENERATION_DURATION_SECONDS,
    ERRORS_TOTAL,
    SERVICE_HEALTH,
    REGISTRY
)
from essence.services.telegram.handlers import (
    start_command, help_command, status_command, language_command, handle_voice_message
)
from essence.services.telegram.handlers.text import handle_text_message
from essence.services.telegram.handlers.admin_commands import (
    block_command, unblock_command, list_blocked_command,
    clear_conversation_command, clear_user_conversations_command,
    system_status_command, admin_message_history_command, admin_help_command
)
from essence.services.telegram.dependencies.config import (
    get_service_config,
    get_stt_address,
    get_metrics_storage
)
from essence.services.telegram.dependencies.rate_limit import get_rate_limiter
from essence.services.telegram.dependencies.grpc_pool import shutdown_grpc_pool

# Import admin_db for blocked user check
# Disabled: No PostgreSQL service available
# try:
#     from admin_db import is_user_blocked
# except ImportError:
#     # Fallback if admin_db not available
#     def is_user_blocked(user_id: str) -> bool:
#         return False

# Import admin_db for blocked user check
try:
    from essence.services.telegram.admin_db import is_user_blocked
except ImportError:
    # Fallback if admin_db not available
    def is_user_blocked(user_id: str) -> bool:
        return False

# Setup logging
setup_logging(config.monitoring.log_level, "telegram")
logger = logging.getLogger(__name__)

# Service name for metrics
SERVICE_NAME = "telegram"
PLATFORM = "telegram"


class TelegramBotService:
    """Telegram bot service for voice-to-text-to-voice processing."""
    
    def __init__(self):
        """Initialize the Telegram bot service."""
        logger.info("Initializing Telegram bot service...")
        
        # Validate required environment variables
        required_env_vars = {
            "TELEGRAM_BOT_TOKEN": "Telegram bot token is required for bot operation"
        }
        missing_vars = []
        for var, description in required_env_vars.items():
            if not os.getenv(var):
                missing_vars.append(var)
                logger.error(f"Missing required environment variable: {var} - {description}")
        
        if missing_vars:
            error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("Required environment variables validated")
        
        # Get service configuration with error handling
        try:
            self.config = get_service_config()
            self.stt_address = get_stt_address()
            logger.info(f"Service configuration loaded. STT address: {self.stt_address}")
        except Exception as e:
            error_msg = f"Failed to load service configuration: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e
        
        # Validate bot token from config (should match env var, but double-check)
        if not self.config.bot_token:
            error_msg = "TELEGRAM_BOT_TOKEN is not configured in service config"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Initialize Telegram application with comprehensive error handling
        logger.info("Setting up Telegram Application builder...")
        try:
            # In python-telegram-bot v20+, timeout is configured via get_updates request
            # The Application builder doesn't accept timeout parameters directly
            # Timeouts are handled per-request or via polling configuration
            self.application = Application.builder().token(self.config.bot_token).build()
            logger.info("Telegram Application created successfully")
        except ValueError as e:
            # Invalid token format
            error_msg = f"Invalid Telegram bot token format: {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
        except Exception as e:
            # Other Telegram API errors
            error_msg = f"Failed to create Telegram Application: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(f"Telegram API initialization failed: {e}") from e
        
        # Initialize health check server
        logger.info("Setting up health check server...")
        self.health_app = FastAPI()
        self._setup_tracing_middleware()
        self._setup_health_endpoint()
        logger.info("Health check server configured")
        
        # Shutdown flag for graceful shutdown
        self._shutdown_event = asyncio.Event()
        self._shutdown_complete = False
        
        # Register handlers
        logger.info("Registering command and message handlers...")
        self._register_handlers()
        logger.info("Handlers registered successfully")
        
        # Setup signal handlers for graceful shutdown
        logger.info("Setting up signal handlers for graceful shutdown...")
        self._setup_signal_handlers()
        logger.info("Signal handlers configured")
        
        logger.info("Telegram bot service initialization complete")
    
    def _setup_tracing_middleware(self):
        """Setup tracing and metrics middleware for HTTP requests."""
        from essence.services.http_middleware import create_tracing_and_metrics_middleware
        
        middleware = create_tracing_and_metrics_middleware(tracer, trace)
        
        @self.health_app.middleware("http")
        async def tracing_and_metrics_middleware(request: Request, call_next):
            return await middleware(request, call_next)
    
    def _setup_health_endpoint(self):
        """Setup health check endpoint."""
        @self.health_app.get("/health")
        async def health_check():
            """Health check endpoint for Docker health checks.
            
            Checks:
            - Service is running
            - STT service connectivity
            - TTS service connectivity
            - LLM service connectivity
            - Required environment variables are set
            """
            health_status = {
                "status": "healthy",
                "service": "telegram-bot",
                "checks": {}
            }
            overall_healthy = True
            http_status = 200
            
            # Check required environment variables
            required_env_vars = ["TELEGRAM_BOT_TOKEN"]
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
                logger.warning(f"Health check: Missing environment variables: {missing_vars}")
            else:
                health_status["checks"]["environment"] = {"status": "healthy"}
            
            # Check service connectivity (STT, TTS, LLM)
            from dependencies.grpc_pool import get_grpc_pool
            from dependencies.config import get_stt_address, get_tts_address, get_llm_address
            import grpc
            
            services_to_check = {
                "stt": get_stt_address(),
                "tts": get_tts_address(),
                "llm": get_llm_address()
            }
            
            pool = get_grpc_pool()
            
            for service_name, address in services_to_check.items():
                # Try to get a channel with timeout (health checks should be fast)
                # If we can get a channel, the service is reachable
                # Use asyncio.wait_for for compatibility
                async def check_service(service_name, pool):
                    if service_name == "stt":
                        async with pool.get_stt_channel() as channel:
                            return channel.get_state()
                    elif service_name == "tts":
                        async with pool.get_tts_channel() as channel:
                            return channel.get_state()
                    elif service_name == "llm":
                        async with pool.get_llm_channel() as channel:
                            return channel.get_state()
                
                try:
                    state = await asyncio.wait_for(check_service(service_name, pool), timeout=3.0)
                    if state == grpc.ChannelConnectivity.READY:
                        health_status["checks"][service_name] = {
                            "status": "healthy",
                            "address": address
                        }
                    else:
                        # Channel exists but not ready - might be transient
                        health_status["checks"][service_name] = {
                            "status": "degraded",
                            "address": address,
                            "state": str(state)
                        }
                        # Don't mark as unhealthy for transient states
                except asyncio.TimeoutError:
                    health_status["checks"][service_name] = {
                        "status": "unhealthy",
                        "address": address,
                        "error": "Connection timeout"
                    }
                    overall_healthy = False
                    http_status = 503
                    logger.warning(f"Health check: {service_name} service connection timeout")
                except grpc.aio.AioRpcError as e:
                    health_status["checks"][service_name] = {
                        "status": "unhealthy",
                        "address": address,
                        "error": f"gRPC error: {e.code()}"
                    }
                    overall_healthy = False
                    http_status = 503
                    logger.error(f"Health check: {service_name} service gRPC error: {e.code()}", exc_info=True)
                except Exception as e:
                    health_status["checks"][service_name] = {
                        "status": "unhealthy",
                        "address": address,
                        "error": str(e)
                    }
                    overall_healthy = False
                    http_status = 503
                    logger.error(f"Health check: {service_name} service check failed: {e}", exc_info=True)
            
            # Update overall status
            if not overall_healthy:
                health_status["status"] = "unhealthy"
            
            # Update service health metric
            SERVICE_HEALTH.labels(service=SERVICE_NAME).set(1 if overall_healthy else 0)
            
            return JSONResponse(
                content=health_status,
                status_code=http_status
            )
        
        @self.health_app.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            return Response(
                content=generate_latest(REGISTRY),
                media_type=CONTENT_TYPE_LATEST
            )
        
        # Setup agent message test endpoint using shared base
        from essence.chat.interaction import setup_agent_message_endpoint
        from typing import Optional, Dict, Any
        
        # Import from essence.chat.agent.handler (chat-service-base is now in essence)
        from essence.chat.agent.handler import process_agent_message
        
        def process_message_wrapper(user_message: str, user_id: Optional[int] = None, 
                                     chat_id: Optional[int] = None, **kwargs) -> Dict[str, Any]:
            """Wrapper for process_agent_message to match expected signature."""
            return process_agent_message(
                user_message, 
                user_id=user_id, 
                chat_id=chat_id,
                platform="telegram",
                agent_script_name="telegram_response_agent.sh",
                agent_script_simple_name="telegram_response_agent_simple.sh",
                max_message_length=4096
            )
        
        setup_agent_message_endpoint(
            self.health_app,
            platform="telegram",
            process_agent_message_func=process_message_wrapper,
            agent_script_name="telegram_response_agent.sh",
            agent_script_simple_name="telegram_response_agent_simple.sh",
            max_message_length=4096  # Telegram message limit
        )
        
        @self.health_app.get("/queue/status")
        async def queue_status():
            """Get voice message queue status.
            
            Note: NATS queue is optional and not available for MVP.
            Returns error status if queue is not available.
            """
            try:
                from essence.services.telegram.voice_queue import VoiceMessageQueue
                queue = VoiceMessageQueue()
                await queue.connect()
                status = await queue.get_queue_status()
                await queue.disconnect()
                return JSONResponse(content=status, status_code=200)
            except RuntimeError as e:
                # NATS not available - return informative error
                logger.debug(f"Queue not available: {e}")
                return JSONResponse(
                    content={
                        "error": "Voice message queue is not available",
                        "message": str(e),
                        "note": "Set USE_VOICE_QUEUE=false to disable queue processing. Queue requires NATS which is not available for MVP."
                    },
                    status_code=503
                )
            except Exception as e:
                logger.error(f"Failed to get queue status: {e}", exc_info=True)
                return JSONResponse(
                    content={
                        "error": "Failed to get queue status",
                        "message": str(e)
                    },
                    status_code=500
                )
    
    def _register_handlers(self):
        """Register command and message handlers."""
        # Add blocked user check and rate limiting middleware
        async def check_blocked_and_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Check if user is blocked and rate limited before processing any update."""
            user_id = str(update.effective_user.id)
            
            # Check if user is blocked
            if is_user_blocked(user_id):
                # Allow admin commands even if user is blocked (for unblocking themselves)
                # But block all other interactions
                if update.message and update.message.text:
                    text = update.message.text.lower()
                    # Only allow admin_unblock command
                    if not text.startswith('/admin_unblock'):
                        await update.message.reply_text(
                            "🚫 **You are blocked from using this bot.**\n\n"
                            "If you believe this is an error, please contact an administrator."
                        )
                        return False  # Stop processing
            
            # Check rate limit (skip for admin commands)
            if update.message and update.message.text:
                text = update.message.text.lower()
                # Skip rate limiting for admin commands
                if not text.startswith('/admin_'):
                    rate_limiter = get_rate_limiter()
                    allowed, error_message = await rate_limiter.check_rate_limit(user_id)
                    if not allowed:
                        await update.message.reply_text(f"⏱️ {error_message}")
                        return False  # Stop processing
            
            return True
        
        # Command handlers - wrap to pass config
        async def start_wrapper(update, context):
            if not await check_blocked_and_rate_limit(update, context):
                return
            await start_command(update, context, self.config)
        
        async def help_wrapper(update, context):
            if not await check_blocked_and_rate_limit(update, context):
                return
            await help_command(update, context, self.config)
        
        async def status_wrapper(update, context):
            if not await check_blocked_and_rate_limit(update, context):
                return
            await status_command(update, context, self.config)
        
        async def language_wrapper(update, context):
            if not await check_blocked_and_rate_limit(update, context):
                return
            await language_command(update, context, self.config)
        
        async def voice_wrapper(update, context):
            if not await check_blocked_and_rate_limit(update, context):
                return
            await handle_voice_message(
                update,
                context,
                self.config,
                self.stt_address,
                get_metrics_storage
            )
        
        async def text_wrapper(update, context):
            if not await check_blocked_and_rate_limit(update, context):
                return
            await handle_text_message(update, context, self.config)
        
        # Admin command handlers (no blocked check - admins can always use admin commands)
        self.application.add_handler(CommandHandler("admin_block", block_command))
        self.application.add_handler(CommandHandler("admin_unblock", unblock_command))
        self.application.add_handler(CommandHandler("admin_list_blocked", list_blocked_command))
        self.application.add_handler(CommandHandler("admin_clear_conversation", clear_conversation_command))
        self.application.add_handler(CommandHandler("admin_clear_user", clear_user_conversations_command))
        self.application.add_handler(CommandHandler("admin_status", system_status_command))
        self.application.add_handler(CommandHandler("admin_message_history", admin_message_history_command))
        self.application.add_handler(CommandHandler("admin_help", admin_help_command))
        
        # Regular command handlers
        self.application.add_handler(CommandHandler("start", start_wrapper))
        self.application.add_handler(CommandHandler("help", help_wrapper))
        self.application.add_handler(CommandHandler("status", status_wrapper))
        self.application.add_handler(CommandHandler("language", language_wrapper))
        self.application.add_handler(MessageHandler(filters.VOICE, voice_wrapper))
        # Text message handler (must be last to catch non-command text)
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_wrapper))
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            # Set shutdown event to trigger graceful shutdown in async loop
            self._shutdown_event.set()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    async def _graceful_shutdown(self):
        """Perform graceful shutdown: stop accepting new requests, complete in-flight requests."""
        if self._shutdown_complete:
            return
        
        logger.info("Initiating graceful shutdown...")
        self._shutdown_event.set()
        
        # Stop the application (stops accepting new updates)
        if self.application.running:
            logger.info("Stopping Telegram application...")
            await self.application.stop()
            await self.application.shutdown()
        
        # Shutdown gRPC connection pool
        try:
            await shutdown_grpc_pool()
            logger.info("gRPC connection pool shut down")
        except Exception as e:
            logger.error(f"Error shutting down gRPC pool: {e}", exc_info=True)
        
        # Wait a bit for in-flight requests to complete
        # In a production system, you might want to track active requests
        logger.info("Waiting for in-flight requests to complete...")
        await asyncio.sleep(2)
        
        self._shutdown_complete = True
        logger.info("Graceful shutdown complete")
    
    def _run_health_server(self):
        """Run health check HTTP server in a separate thread."""
        port = int(os.getenv("TELEGRAM_SERVICE_PORT", "8080"))
        logger.info(f"Starting health check server on port {port}")
        uvicorn.run(self.health_app, host="0.0.0.0", port=port, log_level="error")
    
    async def _run_async(self, use_webhook: bool = False, webhook_url: Optional[str] = None):
        """Run the Telegram bot asynchronously (polling or webhook)."""
        if use_webhook and webhook_url:
            logger.info(f"Starting bot in webhook mode: {webhook_url}")
            webhook_port = int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8443"))
            webhook_path = os.getenv("TELEGRAM_WEBHOOK_PATH", "/webhook")
            
            # Set webhook with error handling
            try:
                await self.application.bot.set_webhook(
                    url=f"{webhook_url}{webhook_path}",
                    allowed_updates=Update.ALL_TYPES
                )
                logger.info(f"Webhook set to {webhook_url}{webhook_path}")
            except Exception as e:
                error_msg = f"Failed to set Telegram webhook: {e}"
                logger.error(error_msg, exc_info=True)
                raise RuntimeError(error_msg) from e
            
            # Start webhook server
            await self.application.start()
            await self.application.updater.start_webhook(
                listen="0.0.0.0",
                port=webhook_port,
                url_path=webhook_path,
                webhook_url=webhook_url
            )
            logger.info(f"Webhook server started on port {webhook_port}")
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
            # Stop webhook
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        else:
            logger.info("Starting bot in polling mode")
            try:
                await self.application.initialize()
                await self.application.start()
                await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
                logger.info("Polling started")
            except Exception as e:
                error_msg = f"Failed to start Telegram polling: {e}"
                logger.error(error_msg, exc_info=True)
                raise RuntimeError(error_msg) from e
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
            # Stop polling
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
    
    def run(self, use_webhook: bool = False, webhook_url: Optional[str] = None):
        """Run the Telegram bot (polling or webhook) and health check server."""
        # Start health check server in a separate thread
        health_thread = threading.Thread(target=self._run_health_server, daemon=True)
        health_thread.start()
        logger.info("Health check server started")
        
        # Run Telegram bot in async event loop
        try:
            asyncio.run(self._run_async(use_webhook=use_webhook, webhook_url=webhook_url))
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            asyncio.run(self._graceful_shutdown())
        except Exception as e:
            logger.error(f"Error running bot: {e}", exc_info=True)
            # Attempt graceful shutdown even on error
            try:
                asyncio.run(self._graceful_shutdown())
            except Exception as shutdown_error:
                logger.error(f"Error during graceful shutdown: {shutdown_error}", exc_info=True)
            raise


def main():
    """Main entry point."""
    try:
        service = TelegramBotService()
        use_webhook = os.getenv("TELEGRAM_USE_WEBHOOK", "false").lower() == "true"
        webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
        service.run(use_webhook=use_webhook, webhook_url=webhook_url)
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
