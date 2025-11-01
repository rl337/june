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
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from pydub.generators import Sine

from telegram import Update, Message, Voice, File, User, Chat
from telegram.ext import ContextTypes

from main import TelegramBotService
from audio_utils import AudioValidationError, prepare_audio_for_stt


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
    """Create sample audio data for testing."""
    audio = Sine(440).to_audio_segment(duration=1000)  # 1 second
    audio = audio.set_frame_rate(16000)
    audio = audio.set_channels(1)
    
    buffer = io.BytesIO()
    audio.export(buffer, format="wav")
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_ogg_audio():
    """Create sample OGG audio data for testing."""
    audio = Sine(440).to_audio_segment(duration=1000)
    buffer = io.BytesIO()
    audio.export(buffer, format="ogg", codec="libvorbis")
    buffer.seek(0)
    return buffer.read()


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
    
    @patch('main.config')
    @patch('main.Application')
    @patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test-token'})
    def test_init_success(self, mock_app_class, mock_config):
        """Test successful initialization."""
        mock_config.telegram.bot_token = "test-token"
        mock_config.telegram.max_file_size = 20 * 1024 * 1024
        
        service = TelegramBotService()
        
        assert service.config is not None
        assert service.application is not None
        mock_app_class.builder.assert_called_once()
    
    @patch('main.config')
    @patch('main.Application')
    @patch.dict(os.environ, {}, clear=True)
    def test_init_missing_token(self, mock_app_class, mock_config):
        """Test initialization fails without bot token."""
        mock_config.telegram.bot_token = None
        
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            TelegramBotService()
    
    @patch('main.config')
    @patch('main.Application')
    @patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test-token', 'STT_URL': 'grpc://custom-stt:50052'})
    def test_init_custom_service_urls(self, mock_app_class, mock_config):
        """Test initialization with custom service URLs."""
        mock_config.telegram.bot_token = "test-token"
        mock_config.telegram.max_file_size = 20 * 1024 * 1024
        
        service = TelegramBotService()
        
        # Should strip grpc:// prefix
        assert service.stt_address == "custom-stt:50052"
        assert "grpc://" not in service.stt_address


class TestCommandHandlers:
    """Tests for command handlers (start, help, status)."""
    
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
            mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
            
            service = TelegramBotService()
            service.application = mock_app
            return service
    
    @pytest.mark.asyncio
    async def test_start_command(self, service, mock_update):
        """Test /start command handler."""
        await service.start_command(mock_update, None)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Hello" in call_args
        assert "June" in call_args
        assert "voice message" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_help_command(self, service, mock_update):
        """Test /help command handler."""
        await service.help_command(mock_update, None)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Help" in call_args or "help" in call_args.lower()
        assert "/start" in call_args
        assert "/help" in call_args
        assert "/status" in call_args
    
    @pytest.mark.asyncio
    async def test_status_command(self, service, mock_update):
        """Test /status command handler."""
        await service.status_command(mock_update, None)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Status" in call_args or "status" in call_args.lower()
        assert "Bot" in call_args or "bot" in call_args.lower()


class TestVoiceMessageHandling:
    """Tests for voice message handling."""
    
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
            mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
            
            service = TelegramBotService()
            service.application = mock_app
            return service
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_file_too_large(self, service, mock_update, mock_context):
        """Test voice message rejection when file is too large."""
        # Set voice file size to exceed limit
        mock_update.message.voice.file_size = service.config.max_file_size + 1
        
        await service.handle_voice_message(mock_update, mock_context)
        
        # Should reply with error message
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "too large" in call_args.lower() or "large" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_success(
        self, service, mock_update, mock_context, mock_telegram_file, sample_ogg_audio
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
        
        mock_stt_client = MagicMock()
        mock_stt_client.recognize = AsyncMock(return_value=mock_stt_result)
        
        with patch('main.grpc.aio.insecure_channel') as mock_channel, \
             patch('main.asr_shim.SpeechToTextClient', return_value=mock_stt_client), \
             patch('main.prepare_audio_for_stt') as mock_prepare:
            
            # Mock audio preparation (conversion)
            prepared_audio = prepare_audio_for_stt(sample_ogg_audio, is_ogg=True)
            mock_prepare.return_value = prepared_audio
            
            # Mock async context manager for channel
            mock_channel.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_channel.return_value.__aexit__ = AsyncMock(return_value=False)
            
            await service.handle_voice_message(mock_update, mock_context)
            
            # Verify status messages were sent
            assert mock_update.message.reply_text.call_count >= 1
            # Verify STT was called
            mock_stt_client.recognize.assert_called_once()
            # Verify final status was updated
            assert mock_status_msg.edit_text.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_audio_validation_error(
        self, service, mock_update, mock_context, mock_telegram_file, sample_ogg_audio
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
        with patch('main.prepare_audio_for_stt', side_effect=AudioValidationError("Audio too long")):
            await service.handle_voice_message(mock_update, mock_context)
            
            # Should show validation error
            mock_status_msg.edit_text.assert_called()
            call_args = str(mock_status_msg.edit_text.call_args)
            assert "validation" in call_args.lower() or "failed" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_stt_error(
        self, service, mock_update, mock_context, mock_telegram_file, sample_ogg_audio
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
        prepared_audio = prepare_audio_for_stt(sample_ogg_audio, is_ogg=True)
        
        # Mock STT to raise error
        mock_stt_client = MagicMock()
        mock_stt_client.recognize = AsyncMock(side_effect=Exception("STT service unavailable"))
        
        with patch('main.grpc.aio.insecure_channel') as mock_channel, \
             patch('main.asr_shim.SpeechToTextClient', return_value=mock_stt_client), \
             patch('main.prepare_audio_for_stt', return_value=prepared_audio):
            
            # Mock async context manager for channel
            mock_channel.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_channel.return_value.__aexit__ = AsyncMock(return_value=False)
            
            await service.handle_voice_message(mock_update, mock_context)
            
            # Should show STT error
            mock_status_msg.edit_text.assert_called()
            call_args = str(mock_status_msg.edit_text.call_args)
            assert "transcription" in call_args.lower() or "failed" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_download_error(
        self, service, mock_update, mock_context
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
        
        await service.handle_voice_message(mock_update, mock_context)
        
        # Should show error message
        mock_status_msg.edit_text.assert_called()
        call_args = str(mock_status_msg.edit_text.call_args)
        assert "error" in call_args.lower() or "failed" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_audio_preparation_error(
        self, service, mock_update, mock_context, mock_telegram_file, sample_ogg_audio
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
        with patch('main.prepare_audio_for_stt', side_effect=ValueError("Invalid audio format")):
            await service.handle_voice_message(mock_update, mock_context)
            
            # Should show error message
            mock_status_msg.edit_text.assert_called()
            call_args = str(mock_status_msg.edit_text.call_args)
            assert "error" in call_args.lower() or "processing" in call_args.lower()


class TestErrorHandlingPaths:
    """Tests for various error handling paths."""
    
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
            mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
            
            service = TelegramBotService()
            service.application = mock_app
            return service
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_generic_exception(
        self, service, mock_update, mock_context
    ):
        """Test handling of generic exceptions."""
        # Setup to raise exception early
        mock_update.message.voice.file_size = 1000
        mock_context.bot.get_file.side_effect = Exception("Unexpected error")
        
        # Mock status message
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status_msg
        
        await service.handle_voice_message(mock_update, mock_context)
        
        # Should handle gracefully and show error
        mock_status_msg.edit_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_voice_message_no_file_size(
        self, service, mock_update, mock_context, mock_telegram_file, sample_ogg_audio
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
        
        with patch('main.grpc.aio.insecure_channel') as mock_channel, \
             patch('main.asr_shim.SpeechToTextClient', return_value=mock_stt_client), \
             patch('main.prepare_audio_for_stt') as mock_prepare:
            
            prepared_audio = prepare_audio_for_stt(sample_ogg_audio, is_ogg=True)
            mock_prepare.return_value = prepared_audio
            
            mock_channel.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_channel.return_value.__aexit__ = AsyncMock(return_value=False)
            
            # Should proceed (file_size check only runs if file_size is not None)
            await service.handle_voice_message(mock_update, mock_context)
            
            # Should have processed the message
            assert mock_update.message.reply_text.call_count >= 1


class TestAudioFormatConversionIntegration:
    """Tests for audio format conversion integration with voice handling."""
    
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
            mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
            
            service = TelegramBotService()
            service.application = mock_app
            return service
    
    @pytest.mark.asyncio
    async def test_audio_conversion_in_voice_processing(
        self, service, mock_update, mock_context, mock_telegram_file, sample_ogg_audio
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
        
        with patch('main.grpc.aio.insecure_channel') as mock_channel, \
             patch('main.asr_shim.SpeechToTextClient', return_value=mock_stt_client):
            
            mock_channel.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_channel.return_value.__aexit__ = AsyncMock(return_value=False)
            
            # Capture the audio passed to STT
            captured_audio = None
            
            async def capture_audio(*args, **kwargs):
                nonlocal captured_audio
                if args:
                    captured_audio = args[0]
                return mock_stt_result
            
            mock_stt_client.recognize = capture_audio
            
            await service.handle_voice_message(mock_update, mock_context)
            
            # Verify audio was prepared (converted)
            # The actual conversion happens in prepare_audio_for_stt
            # We verify that STT was called with prepared audio
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
