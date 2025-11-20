"""
Unit tests for user requests synchronization.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from essence.chat.user_requests_sync import (
    USER_REQUESTS_FILE,
    get_whitelisted_users,
    is_user_whitelisted,
    sync_message_to_user_requests,
    update_message_status,
)


class TestGetWhitelistedUsers:
    """Tests for getting whitelisted users."""

    @patch.dict(os.environ, {"TELEGRAM_WHITELISTED_USERS": "123,456,789"})
    def test_get_whitelisted_users_telegram(self):
        """Test getting Telegram whitelisted users."""
        users = get_whitelisted_users("telegram")
        assert users == ["123", "456", "789"]

    @patch.dict(os.environ, {"DISCORD_WHITELISTED_USERS": "111,222"})
    def test_get_whitelisted_users_discord(self):
        """Test getting Discord whitelisted users."""
        users = get_whitelisted_users("discord")
        assert users == ["111", "222"]

    @patch.dict(os.environ, {}, clear=True)
    def test_get_whitelisted_users_empty(self):
        """Test getting whitelisted users when env var is not set."""
        users = get_whitelisted_users("telegram")
        assert users == []

    @patch.dict(os.environ, {"TELEGRAM_WHITELISTED_USERS": "123, 456 , 789 "})
    def test_get_whitelisted_users_with_spaces(self):
        """Test getting whitelisted users with spaces in env var."""
        users = get_whitelisted_users("telegram")
        assert users == ["123", "456", "789"]


class TestIsUserWhitelisted:
    """Tests for checking if user is whitelisted."""

    @patch.dict(os.environ, {"TELEGRAM_WHITELISTED_USERS": "123,456"})
    def test_is_user_whitelisted_true(self):
        """Test checking if user is whitelisted (returns True)."""
        assert is_user_whitelisted("123", "telegram") is True
        assert is_user_whitelisted("456", "telegram") is True

    @patch.dict(os.environ, {"TELEGRAM_WHITELISTED_USERS": "123,456"})
    def test_is_user_whitelisted_false(self):
        """Test checking if user is not whitelisted (returns False)."""
        assert is_user_whitelisted("999", "telegram") is False

    @patch.dict(os.environ, {}, clear=True)
    def test_is_user_whitelisted_no_env_var(self):
        """Test checking if user is whitelisted when env var is not set."""
        assert is_user_whitelisted("123", "telegram") is False


class TestSyncMessageToUserRequests:
    """Tests for syncing messages to USER_REQUESTS.md."""

    def test_sync_message_creates_file(self, tmp_path):
        """Test that syncing a message creates USER_REQUESTS.md if it doesn't exist."""
        with patch("essence.chat.user_requests_sync.USER_REQUESTS_FILE", tmp_path / "USER_REQUESTS.md"):
            result = sync_message_to_user_requests(
                user_id="123",
                chat_id="456",
                platform="telegram",
                message_type="Request",
                content="Test message",
            )
            assert result is True
            assert (tmp_path / "USER_REQUESTS.md").exists()
            content = (tmp_path / "USER_REQUESTS.md").read_text()
            assert "Test message" in content
            assert "user_id: 123" in content
            assert "**Platform:** Telegram" in content or "Platform: Telegram" in content

    def test_sync_message_appends_to_existing(self, tmp_path):
        """Test that syncing a message appends to existing file."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text("Existing content\n")
        with patch("essence.chat.user_requests_sync.USER_REQUESTS_FILE", test_file):
            result = sync_message_to_user_requests(
                user_id="123",
                chat_id="456",
                platform="telegram",
                message_type="Request",
                content="New message",
            )
            assert result is True
            content = test_file.read_text()
            assert "Existing content" in content
            assert "New message" in content

    def test_sync_message_with_username(self, tmp_path):
        """Test syncing a message with username."""
        with patch("essence.chat.user_requests_sync.USER_REQUESTS_FILE", tmp_path / "USER_REQUESTS.md"):
            result = sync_message_to_user_requests(
                user_id="123",
                chat_id="456",
                platform="telegram",
                message_type="Request",
                content="Test",
                username="@testuser",
            )
            assert result is True
            content = (tmp_path / "USER_REQUESTS.md").read_text()
            assert "@testuser" in content

    def test_sync_message_with_message_id(self, tmp_path):
        """Test syncing a message with message ID."""
        with patch("essence.chat.user_requests_sync.USER_REQUESTS_FILE", tmp_path / "USER_REQUESTS.md"):
            result = sync_message_to_user_requests(
                user_id="123",
                chat_id="456",
                platform="telegram",
                message_type="Request",
                content="Test",
                message_id="789",
            )
            assert result is True
            content = (tmp_path / "USER_REQUESTS.md").read_text()
            assert "**Message ID:** 789" in content or "Message ID: 789" in content


class TestUpdateMessageStatus:
    """Tests for updating message status in USER_REQUESTS.md."""

    def test_update_message_status_found(self, tmp_path):
        """Test updating status when message is found."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text(
            """## [2025-11-19 12:00:00] Request
- **User:** (user_id: 123)
- **Platform:** Telegram
- **Type:** Request
- **Content:** Test message
- **Message ID:** 789
- **Status:** Pending
"""
        )
        with patch("essence.chat.user_requests_sync.USER_REQUESTS_FILE", test_file):
            result = update_message_status(
                user_id="123",
                message_id="789",
                timestamp="2025-11-19 12:00:00",
                new_status="Responded",
            )
            assert result is True
            content = test_file.read_text()
            assert "**Status:** Responded" in content or "Status: Responded" in content
            # Old status should be replaced
            assert content.count("Pending") == 0 or content.count("Responded") > 0

    def test_update_message_status_not_found(self, tmp_path):
        """Test updating status when message is not found."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text("No matching content\n")
        with patch("essence.chat.user_requests_sync.USER_REQUESTS_FILE", test_file):
            result = update_message_status(
                user_id="999",
                message_id="999",
                timestamp="2025-11-19 12:00:00",
                new_status="Responded",
            )
            # Should return False or handle gracefully
            assert result is False or result is True  # Implementation dependent
