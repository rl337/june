"""
Tests for Telegram streaming utilities.
"""
import pytest
import asyncio
import sys
import importlib
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Fix import conflict: ensure we import from installed python-telegram-bot, not local telegram dir
# Strategy: Remove local telegram from module cache, import from installed package
import importlib
import site
import os.path

# Find site-packages directory with telegram
_site_packages = None
for sp_dir in list(site.getsitepackages()) + [site.getusersitepackages()]:
    if sp_dir and 'site-packages' in sp_dir:
        _telegram_pkg_path = os.path.join(sp_dir, 'telegram', '__init__.py')
        if os.path.exists(_telegram_pkg_path):
            _site_packages = sp_dir
            break

# Find local services/telegram directory
_local_telegram_dir = None
_current_dir = os.path.dirname(os.path.abspath(__file__))  # tests/ directory
_parent_dir = os.path.dirname(_current_dir)  # services/telegram/ directory
if os.path.basename(_parent_dir) == 'telegram':
    _local_telegram_dir = _parent_dir

# Clear local telegram from module cache if it was imported
if 'telegram' in sys.modules:
    mod = sys.modules['telegram']
    if hasattr(mod, '__file__') and mod.__file__:
        if _local_telegram_dir and _local_telegram_dir in mod.__file__:
            del sys.modules['telegram']
            if 'telegram.ext' in sys.modules:
                del sys.modules['telegram.ext']
            if 'telegram.error' in sys.modules:
                del sys.modules['telegram.error']

# Temporarily move site-packages to front of sys.path for telegram import
_original_sys_path = sys.path[:]
_test_dir = os.path.dirname(os.path.abspath(__file__))
if _test_dir in sys.path:
    sys.path.remove(_test_dir)
if _site_packages and _site_packages in sys.path:
    sys.path.remove(_site_packages)
if _site_packages:
    sys.path.insert(0, _site_packages)

# Now import telegram from installed package
from telegram import Message
from telegram.error import TelegramError, TimedOut

# Restore original sys.path
sys.path[:] = _original_sys_path
if _local_telegram_dir and _local_telegram_dir not in sys.path:
    sys.path.insert(0, _local_telegram_dir)

from essence.services.telegram.telegram_utils import stream_text_message, stream_llm_response_to_telegram, TELEGRAM_MAX_MESSAGE_LENGTH


@pytest.fixture
def mock_message():
    """Create a mock Telegram message."""
    message = MagicMock(spec=Message)
    message.edit_text = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_stream_text_message_basic(mock_message):
    """Test basic text streaming."""
    text = "Hello, world!"
    result = await stream_text_message(mock_message, text)
    
    assert result is True
    # Should have called edit_text with the complete text
    mock_message.edit_text.assert_called()
    # Last call should have the complete text
    final_call = mock_message.edit_text.call_args_list[-1]
    assert final_call[0][0] == text


@pytest.mark.asyncio
async def test_stream_text_message_long(mock_message):
    """Test streaming with long text."""
    text = "A" * 1000
    result = await stream_text_message(mock_message, text, chunk_size=10)
    
    assert result is True
    # Should have called edit_text multiple times
    assert mock_message.edit_text.call_count > 1
    # Final call should have complete text
    final_call = mock_message.edit_text.call_args_list[-1]
    assert final_call[0][0] == text


@pytest.mark.asyncio
async def test_stream_text_message_truncate(mock_message):
    """Test that text is truncated if exceeds Telegram limit."""
    text = "A" * (TELEGRAM_MAX_MESSAGE_LENGTH + 100)
    result = await stream_text_message(mock_message, text)
    
    assert result is True
    # Final call should have truncated text
    final_call = mock_message.edit_text.call_args_list[-1]
    final_text = final_call[0][0]
    assert len(final_text) <= TELEGRAM_MAX_MESSAGE_LENGTH
    assert final_text.endswith("...")


@pytest.mark.asyncio
async def test_stream_text_message_timeout(mock_message):
    """Test handling of Telegram timeout errors."""
    # Make edit_text raise TimedOut error on first call, then succeed
    mock_message.edit_text.side_effect = [
        TimedOut("Timeout"),
        AsyncMock(),
        AsyncMock()
    ]
    
    text = "Test message"
    result = await stream_text_message(mock_message, text)
    
    # Should continue despite timeout
    assert result is True
    assert mock_message.edit_text.call_count >= 2


@pytest.mark.asyncio
async def test_stream_text_message_cancelled(mock_message):
    """Test handling of cancellation."""
    # Make edit_text raise CancelledError
    async def cancel_after_first(*args, **kwargs):
        if mock_message.edit_text.call_count == 1:
            raise asyncio.CancelledError()
        return AsyncMock()
    
    mock_message.edit_text.side_effect = cancel_after_first
    
    text = "Test message that will be cancelled"
    result = await stream_text_message(mock_message, text)
    
    # Should return False on cancellation
    assert result is False


@pytest.mark.asyncio
async def test_stream_llm_response_to_telegram(mock_message):
    """Test streaming LLM response."""
    # Create async generator for LLM stream
    async def llm_stream():
        chunks = ["Hello", ", ", "world", "!"]
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0.01)
    
    response_text, success = await stream_llm_response_to_telegram(
        mock_message,
        llm_stream(),
        prefix="💬 **Response:**\n\n"
    )
    
    assert success is True
    assert response_text == "Hello, world!"
    # Should have called edit_text multiple times
    assert mock_message.edit_text.call_count >= 1
    # Final call should have complete text with prefix
    final_call = mock_message.edit_text.call_args_list[-1]
    assert "Hello, world!" in final_call[0][0]
    assert "💬 **Response:**" in final_call[0][0]


@pytest.mark.asyncio
async def test_stream_llm_response_to_telegram_long(mock_message):
    """Test streaming long LLM response."""
    # Create async generator with long text
    long_text = "A" * 5000
    async def llm_stream():
        chunk_size = 100
        for i in range(0, len(long_text), chunk_size):
            yield long_text[i:i + chunk_size]
            await asyncio.sleep(0.01)
    
    response_text, success = await stream_llm_response_to_telegram(
        mock_message,
        llm_stream(),
        prefix="💬 **Response:**\n\n"
    )
    
    assert success is True
    # Text should be truncated
    assert len(response_text) <= TELEGRAM_MAX_MESSAGE_LENGTH - len("💬 **Response:**\n\n") - 3
    # Final call should have truncated text
    final_call = mock_message.edit_text.call_args_list[-1]
    final_text = final_call[0][0]
    assert len(final_text) <= TELEGRAM_MAX_MESSAGE_LENGTH


@pytest.mark.asyncio
async def test_stream_llm_response_to_telegram_empty(mock_message):
    """Test streaming empty LLM response."""
    async def llm_stream():
        # Empty stream
        if False:
            yield ""
    
    response_text, success = await stream_llm_response_to_telegram(
        mock_message,
        llm_stream(),
        prefix="💬 **Response:**\n\n"
    )
    
    assert success is True
    assert response_text == ""


@pytest.mark.asyncio
async def test_stream_llm_response_to_telegram_error(mock_message):
    """Test handling of errors during streaming."""
    # Make edit_text raise error
    mock_message.edit_text.side_effect = TelegramError("Test error")
    
    async def llm_stream():
        yield "Test"
        await asyncio.sleep(0.01)
        yield " message"
    
    response_text, success = await stream_llm_response_to_telegram(
        mock_message,
        llm_stream(),
        prefix="💬 **Response:**\n\n"
    )
    
    # Should still accumulate text despite errors
    assert "Test" in response_text or "message" in response_text
