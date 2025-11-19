"""
Unit tests for message history storage.
"""
import pytest
from datetime import datetime
from essence.chat.message_history import (
    MessageHistory,
    MessageHistoryEntry,
    get_message_history,
    reset_message_history
)


class TestMessageHistoryEntry:
    """Tests for MessageHistoryEntry dataclass."""
    
    def test_create_entry(self):
        """Test creating a message history entry."""
        entry = MessageHistoryEntry(
            timestamp=datetime.now(),
            platform="telegram",
            user_id="12345",
            chat_id="67890",
            message_content="Hello, world!",
            message_type="text"
        )
        
        assert entry.platform == "telegram"
        assert entry.user_id == "12345"
        assert entry.chat_id == "67890"
        assert entry.message_content == "Hello, world!"
        assert entry.message_type == "text"
        assert entry.message_id is None
        assert entry.rendering_metadata == {}


class TestMessageHistory:
    """Tests for MessageHistory storage."""
    
    def setup_method(self):
        """Reset message history before each test."""
        reset_message_history()
    
    def test_add_message(self):
        """Test adding a message to history."""
        history = MessageHistory()
        
        history.add_message(
            platform="telegram",
            user_id="12345",
            chat_id="67890",
            message_content="Hello!",
            message_type="text"
        )
        
        assert len(history._messages) == 1
        assert history._by_user["12345"] == [0]
        assert history._by_chat["67890"] == [0]
    
    def test_get_messages_by_user(self):
        """Test retrieving messages by user ID."""
        history = MessageHistory()
        
        history.add_message("telegram", "12345", "67890", "Message 1", "text")
        history.add_message("telegram", "12345", "67890", "Message 2", "text")
        history.add_message("discord", "99999", "88888", "Message 3", "text")
        
        messages = history.get_messages(user_id="12345")
        
        assert len(messages) == 2
        assert messages[0].message_content == "Message 2"  # Newest first
        assert messages[1].message_content == "Message 1"
    
    def test_get_messages_by_chat(self):
        """Test retrieving messages by chat ID."""
        history = MessageHistory()
        
        history.add_message("telegram", "12345", "67890", "Message 1", "text")
        history.add_message("telegram", "99999", "67890", "Message 2", "text")
        history.add_message("discord", "12345", "88888", "Message 3", "text")
        
        messages = history.get_messages(chat_id="67890")
        
        assert len(messages) == 2
        assert messages[0].message_content == "Message 2"  # Newest first
        assert messages[1].message_content == "Message 1"
    
    def test_get_messages_by_platform(self):
        """Test filtering by platform."""
        history = MessageHistory()
        
        history.add_message("telegram", "12345", "67890", "Telegram message", "text")
        history.add_message("discord", "12345", "88888", "Discord message", "text")
        
        telegram_messages = history.get_messages(platform="telegram")
        discord_messages = history.get_messages(platform="discord")
        
        assert len(telegram_messages) == 1
        assert telegram_messages[0].message_content == "Telegram message"
        
        assert len(discord_messages) == 1
        assert discord_messages[0].message_content == "Discord message"
    
    def test_get_messages_by_type(self):
        """Test filtering by message type."""
        history = MessageHistory()
        
        history.add_message("telegram", "12345", "67890", "Text message", "text")
        history.add_message("telegram", "12345", "67890", "Error message", "error")
        history.add_message("telegram", "12345", "67890", "Status message", "status")
        
        text_messages = history.get_messages(message_type="text")
        error_messages = history.get_messages(message_type="error")
        
        assert len(text_messages) == 1
        assert text_messages[0].message_content == "Text message"
        
        assert len(error_messages) == 1
        assert error_messages[0].message_content == "Error message"
    
    def test_get_messages_with_limit(self):
        """Test limiting results."""
        history = MessageHistory()
        
        for i in range(10):
            history.add_message("telegram", "12345", "67890", f"Message {i}", "text")
        
        messages = history.get_messages(user_id="12345", limit=5)
        
        assert len(messages) == 5
        assert messages[0].message_content == "Message 9"  # Newest first
    
    def test_evict_oldest(self):
        """Test evicting oldest entries when over limit."""
        history = MessageHistory(max_entries=3)
        
        history.add_message("telegram", "12345", "67890", "Message 1", "text")
        history.add_message("telegram", "12345", "67890", "Message 2", "text")
        history.add_message("telegram", "12345", "67890", "Message 3", "text")
        history.add_message("telegram", "12345", "67890", "Message 4", "text")  # Should evict Message 1
        
        assert len(history._messages) == 3
        assert history._messages[0].message_content == "Message 2"  # Oldest remaining
        assert history._messages[-1].message_content == "Message 4"  # Newest
    
    def test_clear(self):
        """Test clearing all messages."""
        history = MessageHistory()
        
        history.add_message("telegram", "12345", "67890", "Message 1", "text")
        history.add_message("discord", "99999", "88888", "Message 2", "text")
        
        history.clear()
        
        assert len(history._messages) == 0
        assert len(history._by_user) == 0
        assert len(history._by_chat) == 0
    
    def test_get_stats(self):
        """Test getting statistics."""
        history = MessageHistory()
        
        history.add_message("telegram", "12345", "67890", "Text 1", "text")
        history.add_message("telegram", "12345", "67890", "Text 2", "text")
        history.add_message("discord", "99999", "88888", "Error", "error")
        history.add_message("telegram", "11111", "22222", "Status", "status")
        
        stats = history.get_stats()
        
        assert stats["total_messages"] == 4
        assert stats["by_platform"]["telegram"] == 3
        assert stats["by_platform"]["discord"] == 1
        assert stats["by_type"]["text"] == 2
        assert stats["by_type"]["error"] == 1
        assert stats["by_type"]["status"] == 1
        assert stats["unique_users"] == 3
        assert stats["unique_chats"] == 3  # 67890, 88888, 22222


class TestGetMessageHistory:
    """Tests for get_message_history singleton."""
    
    def setup_method(self):
        """Reset message history before each test."""
        reset_message_history()
    
    def test_singleton(self):
        """Test that get_message_history returns the same instance."""
        history1 = get_message_history()
        history2 = get_message_history()
        
        assert history1 is history2
    
    def test_reset(self):
        """Test resetting the singleton."""
        history1 = get_message_history()
        history1.add_message("telegram", "12345", "67890", "Message", "text")
        
        reset_message_history()
        
        history2 = get_message_history()
        assert history2 is not history1
        assert len(history2._messages) == 0
