"""
Unit tests for Telegram bot service.

Tests cover:
- Telegram API call mocking
- STT/TTS/LLM service call mocking
- Audio format conversion integration
- Error handling paths
- Command handlers
- Voice message processing flow
"""
import pytest
import asyncio
import io
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch, Mock

# Fix import conflict: ensure we import from installed python-telegram-bot, not local telegram dir
# The local services/telegram/__init__.py shadows the installed package when pytest runs from root
# Strategy: Remove local telegram from module cache, import from installed package, then restore path
import importlib
import site
import os.path

# Find site-packages directory with telegram (check both system and user)
_site_packages = None
for sp_dir in list(site.getsitepackages()) + [site.getusersitepackages()]:
    if sp_dir and 'site-packages' in sp_dir:
        _telegram_pkg_path = os.path.join(sp_dir, 'telegram', '__init__.py')
        if os.path.exists(_telegram_pkg_path):
            _site_packages = sp_dir
            break

# Find local essence/services/telegram directory
_local_telegram_dir = None
_current_dir = os.path.dirname(os.path.abspath(__file__))  # tests/services/telegram/ directory
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))  # project root
_essence_telegram_dir = os.path.join(_project_root, 'essence', 'services', 'telegram')
if os.path.exists(_essence_telegram_dir):
    _local_telegram_dir = _essence_telegram_dir

# Clear local telegram from module cache if it was imported
if 'telegram' in sys.modules:
    mod = sys.modules['telegram']
    if hasattr(mod, '__file__') and mod.__file__:
        # Remove if it's from test directory or essence directory (not installed package)
        if _local_telegram_dir and _local_telegram_dir in mod.__file__:
            del sys.modules['telegram']
        elif 'tests/services/telegram' in mod.__file__ or 'essence/services/telegram' in mod.__file__:
            del sys.modules['telegram']
        if 'telegram.ext' in sys.modules:
            del sys.modules['telegram.ext']

# Save original sys.path
_original_sys_path = sys.path[:]

# Remove test directory from path to prevent shadowing installed telegram package
_test_dir = os.path.dirname(os.path.abspath(__file__))  # tests/services/telegram/
if _test_dir in sys.path:
    sys.path.remove(_test_dir)
# Also remove parent directories that might cause issues
_test_parent = os.path.dirname(_test_dir)  # tests/services/
if _test_parent in sys.path:
    sys.path.remove(_test_parent)

# Temporarily move site-packages to front of sys.path for telegram import
if _site_packages and _site_packages in sys.path:
    sys.path.remove(_site_packages)
if _site_packages:
    sys.path.insert(0, _site_packages)

# Now import telegram from installed package
from telegram import Update, Message, Voice, File, User, Chat
from telegram.ext import ContextTypes

# Restore original sys.path and ensure essence/services/telegram is in path for local imports
sys.path[:] = _original_sys_path
# Add essence directory to path so we can import essence.services.telegram
_essence_dir = os.path.join(_project_root, 'essence')
if _essence_dir not in sys.path:
    sys.path.insert(0, _essence_dir)
if _local_telegram_dir and _local_telegram_dir not in sys.path:
    sys.path.insert(0, _local_telegram_dir)

# Mock inference_core and other dependencies before importing main
# (main.py and handlers have top-level imports that need to be mocked)
sys.modules['inference_core'] = MagicMock()
sys.modules['inference_core.config'] = MagicMock()
sys.modules['inference_core.setup_logging'] = MagicMock()

# Mock grpc (needed by handlers/voice.py)
sys.modules['grpc'] = MagicMock()
sys.modules['grpc.aio'] = MagicMock()

# Mock asr_shim (needed by handlers/voice.py)
sys.modules['asr_shim'] = MagicMock()
sys.modules['asr_shim.SpeechToTextClient'] = MagicMock()

# Mock june_grpc_api (needed by handlers/voice.py)
# Create a simple object for june_grpc_api (not MagicMock, so attributes work correctly)
class MockJuneGrpcApi:
    pass
mock_june_grpc_api = MockJuneGrpcApi()

# Create a simple object for the asr module (not MagicMock, so attributes work correctly)
class MockAsrModule:
    RecognitionConfig = MagicMock
    SpeechToTextClient = None  # Will be set in individual tests
mock_asr_module = MockAsrModule()
mock_june_grpc_api.asr = mock_asr_module

# Create shim module
class MockShimModule:
    pass
mock_shim_module = MockShimModule()

# Create llm and tts submodules
class MockLlmModule:
    LLMClient = None  # Will be set in tests
class MockTtsModule:
    TextToSpeechClient = None  # Will be set in tests

mock_llm_module = MockLlmModule()
mock_tts_module = MockTtsModule()
mock_shim_module.llm = mock_llm_module
mock_shim_module.tts = mock_tts_module
mock_june_grpc_api.shim = mock_shim_module

sys.modules['june_grpc_api'] = mock_june_grpc_api
sys.modules['june_grpc_api.asr'] = mock_asr_module
sys.modules['june_grpc_api.shim'] = mock_shim_module
sys.modules['june_grpc_api.shim.llm'] = mock_llm_module
sys.modules['june_grpc_api.shim.tts'] = mock_tts_module

# Mock librosa (needed by handlers/voice.py)
sys.modules['librosa'] = MagicMock()

# Mock httpx (needed by handlers/voice.py)
sys.modules['httpx'] = MagicMock()

# Mock fastapi and uvicorn (needed by main.py)
mock_fastapi = MagicMock()
mock_fastapi.FastAPI = MagicMock
sys.modules['fastapi'] = mock_fastapi
sys.modules['fastapi.responses'] = MagicMock()
sys.modules['uvicorn'] = MagicMock()

# Mock psycopg2 (needed by admin_auth.py and admin_db.py)
sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.pool'] = MagicMock()
sys.modules['psycopg2.extras'] = MagicMock()
mock_psycopg2_extras = MagicMock()
mock_psycopg2_extras.RealDictCursor = MagicMock()
sys.modules['psycopg2.extras'] = mock_psycopg2_extras

# Mock admin_db (needed by handlers/admin_commands.py)
sys.modules['admin_db'] = MagicMock()

# Mock admin_auth (needed by handlers/admin_commands.py)
sys.modules['admin_auth'] = MagicMock()
mock_admin_auth = MagicMock()
mock_admin_auth.require_admin = lambda func: func  # Decorator that returns function as-is
mock_admin_auth.is_admin = MagicMock(return_value=False)
sys.modules['admin_auth'] = mock_admin_auth

# Mock dependencies.config before importing (to avoid ServiceConfig import issue)
sys.modules['dependencies'] = MagicMock()
sys.modules['dependencies.config'] = MagicMock()
mock_deps_config = MagicMock()
mock_deps_config.get_service_config = MagicMock()
mock_deps_config.get_stt_address = MagicMock()
mock_deps_config.get_llm_address = MagicMock(return_value="llm:50052")
mock_deps_config.get_tts_address = MagicMock(return_value="tts:50052")
mock_deps_config.get_metrics_storage = MagicMock()
sys.modules['dependencies.config'] = mock_deps_config

from essence.services.telegram.main import TelegramBotService
from essence.services.telegram.audio_utils import AudioValidationError, prepare_audio_for_stt
from essence.services.telegram.handlers.commands import start_command, help_command, status_command
from essence.services.telegram.handlers.voice import handle_voice_message


# Test fixtures
@pytest.fixture
def mock_telegram_config():
    """Mock Telegram configuration."""
    config_mock = MagicMock()
    config_mock.bot_token = "test-bot-token"
    config_mock.max_file_size = 20 * 1024 * 1024  # 20 MB
    return config_mock


@pytest.fixture
def mock_inference_config():
    """Mock inference-core config."""
    config_mock = MagicMock()
    config_mock.telegram.bot_token = "test-bot-token"
    config_mock.telegram.max_file_size = 20 * 1024 * 1024
    config_mock.monitoring.log_level = "INFO"
    return config_mock


@pytest.fixture
def sample_audio_data():
    """Create sample audio data for testing (mock to avoid ffmpeg dependency)."""
    # Return mock WAV data - just enough bytes to simulate a WAV file
    # Real WAV files start with "RIFF" header, but for testing we just need bytes
    return b'RIFF' + b'\x00' * 1000  # "RIFF" header + padding


@pytest.fixture
def sample_ogg_audio():
    """Create sample OGG audio data for testing (mock to avoid ffmpeg dependency)."""
    # Return mock OGG data - just enough bytes to simulate an OGG file
    # Real OGG files start with "OggS" header, but for testing we just need bytes
    return b'\x4f\x67\x67\x53' + b'\x00' * 1000  # "OggS" header + padding


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update object."""
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.message.reply_voice = AsyncMock()
    update.message.voice = MagicMock(spec=Voice)
    update.message.chat = MagicMock(spec=Chat)
    update.message.chat.id = 12345
    return update


@pytest.fixture
def mock_context():
    """Create a mock ContextTypes.DEFAULT_TYPE object."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.get_file = AsyncMock()
    return context


@pytest.fixture
def mock_telegram_file():
    """Create a mock Telegram File object."""
    file = MagicMock(spec=File)
    file.download_as_bytearray = AsyncMock()
    return file


class TestTelegramBotServiceInitialization:
    """Tests for TelegramBotService initialization."""
    
    @patch('essence.services.telegram.main.get_service_config')
    @patch('essence.services.telegram.main.get_stt_address')
    @patch('essence.services.telegram.main.Application')
    @patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test-token'})
    def test_init_success(self, mock_app_class, mock_get_stt_address, mock_get_service_config):
        """Test successful initialization."""
        mock_config = MagicMock()
        mock_config.bot_token = "test-token"
        mock_config.max_file_size = 20 * 1024 * 1024
        mock_get_service_config.return_value = mock_config
        mock_get_stt_address.return_value = "stt:50052"
        
        mock_app = MagicMock()
        mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
        
        service = TelegramBotService()
        
        assert service.config is not None
        assert service.application is not None
        assert service.config.bot_token == "test-token"
        mock_app_class.builder.assert_called_once()
    
    @patch('essence.services.telegram.main.get_service_config')
    @patch('essence.services.telegram.main.get_stt_address')
    @patch('essence.services.telegram.main.Application')
    @patch.dict(os.environ, {}, clear=True)
    def test_init_missing_token(self, mock_app_class, mock_get_stt_address, mock_get_service_config):
        """Test initialization fails without bot token."""
        mock_config = MagicMock()
        mock_config.bot_token = None
        mock_get_service_config.return_value = mock_config
        mock_get_stt_address.return_value = "stt:50052"
        
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            TelegramBotService()
    
    @patch('essence.services.telegram.main.get_service_config')
    @patch('essence.services.telegram.main.get_stt_address')
    @patch('essence.services.telegram.main.Application')
    @patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test-token', 'STT_URL': 'grpc://custom-stt:50052'})
    def test_init_custom_service_urls(self, mock_app_class, mock_get_stt_address, mock_get_service_config):
        """Test initialization with custom service URLs."""
        mock_config = MagicMock()
        mock_config.bot_token = "test-token"
        mock_config.max_file_size = 20 * 1024 * 1024
        mock_get_service_config.return_value = mock_config
        mock_get_stt_address.return_value = "custom-stt:50052"
        
        mock_app = MagicMock()
        mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
        
        service = TelegramBotService()
        
        # Should have stt_address from get_stt_address
        assert service.stt_address == "custom-stt:50052"
        assert "grpc://" not in service.stt_address


class TestCommandHandlers:
    """Tests for command handlers (start, help, status)."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock config object."""
        config = MagicMock()
        config.bot_token = "test-token"
        config.max_file_size = 20 * 1024 * 1024
        config.monitoring.log_level = "INFO"
        return config
    
    @pytest.mark.asyncio
    async def test_start_command(self, mock_update, mock_config):
        """Test /start command handler."""
        await start_command(mock_update, None, mock_config)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Hello" in call_args
        assert "June" in call_args
        assert "voice message" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_help_command(self, mock_update, mock_config):
        """Test /help command handler."""
        await help_command(mock_update, None, mock_config)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Help" in call_args or "help" in call_args.lower()
        assert "/start" in call_args
        assert "/help" in call_args
        assert "/status" in call_args
    
    @pytest.mark.asyncio
    async def test_status_command(self, mock_update, mock_config):
        """Test /status command handler."""
        await status_command(mock_update, None, mock_config)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Status" in call_args or "status" in call_args.lower()
        assert "Bot" in call_args or "bot" in call_args.lower()


class TestVoiceMessageHandling:
    """Tests for voice message handling."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock config object."""
        config = MagicMock()
        config.bot_token = "test-token"
        config.max_file_size = 20 * 1024 * 1024
        config.monitoring.log_level = "INFO"
        return config
    
    @pytest.fixture
    def mock_get_metrics_storage(self):
        """Create a mock metrics storage getter."""
        metrics_storage = MagicMock()
        metrics_storage.record_transcription = MagicMock()
        return lambda: metrics_storage
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_file_too_large(self, mock_update, mock_context, mock_config, mock_get_metrics_storage):
        """Test voice message rejection when file is too large."""
        # Set voice file size to exceed limit
        mock_update.message.voice.file_size = mock_config.max_file_size + 1
        
        await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
        
        # Should reply with error message
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "too large" in call_args.lower() or "large" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_success(
        self, mock_update, mock_context, mock_telegram_file, sample_ogg_audio, mock_config, mock_get_metrics_storage
    ):
        """Test successful voice message processing."""
        # Setup mocks
        mock_update.message.voice.file_size = 1000  # Small file
        mock_update.message.voice.file_id = "test-file-id"
        mock_context.bot.get_file.return_value = mock_telegram_file
        mock_telegram_file.download_as_bytearray.return_value = bytearray(sample_ogg_audio)
        
        # Mock status message editing
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        # Mock STT service
        mock_stt_result = MagicMock()
        mock_stt_result.transcript = "Hello, this is a test transcription"
        
        # Create mock STT client with recognize as AsyncMock
        # The handler imports: from june_grpc_api import asr as asr_shim
        # Then calls: asr_shim.SpeechToTextClient(channel)
        # Create a proper mock class to avoid MagicMock attribute issues
        class MockSTTClient:
            def __init__(self, channel):
                self.channel = channel
            async def recognize(self, *args, **kwargs):
                return mock_stt_result
        
        # Create mock classes for LLM and TTS clients
        class MockLLMClient:
            def __init__(self, channel):
                self.channel = channel
            async def chat(self, *args, **kwargs):
                return "Mock LLM response"
        
        class MockTTSClient:
            def __init__(self, channel):
                self.channel = channel
            async def synthesize(self, *args, **kwargs):
                return b'mock_tts_audio'
        
        # Set mock clients on the modules (similar to SpeechToTextClient)
        sys.modules['june_grpc_api.asr'].SpeechToTextClient = MockSTTClient
        sys.modules['june_grpc_api.shim.llm'].LLMClient = MockLLMClient
        sys.modules['june_grpc_api.shim.tts'].TextToSpeechClient = MockTTSClient
        
        with patch('grpc.aio.insecure_channel') as mock_channel, \
             patch('handlers.voice.enhance_audio_for_stt') as mock_enhance, \
             patch('handlers.voice.prepare_audio_for_stt') as mock_prepare, \
             patch('june_grpc_api.asr.RecognitionConfig', MagicMock), \
             patch('handlers.voice.AudioSegment') as mock_audio_segment, \
             patch('handlers.voice.export_audio_to_ogg_optimized') as mock_export_ogg, \
             patch('handlers.voice.find_optimal_compression') as mock_find_compression:
            
            # Mock audio enhancement (the handler now uses enhance_audio_for_stt)
            mock_enhance.return_value = b'mock_prepared_audio'
            # Also mock prepare_audio_for_stt for backward compatibility
            mock_prepare.return_value = b'mock_prepared_audio'
            
            # Mock OGG export functions
            mock_find_compression.return_value = ('medium', {'bitrate': 64})
            mock_export_ogg.return_value = {
                'compressed_size': 1000,
                'compression_ratio': 1.5,
                'preset': 'medium'
            }
            
            # Mock async context manager for channel
            mock_channel.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_channel.return_value.__aexit__ = AsyncMock(return_value=False)
            
            # Note: LLM and TTS clients are now set directly on modules above
            # No need for additional mocking since MockLLMClient and MockTTSClient are used
            
            # Mock AudioSegment with proper attributes
            mock_audio = MagicMock()
            # Mock export to actually write a file (for export_audio_to_ogg_optimized)
            def mock_export(path, format='ogg', **kwargs):
                # Create the file so the code can verify it exists
                with open(path, 'wb') as f:
                    f.write(b'mock_ogg_audio_data')
            mock_audio.export = MagicMock(side_effect=mock_export)
            mock_audio.channels = 1  # Mono audio
            mock_audio.frame_rate = 16000  # 16kHz sample rate
            mock_audio.duration_seconds = 1.0  # 1 second duration
            mock_audio.frame_width = 2  # 16-bit = 2 bytes
            mock_audio_segment.from_wav.return_value = mock_audio
            mock_audio_segment.from_file.return_value = mock_audio  # For fallback format detection
            
            # Mock httpx for conversation API (httpx is imported inside the handler)
            mock_response = MagicMock()
            mock_response.status_code = 404  # Conversation doesn't exist
            mock_response.json.return_value = {"messages": []}
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_httpx_module = sys.modules['httpx']
            mock_httpx_module.AsyncClient = MagicMock()
            mock_httpx_module.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx_module.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
            
            # Mock tempfile and file operations
            with patch('handlers.voice.tempfile.NamedTemporaryFile') as mock_tempfile, \
                 patch('handlers.voice.os.unlink') as mock_unlink, \
                 patch('builtins.open', create=True):
                mock_tempfile.return_value.__enter__ = lambda self: self
                mock_tempfile.return_value.__exit__ = lambda *args: None
                mock_tempfile.return_value.name = '/tmp/test.ogg'
                mock_update.message.reply_voice = AsyncMock()
                
                await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
                
                # Verify status messages were sent
                assert mock_update.message.reply_text.call_count >= 1
                # Verify final status was updated
                assert mock_status_msg.edit_text.call_count >= 1
                # Verify reply_voice was called (indicates successful completion)
                # This verifies the full flow worked, including STT recognition
                mock_update.message.reply_voice.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_audio_validation_error(
        self, mock_update, mock_context, mock_telegram_file, sample_ogg_audio, mock_config, mock_get_metrics_storage
    ):
        """Test handling of audio validation errors."""
        # Setup mocks
        mock_update.message.voice.file_size = 1000
        mock_update.message.voice.file_id = "test-file-id"
        mock_context.bot.get_file.return_value = mock_telegram_file
        mock_telegram_file.download_as_bytearray.return_value = bytearray(sample_ogg_audio)
        
        # Mock status message
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        # Mock audio validation to raise error
        with patch('handlers.voice.prepare_audio_for_stt', side_effect=AudioValidationError("Audio too long")):
            await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
            
            # Should show validation error
            mock_status_msg.edit_text.assert_called()
            call_args = str(mock_status_msg.edit_text.call_args)
            assert "validation" in call_args.lower() or "failed" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_stt_error(
        self, mock_update, mock_context, mock_telegram_file, sample_ogg_audio, mock_config, mock_get_metrics_storage
    ):
        """Test handling of STT service errors."""
        # Setup mocks
        mock_update.message.voice.file_size = 1000
        mock_update.message.voice.file_id = "test-file-id"
        mock_context.bot.get_file.return_value = mock_telegram_file
        mock_telegram_file.download_as_bytearray.return_value = bytearray(sample_ogg_audio)
        
        # Mock status message
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        # Mock audio preparation
        mock_prepare = patch('handlers.voice.prepare_audio_for_stt', return_value=b'mock_prepared_audio')
        
        # Mock STT to raise error
        mock_stt_client = MagicMock()
        mock_stt_client.recognize = AsyncMock(side_effect=Exception("STT service unavailable"))
        
        with patch('grpc.aio.insecure_channel') as mock_channel, \
             patch('june_grpc_api.asr.SpeechToTextClient', return_value=mock_stt_client), \
             mock_prepare:
            
            # Mock async context manager for channel
            mock_channel.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_channel.return_value.__aexit__ = AsyncMock(return_value=False)
            
            await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
            
            # Should show STT error
            mock_status_msg.edit_text.assert_called()
            call_args = str(mock_status_msg.edit_text.call_args)
            assert "transcription" in call_args.lower() or "failed" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_download_error(
        self, mock_update, mock_context, mock_config, mock_get_metrics_storage
    ):
        """Test handling of file download errors."""
        # Setup mocks
        mock_update.message.voice.file_size = 1000
        mock_update.message.voice.file_id = "test-file-id"
        mock_context.bot.get_file.side_effect = Exception("Download failed")
        
        # Mock status message
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
        
        # Should show error message
        mock_status_msg.edit_text.assert_called()
        call_args = str(mock_status_msg.edit_text.call_args)
        assert "error" in call_args.lower() or "failed" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_audio_preparation_error(
        self, mock_update, mock_context, mock_telegram_file, sample_ogg_audio, mock_config, mock_get_metrics_storage
    ):
        """Test handling of audio preparation/conversion errors."""
        # Setup mocks
        mock_update.message.voice.file_size = 1000
        mock_update.message.voice.file_id = "test-file-id"
        mock_context.bot.get_file.return_value = mock_telegram_file
        mock_telegram_file.download_as_bytearray.return_value = bytearray(sample_ogg_audio)
        
        # Mock status message
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        # Mock audio preparation to raise ValueError
        with patch('handlers.voice.prepare_audio_for_stt', side_effect=ValueError("Invalid audio format")):
            await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
            
            # Should show error message
            mock_status_msg.edit_text.assert_called()
            call_args = str(mock_status_msg.edit_text.call_args)
            assert "error" in call_args.lower() or "processing" in call_args.lower()


class TestErrorHandlingPaths:
    """Tests for various error handling paths."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock config object."""
        config = MagicMock()
        config.bot_token = "test-token"
        config.max_file_size = 20 * 1024 * 1024
        config.monitoring.log_level = "INFO"
        return config
    
    @pytest.fixture
    def mock_get_metrics_storage(self):
        """Create a mock metrics storage getter."""
        metrics_storage = MagicMock()
        metrics_storage.record_transcription = MagicMock()
        return lambda: metrics_storage
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_generic_exception(
        self, mock_update, mock_context, mock_config, mock_get_metrics_storage
    ):
        """Test handling of generic exceptions."""
        # Setup to raise exception early
        mock_update.message.voice.file_size = 1000
        mock_context.bot.get_file.side_effect = Exception("Unexpected error")
        
        # Mock status message
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
        
        # Should handle gracefully and show error
        mock_status_msg.edit_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_no_file_size(
        self, mock_update, mock_context, mock_telegram_file, sample_ogg_audio, mock_config, mock_get_metrics_storage
    ):
        """Test handling when voice message has no file_size attribute."""
        # Setup mocks - file_size is None
        mock_update.message.voice.file_size = None
        mock_update.message.voice.file_id = "test-file-id"
        mock_context.bot.get_file.return_value = mock_telegram_file
        mock_telegram_file.download_as_bytearray.return_value = bytearray(sample_ogg_audio)
        
        # Mock status message
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        # Mock STT
        mock_stt_result = MagicMock()
        mock_stt_result.transcript = "Test"
        mock_stt_client = MagicMock()
        mock_stt_client.recognize = AsyncMock(return_value=mock_stt_result)
        
        with patch('grpc.aio.insecure_channel') as mock_channel, \
             patch('june_grpc_api.asr.SpeechToTextClient', return_value=mock_stt_client), \
             patch('handlers.voice.prepare_audio_for_stt', return_value=b'mock_prepared_audio'), \
             patch('june_grpc_api.shim.llm.LLMClient') as mock_llm_client_class, \
             patch('june_grpc_api.shim.tts.TextToSpeechClient') as mock_tts_client_class, \
             patch('handlers.voice.AudioSegment') as mock_audio_segment:
            
            mock_channel.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_channel.return_value.__aexit__ = AsyncMock(return_value=False)
            
            # Mock LLM and TTS clients (simplified - just enough to get past errors)
            mock_llm_client = MagicMock()
            mock_llm_client.chat = AsyncMock(return_value="Mock LLM response")
            mock_llm_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_llm_client)
            mock_llm_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            
            mock_tts_client = MagicMock()
            mock_tts_client.synthesize = AsyncMock(return_value=b'mock_tts_audio')
            mock_tts_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_tts_client)
            mock_tts_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            
            mock_audio = MagicMock()
            mock_audio.export = MagicMock()
            mock_audio_segment.from_wav.return_value = mock_audio
            
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"messages": []}
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.post.return_value = mock_response
            mock_httpx_module = sys.modules['httpx']
            mock_httpx_module.AsyncClient = MagicMock()
            mock_httpx_module.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx_module.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
            
            with patch('handlers.voice.tempfile.NamedTemporaryFile') as mock_tempfile, \
                 patch('handlers.voice.os.unlink') as mock_unlink, \
                 patch('builtins.open', create=True):
                mock_tempfile.return_value.__enter__ = lambda self: self
                mock_tempfile.return_value.__exit__ = lambda *args: None
                mock_tempfile.return_value.name = '/tmp/test.ogg'
                mock_update.message.reply_voice = AsyncMock()
                
                # Should proceed (file_size check only runs if file_size is not None)
                await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
                
                # Should have processed the message
                assert mock_update.message.reply_text.call_count >= 1


class TestAudioFormatConversionIntegration:
    """Tests for audio format conversion integration with voice handling."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock config object."""
        config = MagicMock()
        config.bot_token = "test-token"
        config.max_file_size = 20 * 1024 * 1024
        config.monitoring.log_level = "INFO"
        return config
    
    @pytest.fixture
    def mock_get_metrics_storage(self):
        """Create a mock metrics storage getter."""
        metrics_storage = MagicMock()
        metrics_storage.record_transcription = MagicMock()
        return lambda: metrics_storage
    
    @pytest.mark.asyncio
    async def test_audio_conversion_in_voice_processing(
        self, mock_update, mock_context, mock_telegram_file, sample_ogg_audio, mock_config, mock_get_metrics_storage
    ):
        """Test that audio conversion is properly integrated in voice processing."""
        # Setup mocks
        mock_update.message.voice.file_size = 1000
        mock_update.message.voice.file_id = "test-file-id"
        mock_context.bot.get_file.return_value = mock_telegram_file
        mock_telegram_file.download_as_bytearray.return_value = bytearray(sample_ogg_audio)
        
        # Mock status message
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        # Mock STT
        mock_stt_result = MagicMock()
        mock_stt_result.transcript = "Test transcription"
        mock_stt_client = MagicMock()
        mock_stt_client.recognize = AsyncMock(return_value=mock_stt_result)
        
        with patch('grpc.aio.insecure_channel') as mock_channel, \
             patch('june_grpc_api.asr.SpeechToTextClient', return_value=mock_stt_client), \
             patch('handlers.voice.enhance_audio_for_stt', return_value=b'mock_prepared_audio') as mock_enhance, \
             patch('handlers.voice.prepare_audio_for_stt', return_value=b'mock_prepared_audio') as mock_prepare, \
             patch('june_grpc_api.shim.llm.LLMClient') as mock_llm_client_class, \
             patch('june_grpc_api.shim.tts.TextToSpeechClient') as mock_tts_client_class, \
             patch('handlers.voice.AudioSegment') as mock_audio_segment, \
             patch('handlers.voice.export_audio_to_ogg_optimized') as mock_export_ogg, \
             patch('handlers.voice.find_optimal_compression') as mock_find_compression:
            
            mock_channel.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_channel.return_value.__aexit__ = AsyncMock(return_value=False)
            
            # Mock OGG export functions
            mock_find_compression.return_value = ('medium', {'bitrate': 64})
            mock_export_ogg.return_value = {
                'compressed_size': 1000,
                'compression_ratio': 1.5,
                'preset': 'medium'
            }
            
            # Mock LLM and TTS
            mock_llm_client = MagicMock()
            mock_llm_client.chat = AsyncMock(return_value="Mock LLM response")
            mock_llm_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_llm_client)
            mock_llm_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            
            mock_tts_client = MagicMock()
            mock_tts_client.synthesize = AsyncMock(return_value=b'mock_tts_audio')
            mock_tts_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_tts_client)
            mock_tts_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            
            mock_audio = MagicMock()
            def mock_export(path, format='ogg', **kwargs):
                with open(path, 'wb') as f:
                    f.write(b'mock_ogg_audio_data')
            mock_audio.export = MagicMock(side_effect=mock_export)
            mock_audio.channels = 1
            mock_audio.frame_rate = 16000
            mock_audio.duration_seconds = 1.0
            mock_audio.frame_width = 2
            mock_audio_segment.from_wav.return_value = mock_audio
            mock_audio_segment.from_file.return_value = mock_audio
            
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"messages": []}
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.post.return_value = mock_response
            mock_httpx_module = sys.modules['httpx']
            mock_httpx_module.AsyncClient = MagicMock()
            mock_httpx_module.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx_module.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
            
            with patch('handlers.voice.tempfile.NamedTemporaryFile') as mock_tempfile, \
                 patch('handlers.voice.os.unlink') as mock_unlink, \
                 patch('builtins.open', create=True):
                mock_tempfile.return_value.__enter__ = lambda self: self
                mock_tempfile.return_value.__exit__ = lambda *args: None
                mock_tempfile.return_value.name = '/tmp/test.ogg'
                mock_update.message.reply_voice = AsyncMock()
                
                await handle_voice_message(mock_update, mock_context, mock_config, "stt:50052", mock_get_metrics_storage)
                
                # Verify audio was enhanced (the handler now uses enhance_audio_for_stt)
                # The actual conversion happens in enhance_audio_for_stt
                # We verify that enhance_audio_for_stt was called
                mock_enhance.assert_called_once()
                assert mock_update.message.reply_text.call_count >= 1


class TestServiceRun:
    """Tests for service run methods."""
    
    @pytest.fixture
    def service(self):
        """Create a TelegramBotService instance for testing."""
        with patch('main.config') as mock_config, \
             patch('main.Application') as mock_app_class, \
             patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test-token'}):
            mock_config.telegram.bot_token = "test-token"
            mock_config.telegram.max_file_size = 20 * 1024 * 1024
            mock_config.monitoring.log_level = "INFO"
            mock_app = MagicMock()
            mock_app.run_polling = MagicMock()
            mock_app.run_webhook = MagicMock()
            mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
            
            service = TelegramBotService()
            service.application = mock_app
            return service
    
    def test_run_polling_mode(self, service):
        """Test running bot in polling mode."""
        with patch.dict(os.environ, {'TELEGRAM_USE_WEBHOOK': 'false'}):
            # Note: This would block, so we just verify the method call
            # In a real test, you might want to run this in a separate thread/process
            service.application.run_polling = MagicMock()
            service.run(use_webhook=False)
            service.application.run_polling.assert_called_once()
    
    @patch.dict(os.environ, {'TELEGRAM_WEBHOOK_PORT': '8443'})
    def test_run_webhook_mode(self, service):
        """Test running bot in webhook mode."""
        service.application.run_webhook = MagicMock()
        service.run(use_webhook=True, webhook_url="https://example.com/webhook")
        service.application.run_webhook.assert_called_once()
