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



        except Exception as e:
            logger.error(f"Error handling Discord message: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error handling Discord message: {e}", exc_info=True)
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
