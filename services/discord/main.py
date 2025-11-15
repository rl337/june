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
# Use absolute path resolution to handle different working directories
_script_dir = Path(__file__).parent.absolute()
# main.py is in services/discord/, so parent is services/, parent.parent is deployment root
_deploy_root = _script_dir.parent.parent.absolute()

# Try multiple path resolution strategies
chat_base_path = None
candidates = [
    _deploy_root / "services" / "chat-service-base",
    _script_dir.parent / "chat-service-base",
    Path("services/chat-service-base").absolute(),
]

# Add explicit logging to see what we're checking
import logging as _logging
_temp_logger = _logging.getLogger(__name__)
for candidate in candidates:
    exists = candidate.exists()
    handler_exists = (candidate / "agent" / "handler.py").exists() if exists else False
    if exists and handler_exists:
        chat_base_path = candidate
        break

if chat_base_path:
    chat_base_abs = str(chat_base_path.absolute())
    sys.path.insert(0, chat_base_abs)  # Always insert, even if already there (move to front)
else:
    # Last resort: add current working directory's services/chat-service-base
    import os
    cwd_chat_base = Path(os.getcwd()) / "services" / "chat-service-base"
    if cwd_chat_base.exists() and (cwd_chat_base / "agent" / "handler.py").exists():
        sys.path.insert(0, str(cwd_chat_base.absolute()))

# Add essence module to path
essence_path = None
for candidate in [
    _deploy_root / "essence",
    _script_dir.parent.parent / "essence",
    Path("essence").absolute(),
]:
    if candidate.exists():
        essence_path = candidate
        break

if essence_path:
    essence_abs = str(essence_path.absolute())
    if essence_abs not in sys.path:
        sys.path.insert(0, essence_abs)

# Import human interface
from essence.chat.message_builder import MessageBuilder

from inference_core import config, setup_logging
from typing import Optional, Dict, Any

# Setup logging early
setup_logging(config.monitoring.log_level, "discord")
logger = logging.getLogger(__name__)

# Import from chat-service-base agent handler
# Add chat-service-base to sys.path first, then import normally
# This allows relative imports within the agent package to work
logger.info(f"chat_base_path={chat_base_path}, _deploy_root={_deploy_root}, _script_dir={_script_dir}")

if chat_base_path:
    chat_base_abs = str(chat_base_path.absolute())
    logger.info(f"Adding {chat_base_abs} to sys.path")
    sys.path.insert(0, chat_base_abs)
    logger.info(f"sys.path[0] is now: {sys.path[0]}")
    # Verify the handler file exists
    handler_file = chat_base_path / "agent" / "handler.py"
    logger.info(f"Handler file exists: {handler_file.exists()} at {handler_file}")
    # Now we can import normally, which will handle relative imports correctly
    from agent.handler import process_agent_message, stream_agent_message
    logger.info(f"Successfully imported agent.handler from {chat_base_abs}")
else:
    # Try one more time with explicit path
    explicit_path = _deploy_root / "services" / "chat-service-base"
    logger.error(f"chat_base_path is None. Trying explicit path: {explicit_path} (exists={explicit_path.exists()})")
    if explicit_path.exists():
        sys.path.insert(0, str(explicit_path.absolute()))
        from agent.handler import process_agent_message, stream_agent_message
        logger.info(f"Successfully imported agent.handler from explicit path")
    else:
        raise ImportError(f"Could not find chat-service-base directory. _deploy_root={_deploy_root}, _script_dir={_script_dir}, explicit_path={explicit_path}")

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
                # Initialize message builder for structured messaging
                message_builder = MessageBuilder(
                    service_name="discord",
                    user_id=str(user_id),
                    chat_id=str(channel_id)
                )
                
                # Stream responses from the agent
                message_count = 0
                last_message = None
                raw_llm_response = ""  # Track raw LLM response for building turn
                
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
                            # Final signal - build full turn, handle splitting, and log
                            if raw_llm_response:
                                try:
                                    # Build full turn for logging
                                    turn = message_builder.build_turn(message.content, raw_llm_response)
                                    rendered_parts = message_builder.split_message_if_needed(2000)
                                    
                                    if rendered_parts:
                                        if last_message:
                                            # Edit first part in place, send rest as new
                                            await last_message.edit(content=rendered_parts[0])
                                            for part in rendered_parts[1:]:
                                                await message.channel.send(part)
                                                message_count += 1
                                        else:
                                            # No message sent yet, send all parts
                                            last_message = await message.channel.send(rendered_parts[0])
                                            message_count += 1
                                            for part in rendered_parts[1:]:
                                                await message.channel.send(part)
                                                message_count += 1
                                    
                                    # Log the turn for debugging
                                    turn.log_to_file()
                                except Exception as edit_error:
                                    logger.error(f"Failed to edit final message: {edit_error}", exc_info=True)
                                    from essence.chat.error_handler import render_error_for_platform
                                    error_text = render_error_for_platform(
                                        edit_error,
                                        "discord",
                                        "❌ I encountered an error finalizing my response."
                                    )
                                    try:
                                        if last_message:
                                            await last_message.edit(content=error_text)
                                        else:
                                            await message.channel.send(error_text)
                                    except:
                                        pass
                            break
                        
                        if not message_text:
                            continue
                        
                        # Track the raw LLM response (use longest version for incremental updates)
                        if len(message_text) > len(raw_llm_response):
                            raw_llm_response = message_text
                            
                            # For streaming, parse and render incrementally
                            # Don't build full turn until final (that's expensive)
                            try:
                                from essence.chat.markdown_parser import parse_markdown
                                from essence.chat.platform_translators import get_translator
                                
                                # Parse markdown incrementally
                                widgets = parse_markdown(raw_llm_response)
                                translator = get_translator("discord")
                                rendered_text = translator.render_message(widgets)
                                
                                # Validate before sending
                                from essence.chat.platform_validators import get_validator
                                validator = get_validator("discord")
                                is_valid, errors = validator.validate(rendered_text)
                                
                                if not is_valid:
                                    # If invalid, escape the text to be safe
                                    logger.warning(f"Invalid Discord markdown detected, escaping: {errors}")
                                    from essence.chat.human_interface import EscapedText
                                    safe_widget = EscapedText(text=raw_llm_response)
                                    rendered_text = translator.render_widget(safe_widget)
                                
                                # Split if needed (but only for final, for streaming just use first part)
                                if len(rendered_text) > 2000:
                                    # For streaming, just show first part
                                    rendered_text = rendered_text[:2000]
                                
                                if last_message is None:
                                    # First message - send it immediately for streaming
                                    last_message = await message.channel.send(rendered_text)
                                    message_count += 1
                                    logger.debug(f"Sent initial streaming message to user {user_id} (length: {len(rendered_text)})")
                                else:
                                    # Update existing message in place for streaming
                                    await last_message.edit(content=rendered_text)
                                    logger.debug(f"Updated streaming message in place (length: {len(rendered_text)})")
                            except Exception as send_error:
                                logger.error(f"Failed to send/edit message to Discord: {send_error}", exc_info=True)
                                # Use structured error message
                                from essence.chat.error_handler import render_error_for_platform
                                error_text = render_error_for_platform(
                                    send_error,
                                    "discord",
                                    "❌ I encountered an error sending my response. Please try again."
                                )
                                if message_count == 0:
                                    try:
                                        await message.channel.send(error_text)
                                    except:
                                        pass
                                break
                        
                        # If this is the final message, we're done (but continue to get final signal)
                        if is_final:
                            continue
                    
                    if message_count > 0:
                        logger.info(f"Successfully sent {message_count} message(s) to user {user_id}")
                    else:
                        logger.warning(f"No messages were sent to user {user_id}")
                
                except Exception as stream_error:
                    logger.error(f"Error streaming agent response: {stream_error}", exc_info=True)
                    if message_count == 0:
                        try:
                            from essence.chat.error_handler import render_error_for_platform
                            error_text = render_error_for_platform(
                                stream_error,
                                "discord",
                                "❌ I encountered an error processing your message. Please try again."
                            )
                            await message.channel.send(error_text)
                        except Exception as send_error:
                            logger.error(f"Failed to send error message: {send_error}", exc_info=True)
        
        except Exception as e:
            logger.error(f"Error handling Discord message: {e}", exc_info=True)
            DISCORD_ERRORS_TOTAL.labels(error_type=type(e).__name__).inc()
            try:
                from essence.chat.error_handler import render_error_for_platform
                error_text = render_error_for_platform(
                    e,
                    "discord",
                    "❌ I encountered an error processing your message. Please try again."
                )
                await message.channel.send(error_text)
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
        
        try:
            setup_agent_message_endpoint(
                self.health_app,
                platform="discord",
                process_agent_message_func=process_message_wrapper,
                agent_script_name="telegram_response_agent.sh",
                agent_script_simple_name="telegram_response_agent_simple.sh",
                max_message_length=2000
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
                log_level="info"
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

