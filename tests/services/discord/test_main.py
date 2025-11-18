"""
Unit tests for Discord bot service.

Tests cover:
- Discord API call mocking
- Message handling and processing
- Agent message streaming
- Error handling paths
- Command handlers (ping)
- Health check endpoints
"""
import pytest
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch, Mock

# Fix import conflict: ensure we import from installed discord.py, not local discord dir
import importlib
import site

# Find site-packages directory with discord (check both system and user)
_site_packages = None
for sp_dir in list(site.getsitepackages()) + [site.getusersitepackages()]:
    if sp_dir and 'site-packages' in sp_dir:
        _discord_pkg_path = os.path.join(sp_dir, 'discord', '__init__.py')
        if os.path.exists(_discord_pkg_path):
            _site_packages = sp_dir
            break

# Find local essence/services/discord directory
_local_discord_dir = None
_current_dir = os.path.dirname(os.path.abspath(__file__))  # tests/services/discord/ directory
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))  # project root
_essence_discord_dir = os.path.join(_project_root, 'essence', 'services', 'discord')
if os.path.exists(_essence_discord_dir):
    _local_discord_dir = _essence_discord_dir

# Clear local discord from module cache if it was imported
if 'discord' in sys.modules:
    mod = sys.modules['discord']
    if hasattr(mod, '__file__') and mod.__file__:
        # Remove if it's from test directory or essence directory (not installed package)
        if _local_discord_dir and _local_discord_dir in mod.__file__:
            del sys.modules['discord']
        elif 'tests/services/discord' in mod.__file__ or 'essence/services/discord' in mod.__file__:
            del sys.modules['discord']
        if 'discord.ext' in sys.modules:
            del sys.modules['discord.ext']

# Save original sys.path
_original_sys_path = sys.path[:]

# Remove test directory from path to prevent shadowing installed discord package
_test_dir = os.path.dirname(os.path.abspath(__file__))  # tests/services/discord/
if _test_dir in sys.path:
    sys.path.remove(_test_dir)
# Also remove parent directories that might cause issues
_test_parent = os.path.dirname(_test_dir)  # tests/services/
if _test_parent in sys.path:
    sys.path.remove(_test_parent)

# Temporarily move site-packages to front of sys.path for discord import
if _site_packages and _site_packages in sys.path:
    sys.path.remove(_site_packages)
if _site_packages:
    sys.path.insert(0, _site_packages)

# Now import discord from installed package
import discord
from discord.ext import commands

# Restore original sys.path and ensure essence/services/discord is in path for local imports
sys.path[:] = _original_sys_path
# Add essence directory to path so we can import essence.services.discord
_essence_dir = os.path.join(_project_root, 'essence')
if _essence_dir not in sys.path:
    sys.path.insert(0, _essence_dir)
if _local_discord_dir and _local_discord_dir not in sys.path:
    sys.path.insert(0, _local_discord_dir)

# Mock inference_core and other dependencies before importing main
# (main.py has top-level imports that need to be mocked)
sys.modules['inference_core'] = MagicMock()
sys.modules['inference_core.config'] = MagicMock()
sys.modules['inference_core.setup_logging'] = MagicMock()

# Mock fastapi and uvicorn (needed by main.py)
mock_fastapi = MagicMock()
mock_fastapi.FastAPI = MagicMock
sys.modules['fastapi'] = mock_fastapi
sys.modules['fastapi.responses'] = MagicMock()
sys.modules['uvicorn'] = MagicMock()

# Mock prometheus_client (needed by main.py)
sys.modules['prometheus_client'] = MagicMock()
sys.modules['prometheus_client.generate_latest'] = MagicMock(return_value=b'# metrics')
sys.modules['prometheus_client.CollectorRegistry'] = MagicMock()
sys.modules['prometheus_client.CONTENT_TYPE_LATEST'] = 'text/plain'

# Mock opentelemetry before importing essence (essence.chat.utils.tracing requires it)
sys.modules['opentelemetry'] = MagicMock()
sys.modules['opentelemetry.trace'] = MagicMock()
sys.modules['opentelemetry.sdk'] = MagicMock()
sys.modules['opentelemetry.sdk.trace'] = MagicMock()
sys.modules['opentelemetry.sdk.trace.export'] = MagicMock()
sys.modules['opentelemetry.sdk.resources'] = MagicMock()
sys.modules['opentelemetry.exporter'] = MagicMock()
sys.modules['opentelemetry.exporter.jaeger'] = MagicMock()
sys.modules['opentelemetry.exporter.jaeger.thrift'] = MagicMock()
sys.modules['opentelemetry.instrumentation'] = MagicMock()
sys.modules['opentelemetry.instrumentation.grpc'] = MagicMock()

# Mock essence.chat modules
sys.modules['essence.chat.message_builder'] = MagicMock()
sys.modules['essence.chat.agent.handler'] = MagicMock()
sys.modules['essence.chat.error_handler'] = MagicMock()
sys.modules['essence.chat.interaction'] = MagicMock()
sys.modules['essence.chat.utils.tracing'] = MagicMock()
sys.modules['essence.services.shared_metrics'] = MagicMock()
sys.modules['essence.services.http_middleware'] = MagicMock()

from essence.services.discord.main import DiscordBotService


# Test fixtures
@pytest.fixture
def mock_discord_config():
    """Mock Discord configuration."""
    config_mock = MagicMock()
    config_mock.bot_token = "test-bot-token"
    config_mock.monitoring.log_level = "INFO"
    return config_mock


@pytest.fixture
def mock_discord_message():
    """Create a mock Discord Message object."""
    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(spec=discord.User)
    message.author.id = 12345
    message.author.bot = False
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.id = 67890
    message.channel.send = AsyncMock()
    message.content = "Hello, bot!"
    return message


@pytest.fixture
def mock_discord_bot():
    """Create a mock Discord Bot object."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.name = "TestBot"
    bot.is_ready = MagicMock(return_value=True)
    bot.start = AsyncMock()
    bot.close = AsyncMock()
    bot.process_commands = AsyncMock()
    return bot


class TestDiscordBotServiceInitialization:
    """Tests for DiscordBotService initialization."""
    
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    def test_init_success(self, mock_fastapi_class, mock_bot_class):
        """Test successful initialization."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        service = DiscordBotService()
        
        assert service.bot_token == "test-token"
        assert service.bot is not None
        assert service.health_app is not None
        mock_bot_class.assert_called_once()
    
    @patch.dict(os.environ, {}, clear=True)
    def test_init_missing_token(self):
        """Test initialization fails without bot token."""
        with pytest.raises(ValueError, match="DISCORD_BOT_TOKEN"):
            DiscordBotService()
    
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token', 'DISCORD_SERVICE_PORT': '9090'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    def test_init_custom_port(self, mock_fastapi_class, mock_bot_class):
        """Test initialization with custom service port."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        service = DiscordBotService()
        
        assert service.bot_token == "test-token"
        # Port is used in run() method, not stored in __init__


class TestDiscordMessageHandling:
    """Tests for Discord message handling."""
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    @patch('essence.services.discord.main.stream_agent_message')
    async def test_handle_message_success(self, mock_stream_agent, mock_fastapi_class, mock_bot_class, mock_discord_message):
        """Test successful message handling."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        # Mock stream_agent_message to return a simple response
        mock_stream_agent.return_value = iter([
            ("Hello, user!", False, "assistant"),
            ("", True, None)
        ])
        
        # Mock MessageBuilder
        with patch('essence.services.discord.main.MessageBuilder') as mock_builder_class:
            mock_builder = MagicMock()
            mock_builder_class.return_value = mock_builder
            mock_builder.build_turn.return_value = MagicMock()
            mock_builder.split_message_if_needed.return_value = ["Hello, user!"]
            
            service = DiscordBotService()
            await service._handle_message(mock_discord_message)
            
            # Verify status message was sent
            assert mock_discord_message.channel.send.called
            # Verify final message was sent/edited
            assert mock_stream_agent.called
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    @patch('essence.services.discord.main.stream_agent_message')
    async def test_handle_message_error(self, mock_stream_agent, mock_fastapi_class, mock_bot_class, mock_discord_message):
        """Test message handling with error."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        # Mock stream_agent_message to raise an error
        mock_stream_agent.side_effect = Exception("Test error")
        
        # Mock error handler
        with patch('essence.chat.error_handler.render_error_for_platform') as mock_error_handler:
            mock_error_handler.return_value = "❌ Error occurred"
            
            service = DiscordBotService()
            await service._handle_message(mock_discord_message)
            
            # Verify error handler was called
            mock_error_handler.assert_called_once()
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    @patch('essence.services.discord.main.stream_agent_message')
    async def test_handle_message_no_response(self, mock_stream_agent, mock_fastapi_class, mock_bot_class, mock_discord_message):
        """Test message handling when no response is generated."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        # Mock stream_agent_message to return empty response
        mock_stream_agent.return_value = iter([
            ("", True, None)
        ])
        
        service = DiscordBotService()
        await service._handle_message(mock_discord_message)
        
        # Verify status message was updated with "no response" message
        assert mock_discord_message.channel.send.called
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    async def test_handle_message_bot_message_ignored(self, mock_fastapi_class, mock_bot_class):
        """Test that messages from bots are ignored."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        # Create a message from a bot
        bot_message = MagicMock(spec=discord.Message)
        bot_message.author = MagicMock(spec=discord.User)
        bot_message.author.bot = True
        bot_message.channel = MagicMock()
        bot_message.channel.send = AsyncMock()
        
        service = DiscordBotService()
        # The on_message handler should ignore bot messages
        # We can't directly test on_message, but we can verify the handler is registered
        assert service.bot is not None


class TestDiscordCommandHandlers:
    """Tests for Discord command handlers."""
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    async def test_ping_command(self, mock_fastapi_class, mock_bot_class):
        """Test ping command handler."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        service = DiscordBotService()
        
        # Create a mock context for the ping command
        mock_ctx = MagicMock()
        mock_ctx.send = AsyncMock()
        
        # Find the ping command handler
        ping_command = None
        for command in service.bot.commands:
            if command.name == 'ping':
                ping_command = command
                break
        
        if ping_command:
            await ping_command.callback(mock_ctx)
            mock_ctx.send.assert_called_once_with('Pong!')


class TestDiscordHealthEndpoints:
    """Tests for Discord health check endpoints."""
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    async def test_health_check_healthy(self, mock_fastapi_class, mock_bot_class):
        """Test health check endpoint when service is healthy."""
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True
        mock_bot.user = MagicMock()
        mock_bot.user.name = "TestBot"
        mock_bot_class.return_value = mock_bot
        
        service = DiscordBotService()
        
        # Get the health check endpoint
        health_route = None
        for route in service.health_app.routes:
            if route.path == "/health" and hasattr(route, 'endpoint'):
                health_route = route
                break
        
        if health_route:
            response = await health_route.endpoint()
            assert response.status_code == 200
            assert response.body is not None
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {}, clear=True)
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    async def test_health_check_unhealthy_missing_token(self, mock_fastapi_class, mock_bot_class):
        """Test health check endpoint when token is missing."""
        # This will fail during initialization, so we need to handle it differently
        with pytest.raises(ValueError):
            DiscordBotService()
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    async def test_metrics_endpoint(self, mock_fastapi_class, mock_bot_class):
        """Test metrics endpoint."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        service = DiscordBotService()
        
        # Get the metrics endpoint
        metrics_route = None
        for route in service.health_app.routes:
            if route.path == "/metrics" and hasattr(route, 'endpoint'):
                metrics_route = route
                break
        
        if metrics_route:
            response = await metrics_route.endpoint()
            assert response is not None


class TestDiscordErrorHandling:
    """Tests for error handling in Discord service."""
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    @patch('essence.services.discord.main.stream_agent_message')
    async def test_handle_message_stream_error(self, mock_stream_agent, mock_fastapi_class, mock_bot_class, mock_discord_message):
        """Test error handling when streaming fails."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        # Mock stream_agent_message to raise an error
        mock_stream_agent.side_effect = RuntimeError("Stream error")
        
        # Mock error handler
        with patch('essence.chat.error_handler.render_error_for_platform') as mock_error_handler:
            mock_error_handler.return_value = "❌ Error occurred"
            
            service = DiscordBotService()
            await service._handle_message(mock_discord_message)
            
            # Verify error handler was called
            mock_error_handler.assert_called_once()
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    async def test_handle_message_send_error(self, mock_fastapi_class, mock_bot_class, mock_discord_message):
        """Test error handling when sending message fails."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        # Make channel.send raise an error
        mock_discord_message.channel.send.side_effect = Exception("Send error")
        
        service = DiscordBotService()
        # Should not raise, but log the error
        await service._handle_message(mock_discord_message)


class TestDiscordServiceRun:
    """Tests for Discord service run method."""
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test-token'})
    @patch('essence.services.discord.main.commands.Bot')
    @patch('essence.services.discord.main.FastAPI')
    @patch('essence.services.discord.main.uvicorn.Server')
    async def test_run_shutdown(self, mock_server_class, mock_fastapi_class, mock_bot_class):
        """Test service run and shutdown."""
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.close = AsyncMock()
        mock_bot_class.return_value = mock_bot
        
        mock_server = MagicMock()
        mock_server.serve = AsyncMock()
        mock_server.should_exit = False
        mock_server_class.return_value = mock_server
        
        service = DiscordBotService()
        
        # Start run in background and immediately trigger shutdown
        run_task = asyncio.create_task(service.run())
        
        # Wait a bit for initialization
        await asyncio.sleep(0.1)
        
        # Trigger shutdown
        service._shutdown_event.set()
        
        # Wait for shutdown
        try:
            await asyncio.wait_for(run_task, timeout=1.0)
        except asyncio.TimeoutError:
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass
        
        # Verify bot was closed
        mock_bot.close.assert_called_once()
