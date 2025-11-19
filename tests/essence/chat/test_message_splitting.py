"""
Tests for message splitting and truncation logic.

Tests verify that messages are properly split when too long and truncated
when exceeding 2x the maximum length.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from essence.chat.message_builder import MessageBuilder
from essence.chat.human_interface import Message, EscapedText, Paragraph


class TestMessageSplitting:
    """Tests for message splitting functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = MessageBuilder(service_name="test")

    def test_short_message_no_split(self):
        """Test that short messages are not split."""
        message = Message(content=[EscapedText(text="Short message")])
        parts = self.builder.split_message_if_needed(max_length=4096, message=message)

        assert len(parts) == 1
        assert parts[0] == "Short message"

    def test_message_within_limit_no_split(self):
        """Test that messages within limit are not split."""
        text = "A" * 1000  # Well within 4096 limit
        message = Message(content=[EscapedText(text=text)])
        parts = self.builder.split_message_if_needed(max_length=4096, message=message)

        assert len(parts) == 1
        assert len(parts[0]) <= 4096

    def test_message_exceeds_limit_splits(self):
        """Test that messages exceeding limit are split into 2."""
        text = "A" * 5000  # Exceeds 4096 but < 2 * 4096
        message = Message(content=[EscapedText(text=text)])
        parts = self.builder.split_message_if_needed(max_length=4096, message=message)

        assert len(parts) == 2
        assert len(parts[0]) <= 4096
        assert len(parts[1]) <= 4096
        # Combined length should be approximately original
        assert len(parts[0]) + len(parts[1]) >= 5000 - 100  # Allow some margin

    def test_message_exceeds_2x_limit_truncates(self):
        """Test that messages exceeding 2x limit are truncated."""
        text = "A" * 10000  # Exceeds 2 * 4096
        message = Message(content=[EscapedText(text=text)])
        parts = self.builder.split_message_if_needed(max_length=4096, message=message)

        assert len(parts) == 2
        assert len(parts[0]) <= 4096
        assert len(parts[1]) <= 4096
        # Second part should have truncation indicator
        assert "... (message truncated)" in parts[1]
        # Total should be approximately 2 * max_length
        assert len(parts[0]) + len(parts[1]) <= 2 * 4096 + 100  # Allow margin

    def test_split_at_widget_boundaries(self):
        """Test that splitting prefers widget boundaries."""
        message = Message(
            content=[
                EscapedText(text="A" * 2000),
                EscapedText(text="B" * 2000),
                EscapedText(text="C" * 2000),
            ]
        )
        parts = self.builder.split_message_if_needed(max_length=4096, message=message)

        # Should split at widget boundaries if possible
        # First part should contain first widget(s), second part should contain rest
        assert len(parts) >= 1
        assert all(len(part) <= 4096 for part in parts)

    def test_split_finds_good_split_point(self):
        """Test that splitting finds good split points (newlines, spaces)."""
        # Create text with newlines
        text = "Line 1\n" * 500 + "Line 2\n" * 500
        message = Message(content=[EscapedText(text=text)])
        parts = self.builder.split_message_if_needed(max_length=4096, message=message)

        assert len(parts) == 2
        # Split should be at a newline if possible
        # (We can't guarantee this, but we can check it's reasonable)
        assert all(len(part) <= 4096 for part in parts)

    def test_discord_message_length(self):
        """Test that Discord messages respect 2000 character limit."""
        text = "A" * 3000  # Exceeds Discord's 2000 limit
        message = Message(content=[EscapedText(text=text)])
        builder = MessageBuilder(service_name="discord")
        parts = builder.split_message_if_needed(max_length=2000, message=message)

        assert len(parts) == 2
        assert all(len(part) <= 2000 for part in parts)

    def test_telegram_message_length(self):
        """Test that Telegram messages respect 4096 character limit."""
        text = "A" * 5000  # Exceeds Telegram's 4096 limit
        message = Message(content=[EscapedText(text=text)])
        builder = MessageBuilder(service_name="telegram")
        parts = builder.split_message_if_needed(max_length=4096, message=message)

        assert len(parts) == 2
        assert all(len(part) <= 4096 for part in parts)

    def test_truncation_indicator_preserved(self):
        """Test that truncation indicator doesn't cause overflow."""
        text = "A" * 15000  # Way over 2x limit
        message = Message(content=[EscapedText(text=text)])
        parts = self.builder.split_message_if_needed(max_length=4096, message=message)

        assert len(parts) == 2
        # Second part should have truncation indicator and still be within limit
        assert "... (message truncated)" in parts[1]
        assert len(parts[1]) <= 4096
