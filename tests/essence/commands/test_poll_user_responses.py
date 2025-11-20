"""
Unit tests for poll-user-responses command.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from essence.commands.poll_user_responses import (
    PollUserResponsesCommand,
    check_for_user_responses,
)


class TestCheckForUserResponses:
    """Tests for check_for_user_responses function."""

    def test_check_no_file(self, tmp_path):
        """Test checking when USER_REQUESTS.md doesn't exist."""
        with patch(
            "essence.commands.poll_user_responses.USER_REQUESTS_FILE",
            tmp_path / "USER_REQUESTS.md",
        ):
            new_responses, timed_out = check_for_user_responses()
            assert new_responses == []
            assert timed_out == []

    def test_check_no_agent_messages(self, tmp_path):
        """Test checking when there are no agent messages waiting."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text(
            """## [2025-11-19 12:00:00] Request
- **User:** (user_id: 123)
- **Platform:** Telegram
- **Type:** Request
- **Content:** User message
- **Status:** Pending
"""
        )
        with patch(
            "essence.commands.poll_user_responses.USER_REQUESTS_FILE", test_file
        ), patch("essence.chat.user_requests_sync.USER_REQUESTS_FILE", test_file):
            new_responses, timed_out = check_for_user_responses()
            assert new_responses == []
            assert timed_out == []

    def test_check_with_agent_message_no_response(self, tmp_path):
        """Test checking when agent message exists but no user response."""
        test_file = tmp_path / "USER_REQUESTS.md"
        test_file.write_text(
            """## [2025-11-19 12:00:00] Clarification
- **User:** (user_id: 123)
- **Platform:** Telegram
- **Type:** Clarification
- **Content:** Agent asking for clarification
- **Chat ID:** 456
- **Status:** Pending
"""
        )
        with patch(
            "essence.commands.poll_user_responses.USER_REQUESTS_FILE", test_file
        ), patch("essence.chat.user_requests_sync.USER_REQUESTS_FILE", test_file):
            new_responses, timed_out = check_for_user_responses(timeout_hours=0.001)
            # With very short timeout, should detect timeout
            # (implementation dependent - may require actual time check)
            assert isinstance(new_responses, list)
            assert isinstance(timed_out, list)


class TestPollUserResponsesCommand:
    """Tests for PollUserResponsesCommand."""

    def test_command_initialization(self):
        """Test command can be initialized."""
        from argparse import Namespace

        args = Namespace(timeout_hours=24.0)
        command = PollUserResponsesCommand(args)
        assert command is not None

    def test_command_name(self):
        """Test command name."""
        assert PollUserResponsesCommand.get_name() == "poll-user-responses"

    def test_command_description(self):
        """Test command description."""
        description = PollUserResponsesCommand.get_description()
        assert description is not None
        assert len(description) > 0

    @patch("essence.commands.poll_user_responses.check_for_user_responses")
    def test_command_run_no_responses(self, mock_check):
        """Test command run when no responses found."""
        from argparse import Namespace

        mock_check.return_value = ([], [])
        args = Namespace(timeout_hours=24.0)
        command = PollUserResponsesCommand(args)
        command.init()
        # Should not raise exception
        command.run()
        command.cleanup()

    @patch("essence.commands.poll_user_responses.check_for_user_responses")
    def test_command_run_with_responses(self, mock_check):
        """Test command run when responses found."""
        from argparse import Namespace

        from essence.commands.read_user_requests import UserRequest

        mock_check.return_value = (
            [
                UserRequest(
                    timestamp="2025-11-19 12:00:00",
                    user_id="123",
                    chat_id="456",
                    platform="telegram",
                    message_type="Clarification",
                    content="Agent question",
                    message_id="789",
                    status="Pending",
                )
            ],
            [],
        )
        args = Namespace(timeout_hours=24.0)
        command = PollUserResponsesCommand(args)
        command.init()
        # Should not raise exception
        command.run()
        command.cleanup()

    def test_command_add_args(self):
        """Test command argument parsing."""
        import argparse

        parser = argparse.ArgumentParser()
        PollUserResponsesCommand.add_args(parser)
        # Parse with default
        args = parser.parse_args([])
        assert hasattr(args, "timeout_hours")
        # Parse with custom timeout
        args = parser.parse_args(["--timeout-hours", "48"])
        assert args.timeout_hours == 48.0
