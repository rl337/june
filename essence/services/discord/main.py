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
        - Owner users: Append to USER_MESSAGES.md with status "NEW" for looping agent to process
        - Whitelisted (non-owner) users: Forward message to owner

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
            append_message_to_user_messages,
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
            # Owner: Append to USER_MESSAGES.md with status "NEW"
            logger.info(
                f"Owner user {user_id} - appending to USER_MESSAGES.md with status NEW"
            )

            success = append_message_to_user_messages(
                user_id=user_id,
                chat_id=channel_id,
                platform="discord",
                message_type="Request",
                content=user_message,
                message_id=str(message.id),
                status="NEW",
                username=username,
            )

            if success:
                if span:
                    span.set_attribute("action", "appended_to_user_messages")
                logger.info(f"Successfully appended owner message to USER_MESSAGES.md")
            else:
                if span:
                    span.set_attribute("action", "append_failed")
                logger.error(f"Failed to append owner message to USER_MESSAGES.md")

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

            # Append forwarded message to USER_MESSAGES.md
            forward_content = f"[Forwarded from whitelisted user {user_id} ({username or 'unknown'})] {user_message}"

            success = append_message_to_user_messages(
                user_id=owner_user_id,
                chat_id=channel_id,  # Use original chat_id
                platform="discord",
                message_type="Request",
                content=forward_content,
                message_id=str(message.id),
                status="NEW",
                username=f"forwarded_from_{user_id}",
            )

            if success:
                if span:
                    span.set_attribute("action", "forwarded_to_owner")
                logger.info(
                    f"Successfully forwarded whitelisted user message to owner {owner_user_id}"
                )
            else:
                if span:
                    span.set_attribute("action", "forward_failed")
                logger.error(
                    f"Failed to forward whitelisted user message to owner {owner_user_id}"
                )

            if span:
                span.set_status(trace.Status(trace.StatusCode.OK))
            return
