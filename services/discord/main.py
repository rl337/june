"""
Discord Bot Service - Chat integration using shared base.

Receives messages from Discord users and processes them through the agent system.
"""
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import uvicorn
import discord
from discord.ext import commands
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST

# Add shared base to path
chat_base_path = Path(__file__).parent.parent / "chat-service-base"
sys.path.insert(0, str(chat_base_path))

# Add essence module to path
essence_path = Path(__file__).parent.parent.parent / "essence"
sys.path.insert(0, str(essence_path))

from inference_core import config, setup_logging
from agent.handler import process_agent_message, stream_agent_message
from typing import Optional, Dict, Any

# Setup logging
setup_logging(config.monitoring.log_level, "discord")
logger = logging.getLogger(__name__)

# Prometheus metrics
REGISTRY = CollectorRegistry()
DISCORD_MESSAGES_TOTAL = Counter('discord_messages_total', 'Total Discord messages processed', ['type'], registry=REGISTRY)
DISCORD_COMMANDS_TOTAL = Counter('discord_commands_total', 'Total Discord commands processed', ['command'], registry=REGISTRY)
DISCORD_ERRORS_TOTAL = Counter('discord_errors_total', 'Total errors', ['error_type'], registry=REGISTRY)
DISCORD_ACTIVE_USERS = Gauge('discord_active_users', 'Number of active users', registry=REGISTRY)
DISCORD_HEALTH_REQUESTS = Counter('discord_health_requests_total', 'Total health check requests', registry=REGISTRY)
DISCORD_MESSAGE_PROCESSING_TIME = Histogram('discord_message_processing_seconds', 'Message processing time', registry=REGISTRY)


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
                logger.error(f"Missing required environment variable: {var} - {description}")
        
        if missing_vars:
            error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("Required environment variables validated")
        
        # Get bot token
        self.bot_token = os.getenv("DISCORD_BOT_TOKEN")
        
        # Initialize Discord bot with intents
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.members = True  # Required for user information
        
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        self._register_handlers()
        
        # Initialize health check server
        logger.info("Setting up health check server...")
        self.health_app = FastAPI()
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
            DISCORD_ACTIVE_USERS.set(len(self.bot.users))
        
        @self.bot.event
        async def on_message(message: discord.Message):
            # Ignore messages from bots
            if message.author.bot:
                return
            
            # Ignore messages that are commands
            if message.content.startswith('!'):
                await self.bot.process_commands(message)
                return
            
            # Process regular messages
            await self._handle_message(message)
        
        @self.bot.command(name='ping')
        async def ping_command(ctx):
            """Respond to ping command."""
            DISCORD_COMMANDS_TOTAL.labels(command='ping').inc()
            await ctx.send('Pong!')
        
        # Note: 'help' is a built-in command in discord.py, so we don't override it
        # Users can use !help to see all commands including !ping
    
    async def _handle_message(self, message: discord.Message):
        """Handle incoming Discord message."""
        try:
            DISCORD_MESSAGES_TOTAL.labels(type='text').inc()
            user_id = message.author.id
            channel_id = message.channel.id
            
            logger.info(f"Received message from user {user_id} in channel {channel_id}: {message.content[:100]}")
            
            # Show typing indicator
            async with message.channel.typing():
                # Stream responses from the agent
                message_count = 0
                last_message = None
                
                try:
                    for message_text, is_final in stream_agent_message(
                        message.content,
                        user_id=user_id,
                        chat_id=channel_id,
                        platform="discord",
                        agent_script_name="telegram_response_agent.sh",  # Use same script for now
                        agent_script_simple_name="telegram_response_agent_simple.sh",
                        max_message_length=2000  # Discord message limit
                    ):
                        # Skip empty messages (final signal)
                        if not message_text and is_final:
                            break
                        
                        if not message_text:
                            continue
                        
                        # Send the message
                        try:
                            sent_message = await message.channel.send(message_text)
                            message_count += 1
                            last_message = sent_message
                            logger.debug(f"Sent message {message_count} to user {user_id}")
                        except Exception as send_error:
                            logger.error(f"Failed to send message to Discord: {send_error}", exc_info=True)
                            if message_count == 0:
                                try:
                                    await message.channel.send(
                                        "❌ I encountered an error sending my response. Please try again."
                                    )
                                except:
                                    pass
                            break
                        
                        # If this is the final message, we're done
                        if is_final:
                            break
                    
                    if message_count > 0:
                        logger.info(f"Successfully sent {message_count} message(s) to user {user_id}")
                    else:
                        logger.warning(f"No messages were sent to user {user_id}")
                
                except Exception as stream_error:
                    logger.error(f"Error streaming agent response: {stream_error}", exc_info=True)
                    if message_count == 0:
                        try:
                            await message.channel.send(
                                "❌ I encountered an error processing your message. Please try again."
                            )
                        except Exception as send_error:
                            logger.error(f"Failed to send error message: {send_error}", exc_info=True)
        
        except Exception as e:
            logger.error(f"Error handling Discord message: {e}", exc_info=True)
            DISCORD_ERRORS_TOTAL.labels(error_type=type(e).__name__).inc()
            try:
                await message.channel.send(
                    "❌ I encountered an error processing your message. Please try again."
                )
            except:
                pass
    
    def _setup_health_endpoint(self):
        """Setup health check endpoint."""
        @self.health_app.get("/health")
        async def health_check():
            """Health check endpoint."""
            DISCORD_HEALTH_REQUESTS.inc()
            
            health_status = {
                "status": "healthy",
                "service": "discord-bot",
                "checks": {}
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
                    "missing_variables": missing_vars
                }
                overall_healthy = False
                http_status = 503
            else:
                health_status["checks"]["environment"] = {"status": "healthy"}
            
            # Check bot status
            if self.bot.is_ready():
                health_status["checks"]["bot"] = {
                    "status": "healthy",
                    "user": str(self.bot.user) if self.bot.user else None
                }
            else:
                health_status["checks"]["bot"] = {
                    "status": "degraded",
                    "message": "Bot not ready yet"
                }
            
            if not overall_healthy:
                health_status["status"] = "unhealthy"
            
            return JSONResponse(content=health_status, status_code=http_status)
        
        @self.health_app.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
        
        # Setup agent message test endpoint using shared base
        from essence.chat.interaction import setup_agent_message_endpoint
        
        def process_message_wrapper(user_message: str, user_id: Optional[int] = None, 
                                     chat_id: Optional[int] = None, **kwargs) -> Dict[str, Any]:
            """Wrapper for process_agent_message to match expected signature."""
            return process_agent_message(
                user_message,
                user_id=user_id,
                chat_id=chat_id,
                platform="discord",
                agent_script_name="telegram_response_agent.sh",
                agent_script_simple_name="telegram_response_agent_simple.sh",
                max_message_length=2000
            )
        
        setup_agent_message_endpoint(
            self.health_app,
            platform="discord",
            process_agent_message_func=process_message_wrapper,
            agent_script_name="telegram_response_agent.sh",
            agent_script_simple_name="telegram_response_agent_simple.sh",
            max_message_length=2000
        )
    
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
        
        # Start health check server in background
        health_server = uvicorn.Server(
            uvicorn.Config(
                self.health_app,
                host="0.0.0.0",
                port=int(os.getenv("DISCORD_SERVICE_PORT", "8081")),
                log_level="info"
            )
        )
        health_task = asyncio.create_task(health_server.serve())
        
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

