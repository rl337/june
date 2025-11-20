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

from essence.chat.agent.handler import process_agent_message, stream_agent_message
from essence.chat.message_builder import MessageBuilder
from essence.services.discord.message_history_helpers import (
    edit_with_history,
    send_with_history,
)

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
        """Handle incoming Discord message."""
        try:
            user_id = message.author.id
            channel_id = message.channel.id

            # Check if user is whitelisted for direct agent communication
            from essence.chat.user_requests_sync import is_user_whitelisted, sync_message_to_user_requests

            is_whitelisted = is_user_whitelisted(str(user_id), "discord")

            if is_whitelisted:
                # Whitelisted user: Sync to USER_REQUESTS.md and skip agentic flow
                # The looping agent will read from USER_REQUESTS.md and process the request
                logger.info(
                    f"Whitelisted user {user_id} - syncing to USER_REQUESTS.md and skipping agentic flow"
                )

                # Get username if available
                username = None
                try:
                    if message.author.name:
                        username = message.author.name
                except Exception:
                    pass

                # Sync user request to USER_REQUESTS.md
                sync_message_to_user_requests(
                    user_id=str(user_id),
                    chat_id=str(channel_id),
                    platform="discord",
                    message_type="Request",
                    content=message.content,
                    message_id=str(message.id),
                    status="Pending",
                    username=username,
                )

                # Send acknowledgment to user
                try:
                    await send_with_history(
                        message.channel,
                        "✅ Request received and queued for processing by the looping agent. "
                        "You will receive a response when the agent processes your request.",
                        user_id=str(user_id),
                        message_type="status",
                    )
                except Exception as e:
                    logger.warning(f"Failed to send acknowledgment to whitelisted user: {e}")

                return  # Skip agentic flow for whitelisted users

            logger.info(
                f"Received message from user {user_id} in channel {channel_id}: {message.content[:100]}"
            )

            # Simple status-based approach (same as Telegram):
            # 1. Send "received request" immediately
            # 2. Send "processing" when making agentic call
            # 3. Send "generating" with dots for each chunk
            # 4. Replace with final result when done

            status_message = None
            chunk_count = 0
            raw_llm_response = ""

            # Step 1: Send "received request" immediately
            try:
                status_message = await send_with_history(
                    message.channel,
                    "✅ Received request",
                    user_id=str(user_id),
                    message_type="status",
                )
                logger.info(f"Sent 'received request' to user {user_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to send 'received request': {e}, continuing anyway"
                )
                # Continue processing even if initial status fails

            # Step 2: Update to "processing" when making agentic call
            if status_message:
                try:
                    await edit_with_history(
                        status_message,
                        "🔄 Processing...",
                        user_id=str(user_id),
                        message_type="status",
                    )
                    logger.info(f"Updated to 'processing' for user {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to update to 'processing': {e}")

            # Initialize message builder for final result (using markdown format for Discord)
            message_builder = MessageBuilder(
                service_name="discord",
                user_id=str(user_id),
                chat_id=str(channel_id),
                format="markdown",  # Discord supports markdown natively
            )

            try:
                # Stream responses from the agent
                for message_text, is_final, message_type in stream_agent_message(
                    message.content,
                    user_id=user_id,
                    chat_id=channel_id,
                    platform="discord",
                    agent_script_name="telegram_response_agent.sh",  # Use same script for now
                    agent_script_simple_name="telegram_response_agent_simple.sh",
                    max_message_length=2000,  # Discord message limit
                ):
                    # Skip empty final signal - we'll handle final result separately
                    if not message_text and is_final:
                        break

                    if not message_text:
                        continue

                    # Track the raw LLM response - use result type as authoritative, otherwise keep longest
                    if message_type == "result":
                        raw_llm_response = message_text
                        logger.info(
                            f"Received authoritative result message: {len(raw_llm_response)} chars"
                        )
                    elif len(message_text) > len(raw_llm_response):
                        raw_llm_response = message_text
                        logger.debug(
                            f"Extended raw_llm_response: {len(raw_llm_response)} chars"
                        )

                    # Step 3: Update status to "generating" with dots for each chunk
                    chunk_count += 1
                    if status_message:
                        dots = "." * min(chunk_count, 5)  # Max 5 dots
                        try:
                            await edit_with_history(
                                status_message,
                                f"⚙️ Generating{dots}",
                                user_id=str(user_id),
                                message_type="status",
                            )
                        except Exception as e:
                            logger.debug(f"Failed to update generating status: {e}")

                # Step 4: Replace with final result when done
                if raw_llm_response:
                    try:
                        # Build full turn and render
                        turn = message_builder.build_turn(
                            message.content, raw_llm_response
                        )
                        rendered_parts = message_builder.split_message_if_needed(2000)

                        logger.info(
                            f"Final message split into {len(rendered_parts)} parts"
                        )

                        if rendered_parts:
                            # Replace status message with first part (or send as new if no status message)
                            if status_message:
                                try:
                                    await edit_with_history(
                                        status_message,
                                        rendered_parts[0],
                                        user_id=str(user_id),
                                        message_type="text",
                                        rendering_metadata={
                                            "part": 1,
                                            "total_parts": len(rendered_parts),
                                        },
                                        raw_text=raw_llm_response
                                        if raw_llm_response
                                        else None,
                                    )
                                    logger.info(
                                        f"Replaced status with final message (first part: {len(rendered_parts[0])} chars)"
                                    )
                                except Exception as edit_err:
                                    # If edit fails, send as new message
                                    error_msg = str(edit_err)
                                    if "message is not modified" in error_msg.lower():
                                        logger.debug(
                                            f"Final message unchanged, skipping edit"
                                        )
                                    else:
                                        logger.warning(
                                            f"Failed to edit status message, sending as new: {edit_err}"
                                        )
                                        await send_with_history(
                                            message.channel,
                                            rendered_parts[0],
                                            user_id=str(user_id),
                                            message_type="text",
                                            rendering_metadata={
                                                "part": 1,
                                                "total_parts": len(rendered_parts),
                                                "fallback": True,
                                            },
                                            raw_text=raw_llm_response
                                            if raw_llm_response
                                            else None,
                                        )
                            else:
                                # No status message, send as new
                                await send_with_history(
                                    message.channel,
                                    rendered_parts[0],
                                    user_id=str(user_id),
                                    message_type="text",
                                    rendering_metadata={
                                        "part": 1,
                                        "total_parts": len(rendered_parts),
                                    },
                                    raw_text=raw_llm_response
                                    if raw_llm_response
                                    else None,
                                )
                                logger.info(
                                    f"Sent final message (first part: {len(rendered_parts[0])} chars)"
                                )

                            # Send additional parts as new messages
                            for i, part in enumerate(rendered_parts[1:], 1):
                                logger.info(
                                    f"Sending additional part {i+1}/{len(rendered_parts)} (length: {len(part)})"
                                )
                                await send_with_history(
                                    message.channel,
                                    part,
                                    user_id=str(user_id),
                                    message_type="text",
                                    rendering_metadata={
                                        "part": i + 1,
                                        "total_parts": len(rendered_parts),
                                    },
                                    raw_text=raw_llm_response
                                    if raw_llm_response and i == 0
                                    else None,
                                )

                        # Log the turn for debugging
                        try:
                            turn.log_to_file()
                        except Exception as log_error:
                            logger.warning(f"Failed to log turn to file: {log_error}")
                    except Exception as final_error:
                        logger.error(
                            f"Failed to render final message: {final_error}",
                            exc_info=True,
                        )
                        from essence.chat.error_handler import render_error_for_platform

                        error_text = render_error_for_platform(
                            final_error,
                            "discord",
                            "❌ I encountered an error finalizing my response.",
                        )
                        try:
                            if status_message:
                                await status_message.edit(content=error_text)
                            else:
                                await message.channel.send(error_text)
                        except:
                            pass
                else:
                    # No response received
                    if status_message:
                        try:
                            await status_message.edit(
                                content="⚠️ No response generated"
                            )
                        except:
                            pass
                    else:
                        try:
                            await message.channel.send("⚠️ No response generated")
                        except:
                            pass

            except Exception as stream_error:
                logger.error(
                    f"Error streaming agent response: {stream_error}", exc_info=True
                )
                # Update status message with error
                try:
                    from essence.chat.error_handler import render_error_for_platform

                    error_text = render_error_for_platform(
                        stream_error,
                        "discord",
                        "❌ I encountered an error processing your message. Please try again.",
                    )
                    if status_message:
                        await status_message.edit(content=error_text)
                    else:
                        await message.channel.send(error_text)
                except Exception as send_error:
                    logger.error(
                        f"Failed to send error message: {send_error}", exc_info=True
                    )

        except Exception as e:
            logger.error(f"Error handling Discord message: {e}", exc_info=True)
            error_type = type(e).__name__
            ERRORS_TOTAL.labels(service=SERVICE_NAME, error_type=error_type).inc()
            try:
                from essence.chat.error_handler import render_error_for_platform

                error_text = render_error_for_platform(
                    e,
                    "discord",
                    "❌ I encountered an error processing your message. Please try again.",
                )
                await message.channel.send(error_text)
            except:
                pass

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
            """Health check endpoint."""
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
            else:
                health_status["checks"]["environment"] = {"status": "healthy"}

            # Check bot status
            if self.bot.is_ready():
                health_status["checks"]["bot"] = {
                    "status": "healthy",
                    "user": str(self.bot.user) if self.bot.user else None,
                }
            else:
                health_status["checks"]["bot"] = {
                    "status": "degraded",
                    "message": "Bot not ready yet",
                }

            if not overall_healthy:
                health_status["status"] = "unhealthy"

            # Update service health metric
            SERVICE_HEALTH.labels(service=SERVICE_NAME).set(1 if overall_healthy else 0)

            return JSONResponse(content=health_status, status_code=http_status)

        @self.health_app.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

        # Setup agent message test endpoint using shared base
        from essence.chat.interaction import setup_agent_message_endpoint

        def process_message_wrapper(
            user_message: str,
            user_id: Optional[int] = None,
            chat_id: Optional[int] = None,
            **kwargs,
        ) -> Dict[str, Any]:
            """Wrapper for process_agent_message to match expected signature."""
            return process_agent_message(
                user_message,
                user_id=user_id,
                chat_id=chat_id,
                platform="discord",
                agent_script_name="telegram_response_agent.sh",
                agent_script_simple_name="telegram_response_agent_simple.sh",
                max_message_length=2000,
            )

        try:
            setup_agent_message_endpoint(
                self.health_app,
                platform="discord",
                process_agent_message_func=process_message_wrapper,
                agent_script_name="telegram_response_agent.sh",
                agent_script_simple_name="telegram_response_agent_simple.sh",
                max_message_length=2000,
            )
            logger.info("Agent message endpoint configured successfully")
        except Exception as e:
            logger.error(f"Failed to setup agent message endpoint: {e}", exc_info=True)
            raise

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self._shutdown_event.set()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    async def run(self):
        """Run the Discord bot service."""
        logger.info("Starting Discord bot service...")

        # Verify routes before starting server
        route_paths = [route.path for route in self.health_app.routes]
        logger.info(f"Health app routes before server start: {route_paths}")

        # Start health check server in background
        health_server = uvicorn.Server(
            uvicorn.Config(
                self.health_app,
                host="0.0.0.0",
                port=int(os.getenv("DISCORD_SERVICE_PORT", "8081")),
                log_level="info",
            )
        )
        health_task = asyncio.create_task(health_server.serve())

        # Give server a moment to start, then verify routes again
        await asyncio.sleep(0.5)
        route_paths_after = [route.path for route in self.health_app.routes]
        logger.info(f"Health app routes after server start: {route_paths_after}")

        try:
            # Start bot
            bot_task = asyncio.create_task(self.bot.start(self.bot_token))

            # Wait for shutdown signal
            await self._shutdown_event.wait()

            logger.info("Shutting down Discord bot...")

            # Close bot
            await self.bot.close()
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                pass

            # Stop health server
            health_server.should_exit = True
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass

            self._shutdown_complete = True
            logger.info("Discord bot service shutdown complete")

        except Exception as e:
            logger.error(f"Error running Discord bot service: {e}", exc_info=True)
            raise


def main():
    """Main entry point."""
    try:
        service = DiscordBotService()
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error in Discord bot service: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
