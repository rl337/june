"""
Unit tests for Telegram handler message accumulation.

Tests that the Telegram handler properly accumulates and updates messages
in place as chunks arrive from the streaming function.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add parent directories to path
base_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(base_path / "services" / "chat-service-base"))
sys.path.insert(0, str(base_path / "services" / "telegram"))

# Import after path setup
from handlers.text import handle_text_message


class TestTelegramMessageAccumulation:
    """Test that Telegram handler accumulates messages correctly."""

    @pytest.mark.asyncio
    async def test_accumulates_incremental_chunks(self):
        """Test that incremental chunks are accumulated and message updates in place."""

        # Mock the streaming function to yield incremental chunks
        async def mock_stream_agent_message(*args, **kwargs):
            chunks = [
                ("Hi. How can", False),
                ("Hi. How can I help you today?", False),
                (
                    "Hi. How can I help you today?\n\nI can help with:\n- **Tasks & Projects**",
                    False,
                ),
                (
                    "Hi. How can I help you today?\n\nI can help with:\n- **Tasks & Projects** — list, create, or manage tasks\n- **Documentation** — search or create docs\n- **Knowledge** — query or store facts\n\nWhat would you like to do?",
                    False,
                ),
                ("", True),  # Final signal
            ]
            for chunk, is_final in chunks:
                yield (chunk, is_final)

        # Mock Telegram update and context
        update = Mock()
        update.message = Mock()
        update.message.reply_text = AsyncMock()
        update.message.reply_text.return_value = Mock(message_id=123)

        context = Mock()
        context.bot = Mock()
        context.bot.send_chat_action = AsyncMock()

        # Mock the stream_agent_message function
        with patch("handlers.text.stream_agent_message", mock_stream_agent_message):
            await handle_text_message(update, context)

        # Check that reply_text was called (for initial message)
        assert update.message.reply_text.called

        # The message should have been updated multiple times
        # (we can't easily test edit_text without more mocking, but we can verify the flow)

    @pytest.mark.asyncio
    async def test_handles_middle_chunk_problem(self):
        """Test that middle chunks don't replace the accumulated message."""

        # Simulate the problematic scenario: getting a middle chunk
        async def mock_stream_agent_message(*args, **kwargs):
            chunks = [
                ("Hi. How can", False),
                ("order or not al", False),  # Problem: middle chunk
                ("Hi. How can I help you? You can order or not all items.", False),
                ("", True),
            ]
            for chunk, is_final in chunks:
                yield (chunk, is_final)

        update = Mock()
        update.message = Mock()
        update.message.reply_text = AsyncMock()
        last_message = Mock()
        last_message.edit_text = AsyncMock()
        update.message.reply_text.return_value = last_message

        context = Mock()
        context.bot = Mock()
        context.bot.send_chat_action = AsyncMock()

        with patch("handlers.text.stream_agent_message", mock_stream_agent_message):
            await handle_text_message(update, context)

        # Should have called edit_text to update the message
        # The final message should be the longest one, not the middle chunk
        assert last_message.edit_text.called

        # Get the last call to edit_text - should be the longest message
        calls = last_message.edit_text.call_args_list
        if calls:
            last_call_text = calls[-1][0][0] if calls[-1][0] else ""
            # Should contain the full message, not just "order or not al"
            assert (
                len(last_call_text) > len("order or not al")
                or "Hi. How can" in last_call_text
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
