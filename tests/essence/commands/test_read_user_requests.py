"""
Unit tests for read-user-requests command.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from essence.commands.read_user_requests import (
    ReadUserRequestsCommand,
    get_pending_requests,
    parse_user_requests_file,
)


class TestParseUserRequestsFile:
    """Tests for parsing USER_REQUESTS.md file."""

    def test_parse_empty_file(self, tmp_path):
        """Test parsing an empty file."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text("")
        result = parse_user_requests_file(test_file)
        assert result == []

    def test_parse_single_request(self, tmp_path):
        """Test parsing a single request."""
        # Use the actual format from sync_message_to_user_requests
        test_file = tmp_path / "USER_REQUESTS.md"
        # The format has the entry after "## Communication Log" section
        test_file.write_text(
            """# User Requests and Agent Communication Log

## Communication Log

## [2025-11-19 12:00:00] Request
- **User:** @testuser (user_id: 123)
- **Platform:** Telegram
- **Type:** Request
- **Content:** Test message
- **Message ID:** 789
- **Chat ID:** 456
- **Status:** Pending

<!-- Messages will be synced here automatically -->
"""
        )
        result = parse_user_requests_file(test_file)
        assert len(result) == 1
        assert result[0].user_id == "123"
        assert result[0].content == "Test message"
        assert result[0].status == "Pending"
        assert result[0].message_type == "Request"

    def test_parse_multiple_requests(self, tmp_path):
        """Test parsing multiple requests."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text(
            """## [2025-11-19 12:00:00] Request
- **User:** (user_id: 123)
- **Platform:** Telegram
- **Type:** Request
- **Content:** Message 1
- **Chat ID:** 111
- **Status:** Pending

## [2025-11-19 12:05:00] Request
- **User:** (user_id: 456)
- **Platform:** Discord
- **Type:** Request
- **Content:** Message 2
- **Chat ID:** 222
- **Status:** Responded
"""
        )
        result = parse_user_requests_file(test_file)
        assert len(result) == 2
        assert result[0].user_id == "123"
        assert result[1].user_id == "456"
        assert result[0].status == "Pending"
        assert result[1].status == "Responded"
        # Note: parse_user_requests_file only returns entries with message_type == "Request"
        # and status doesn't matter for inclusion, only for filtering in get_pending_requests


class TestGetPendingRequests:
    """Tests for getting pending requests."""

    def test_get_pending_requests_empty(self, tmp_path):
        """Test getting pending requests from empty file."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text("")
        result = get_pending_requests(test_file)
        assert result == []

    def test_get_pending_requests_filtered(self, tmp_path):
        """Test that only pending requests are returned."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text(
            """## [2025-11-19 12:00:00] Request
- **User:** (user_id: 123)
- **Platform:** Telegram
- **Type:** Request
- **Content:** Pending message
- **Chat ID:** 111
- **Status:** Pending

## [2025-11-19 12:05:00] Request
- **User:** (user_id: 456)
- **Platform:** Telegram
- **Type:** Request
- **Content:** Responded message
- **Chat ID:** 222
- **Status:** Responded
"""
        )
        result = get_pending_requests(test_file)
        assert len(result) == 1
        assert result[0].user_id == "123"
        assert result[0].status == "Pending"


class TestReadUserRequestsCommand:
    """Tests for ReadUserRequestsCommand."""

    def test_command_initialization(self):
        """Test command can be initialized."""
        from argparse import Namespace

        args = Namespace()
        command = ReadUserRequestsCommand(args)
        assert command is not None

    def test_command_name(self):
        """Test command name."""
        assert ReadUserRequestsCommand.get_name() == "read-user-requests"

    def test_command_description(self):
        """Test command description."""
        description = ReadUserRequestsCommand.get_description()
        assert description is not None
        assert len(description) > 0

    @patch("essence.commands.read_user_requests.get_pending_requests")
    def test_command_run_no_requests(self, mock_get_pending):
        """Test command run when no pending requests."""
        from argparse import Namespace

        mock_get_pending.return_value = []
        args = Namespace()
        command = ReadUserRequestsCommand(args)
        command.init()
        # Should not raise exception
        command.run()
        command.cleanup()

    @patch("essence.commands.read_user_requests.get_pending_requests")
    def test_command_run_with_requests(self, mock_get_pending):
        """Test command run with pending requests."""
        from argparse import Namespace

        from essence.commands.read_user_requests import UserRequest

        mock_get_pending.return_value = [
            UserRequest(
                timestamp="2025-11-19 12:00:00",
                user_id="123",
                chat_id="456",
                platform="telegram",
                message_type="Request",
                content="Test message",
                message_id="789",
                status="Pending",
            )
        ]
        args = Namespace()
        command = ReadUserRequestsCommand(args)
        command.init()
        # Should not raise exception
        command.run()
        command.cleanup()
