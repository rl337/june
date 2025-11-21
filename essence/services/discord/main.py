"""
Discord Bot Service - Chat integration using shared base.

Receives messages from Discord users and processes them through the agent system.
"""
import asyncio
import logging
import os
import signal
import sys
import time
from typing import Any, Dict, Optional

import discord
import uvicorn
from discord.ext import commands
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from inference_core import config, setup_logging
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

# Removed unused imports after radical refactor:
# - process_agent_message, stream_agent_message (old agentic flow)
# - MessageBuilder (old agentic flow)
# - edit_with_history, send_with_history (old agentic flow)

# Initialize tracing early
try:
    from opentelemetry import trace

    from essence.chat.utils.tracing import get_tracer, setup_tracing

    setup_tracing(service_name="june-discord")
    tracer = get_tracer(__name__)
except ImportError:
    tracer = None
    trace = None

# Import shared metrics
from essence.services.shared_metrics import (
    ERRORS_TOTAL,
    GRPC_REQUEST_DURATION_SECONDS,
    GRPC_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    REGISTRY,
    SERVICE_HEALTH,
)

# Setup logging early
setup_logging(config.monitoring.log_level, "discord")
logger = logging.getLogger(__name__)

# Service name for metrics
SERVICE_NAME = "discord"
PLATFORM = "discord"


class DiscordBotService:
    """Discord bot service for chat processing."""

    def __init__(self):
        """Initialize the Discord bot service."""
        logger.info("Initializing Discord bot service...")

        # Validate required environment variables
        required_env_vars = {
            "DISCORD_BOT_TOKEN": "Discord bot token is required for bot operation"
        }
        missing_vars = []
        for var, description in required_env_vars.items():
            if not os.getenv(var):
                missing_vars.append(var)
                logger.error(
                    f"Missing required environment variable: {var} - {description}"
                )

        if missing_vars:
            error_msg = (
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("Required environment variables validated")

        # Get bot token
        self.bot_token = os.getenv("DISCORD_BOT_TOKEN")

        # Initialize Discord bot with intents
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.members = True  # Required for user information

        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self._register_handlers()

        # Initialize health check server
        logger.info("Setting up health check server...")
        self.health_app = FastAPI()
        self._setup_tracing_middleware()
        self._setup_health_endpoint()
        logger.info("Health check server configured")

        # Shutdown flag for graceful shutdown
        self._shutdown_event = asyncio.Event()
        self._shutdown_complete = False

        # Setup signal handlers for graceful shutdown
        logger.info("Setting up signal handlers for graceful shutdown...")
        self._setup_signal_handlers()
        logger.info("Signal handlers configured")

        logger.info("Discord bot service initialization complete")

    def _setup_tracing_middleware(self):
        """Setup tracing and metrics middleware for HTTP requests."""
        from essence.services.http_middleware import (
            create_tracing_and_metrics_middleware,
        )

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
            - Required environment variables are set
            """
            health_status = {
                "status": "healthy",
                "service": "discord-bot",
                "checks": {},
            }
            overall_healthy = True
            http_status = 200

            # Check required environment variables
            required_env_vars = ["DISCORD_BOT_TOKEN"]
            missing_vars = []
            for var in required_env_vars:
                if not os.getenv(var):
                    missing_vars.append(var)

            if missing_vars:
                health_status["checks"]["environment"] = {
                    "status": "unhealthy",
                    "missing_variables": missing_vars,
                }
                overall_healthy = False
                http_status = 503
                logger.warning(
                    f"Health check: Missing environment variables: {missing_vars}"
                )
            else:
                health_status["checks"]["environment"] = {"status": "healthy"}

            # Update overall status
            if not overall_healthy:
                health_status["status"] = "unhealthy"

            # Update service health metric
            SERVICE_HEALTH.labels(service=SERVICE_NAME).set(1 if overall_healthy else 0)

            return JSONResponse(content=health_status, status_code=http_status)

        @self.health_app.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            return Response(
                content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST
            )

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            # Set shutdown event to trigger graceful shutdown in async loop
            self._shutdown_event.set()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def _register_handlers(self):
        """Register Discord event handlers."""

        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot logged in as {self.bot.user}")

        @self.bot.event
        async def on_message(message: discord.Message):
            # Ignore messages from bots
            if message.author.bot:
                return

            # Ignore messages that are commands
            if message.content.startswith("!"):
                await self.bot.process_commands(message)
                return

            # Process regular messages
            await self._handle_message(message)

        @self.bot.command(name="ping")
        async def ping_command(ctx):
            """Respond to ping command."""
            await ctx.send("Pong!")

        # Note: 'help' is a built-in command in discord.py, so we don't override it
        # Users can use !help to see all commands including !ping

    async def _handle_message(self, message: discord.Message):
        """
        Handle incoming Discord messages.

        Flow:
        - Non-whitelisted users: Ignore completely (no response)
        - Owner users: Create todorama task for looping agent to process
        - Whitelisted (non-owner) users: Forward message to owner (create todorama task)

        Args:
            message: Discord message object
        """
        if tracer:
            with tracer.start_as_current_span("discord.message.handle") as span:
                try:
                    self._handle_message_impl(message, span)
                except Exception as e:
                    logger.error(f"Error handling Discord message: {e}", exc_info=True)
                    if span:
                        span.record_exception(e)
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        else:
            try:
                self._handle_message_impl(message, None)
            except Exception as e:
                logger.error(f"Error handling Discord message: {e}", exc_info=True)

    def _handle_message_impl(self, message: discord.Message, span):
        """Implementation of message handling (separated for tracing)."""
        user_id = str(message.author.id)
        channel_id = str(message.channel.id)
        user_message = message.content

        # Set span attributes if tracing is available
        if span:
            span.set_attribute("user_id", user_id)
            span.set_attribute("chat_id", channel_id)
            span.set_attribute("message_length", len(user_message) if user_message else 0)
            span.set_attribute("platform", "discord")

        # Check if user is whitelisted
        from essence.chat.user_messages_sync import (
            is_user_whitelisted,
            is_user_owner,
            get_owner_users,
        )

        is_whitelisted = is_user_whitelisted(user_id, "discord")
        if span:
            span.set_attribute("whitelisted", is_whitelisted)

        # Non-whitelisted users: Ignore completely (no response)
        if not is_whitelisted:
            logger.info(f"Ignoring message from non-whitelisted user {user_id}")
            if span:
                span.set_attribute("action", "ignored")
                span.set_status(trace.Status(trace.StatusCode.OK))
            return  # Silently ignore - don't send any response

        # Get username if available
        username = None
        try:
            if message.author.name:
                username = message.author.name
        except Exception:
            pass

        # Check if user is owner
        is_owner = is_user_owner(user_id, "discord")
        if span:
            span.set_attribute("is_owner", is_owner)

        if is_owner:
            # Owner: Create todorama task instead of appending to USER_MESSAGES.md
            logger.info(
                f"Owner user {user_id} - creating todorama task for user interaction"
            )

            # Call command to create todorama task
            import subprocess
            import sys
            
            try:
                # Build command to create user interaction task
                cmd = [
                    sys.executable,
                    "-m",
                    "essence",
                    "create-user-interaction-task",
                    "--user-id", user_id,
                    "--chat-id", channel_id,
                    "--platform", "discord",
                    "--content", user_message,
                    "--message-id", str(message.id),
                ]
                
                if username:
                    cmd.extend(["--username", username])
                
                # Run command (non-blocking, fire-and-forget)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                
                if result.returncode == 0:
                    if span:
                        span.set_attribute("action", "created_todorama_task")
                    logger.info(f"Successfully created todorama task for owner message")
                else:
                    if span:
                        span.set_attribute("action", "task_creation_failed")
                    logger.error(
                        f"Failed to create todorama task: {result.stderr}"
                    )
            except Exception as e:
                if span:
                    span.set_attribute("action", "task_creation_error")
                logger.error(
                    f"Error creating todorama task: {e}", exc_info=True
                )

            if span:
                span.set_status(trace.Status(trace.StatusCode.OK))
            return

        else:
            # Whitelisted (non-owner): Forward to owner
            logger.info(
                f"Whitelisted (non-owner) user {user_id} - forwarding message to owner"
            )

            # Get owner user IDs for forwarding
            owner_users = get_owner_users("discord")
            if not owner_users:
                logger.warning(
                    "No owner users configured, cannot forward whitelisted user message"
                )
                if span:
                    span.set_attribute("action", "forward_failed_no_owner")
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                return

            # Forward to first owner (for now - could be enhanced to forward to all)
            owner_user_id = owner_users[0]

            # Create todorama task for forwarded message
            forward_content = f"[Forwarded from whitelisted user {user_id} ({username or 'unknown'})] {user_message}"

            import subprocess
            import sys
            
            try:
                # Build command to create user interaction task
                cmd = [
                    sys.executable,
                    "-m",
                    "essence",
                    "create-user-interaction-task",
                    "--user-id", owner_user_id,
                    "--chat-id", channel_id,
                    "--platform", "discord",
                    "--content", forward_content,
                    "--message-id", str(message.id),
                    "--username", f"forwarded_from_{user_id}",
                ]
                
                # Run command (non-blocking, fire-and-forget)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                
                if result.returncode == 0:
                    if span:
                        span.set_attribute("action", "forwarded_to_owner")
                    logger.info(
                        f"Successfully forwarded whitelisted user message to owner {owner_user_id}"
                    )
                else:
                    if span:
                        span.set_attribute("action", "forward_failed")
                    logger.error(
                        f"Failed to forward whitelisted user message: {result.stderr}"
                    )
            except Exception as e:
                if span:
                    span.set_attribute("action", "forward_error")
                logger.error(
                    f"Error forwarding whitelisted user message: {e}", exc_info=True
                )

            if span:
                span.set_status(trace.Status(trace.StatusCode.OK))
            return

    def _run_health_server(self):
        """Run health check HTTP server in a separate thread."""
        port = int(os.getenv("DISCORD_SERVICE_PORT", "8081"))
        logger.info(f"Starting health check server on port {port}")
        uvicorn.run(self.health_app, host="0.0.0.0", port=port, log_level="error")

    async def _run_async(self):
        """Run the Discord bot asynchronously."""
        logger.info("Starting Discord bot...")
        try:
            await self.bot.start(self.bot_token)
        except Exception as e:
            logger.error(f"Error starting Discord bot: {e}", exc_info=True)
            raise
        finally:
            logger.info("Discord bot stopped")

    def run(self):
        """Run the Discord bot and health check server."""
        # Start health check server in a separate thread
        import threading
        health_thread = threading.Thread(target=self._run_health_server, daemon=True)
        health_thread.start()
        logger.info("Health check server started")

        # Run Discord bot in async event loop
        try:
            asyncio.run(self._run_async())
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            asyncio.run(self._graceful_shutdown())
        except Exception as e:
            logger.error(f"Error running bot: {e}", exc_info=True)
            # Attempt graceful shutdown even on error
            try:
                asyncio.run(self._graceful_shutdown())
            except Exception as shutdown_error:
                logger.error(
                    f"Error during graceful shutdown: {shutdown_error}", exc_info=True
                )
            raise

    async def _graceful_shutdown(self):
        """Perform graceful shutdown: stop accepting new requests, complete in-flight requests."""
        if self._shutdown_complete:
            return

        logger.info("Initiating graceful shutdown...")
        self._shutdown_event.set()

        # Stop the bot
        if self.bot and not self.bot.is_closed():
            logger.info("Closing Discord bot connection...")
            await self.bot.close()
            logger.info("Discord bot connection closed")

        self._shutdown_complete = True
        logger.info("Graceful shutdown complete")
