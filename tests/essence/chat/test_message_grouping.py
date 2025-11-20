"""
Unit tests for message grouping functionality.
"""
import pytest

from essence.chat.message_grouping import (
    DEFAULT_MAX_GROUP_LENGTH,
    DEFAULT_MAX_MESSAGES_PER_GROUP,
    DEFAULT_TIME_WINDOW_SECONDS,
    GroupedMessage,
    format_grouped_message,
    group_messages,
    should_group_messages,
    split_if_too_long,
)


class TestShouldGroupMessages:
    """Tests for should_group_messages function."""

    def test_should_group_single_message(self):
        """Test that single message should not be grouped."""
        assert should_group_messages(["Single message"]) is False

    def test_should_group_two_short_messages(self):
        """Test that two short messages should be grouped."""
        messages = ["Message 1", "Message 2"]
        assert should_group_messages(messages) is True

    def test_should_group_too_many_messages(self):
        """Test that too many messages should not be grouped."""
        messages = ["Message"] * (DEFAULT_MAX_MESSAGES_PER_GROUP + 1)
        assert should_group_messages(messages) is False

    def test_should_group_too_long_messages(self):
        """Test that messages exceeding max length should not be grouped."""
        long_message = "X" * (DEFAULT_MAX_GROUP_LENGTH + 1)
        messages = ["Message 1", long_message]
        assert should_group_messages(messages) is False

    def test_should_group_custom_parameters(self):
        """Test should_group_messages with custom parameters."""
        messages = ["Message 1", "Message 2"]
        # With very small max_messages, should not group
        assert should_group_messages(messages, max_messages=1) is False
        # With larger max_messages, should group
        assert should_group_messages(messages, max_messages=5) is True


class TestGroupMessages:
    """Tests for group_messages function."""

    def test_group_messages_single(self):
        """Test grouping a single message."""
        result = group_messages(["Single message"])
        assert result.can_group is False
        assert len(result.messages) == 1
        assert result.messages[0] == "Single message"

    def test_group_messages_multiple(self):
        """Test grouping multiple messages."""
        messages = ["Message 1", "Message 2", "Message 3"]
        result = group_messages(messages)
        assert result.can_group is True
        # When grouped, messages are combined into a single formatted string
        assert len(result.messages) == 1
        assert result.total_length > 0
        # The grouped message should contain all original messages
        grouped_text = result.messages[0]
        assert "Message 1" in grouped_text
        assert "Message 2" in grouped_text
        assert "Message 3" in grouped_text

    def test_group_messages_with_types(self):
        """Test grouping messages with types."""
        messages = ["Message 1", "Message 2"]
        message_types = ["text", "code"]
        result = group_messages(messages, message_types=message_types)
        assert result.can_group is True
        # When grouped, message_types becomes ["grouped"]
        assert len(result.message_types) == 1
        assert result.message_types[0] == "grouped"
        # But the grouped text should contain type information
        grouped_text = result.messages[0]
        assert "text" in grouped_text.lower() or "code" in grouped_text.lower()

    def test_group_messages_too_many(self):
        """Test grouping when there are too many messages."""
        messages = ["Message"] * (DEFAULT_MAX_MESSAGES_PER_GROUP + 5)
        result = group_messages(messages)
        # Should still group up to max, or return can_group=False
        assert isinstance(result, GroupedMessage)


class TestFormatGroupedMessage:
    """Tests for format_grouped_message function."""

    def test_format_grouped_message_telegram(self):
        """Test formatting grouped message for Telegram."""
        messages = ["Message 1", "Message 2"]
        formatted = format_grouped_message(messages, platform="telegram")
        assert "Message 1" in formatted
        assert "Message 2" in formatted
        # Telegram uses HTML formatting
        assert "<b>" in formatted or "**" in formatted or formatted.count("\n") > 0

    def test_format_grouped_message_discord(self):
        """Test formatting grouped message for Discord."""
        messages = ["Message 1", "Message 2"]
        formatted = format_grouped_message(messages, platform="discord")
        assert "Message 1" in formatted
        assert "Message 2" in formatted
        # Discord uses Markdown formatting

    def test_format_grouped_message_with_types(self):
        """Test formatting grouped message with message types."""
        messages = ["Text message", "Code: print('hello')"]
        message_types = ["text", "code"]
        formatted = format_grouped_message(messages, message_types=message_types, platform="telegram")
        assert "Text message" in formatted
        assert "Code:" in formatted or "print" in formatted


class TestSplitIfTooLong:
    """Tests for split_if_too_long function."""

    def test_split_if_too_long_short_message(self):
        """Test that short message is not split."""
        message = "Short message"
        result = split_if_too_long(message, max_length=1000)
        assert len(result) == 1
        assert result[0] == message

    def test_split_if_too_long_long_message(self):
        """Test that long message is split."""
        long_message = "X" * 5000
        result = split_if_too_long(long_message, max_length=1000)
        assert len(result) > 1
        # Each chunk should be <= max_length
        for chunk in result:
            assert len(chunk) <= 1000

    def test_split_if_too_long_with_paragraphs(self):
        """Test splitting message with paragraphs."""
        message = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        result = split_if_too_long(message, max_length=20)
        # Should split by paragraphs when possible
        assert len(result) >= 1

    def test_split_if_too_long_telegram(self):
        """Test splitting for Telegram platform."""
        long_message = "X" * 5000
        result = split_if_too_long(long_message, max_length=1000, platform="telegram")
        assert len(result) > 1

    def test_split_if_too_long_discord(self):
        """Test splitting for Discord platform."""
        long_message = "X" * 5000
        result = split_if_too_long(long_message, max_length=1000, platform="discord")
        assert len(result) > 1
