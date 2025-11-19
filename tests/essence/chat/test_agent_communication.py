"""
Unit tests for agent-to-user communication interface.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from essence.chat.agent_communication import (
    AgentCommunicationError,
    ChannelUnavailableError,
    CommunicationChannel,
    ServiceRunningError,
    ask_for_clarification,
    ask_for_feedback,
    check_discord_service_running,
    check_service_running,
    check_telegram_service_running,
    report_progress,
    request_help,
    send_message_to_user,
)


class TestCheckServiceRunning:
    """Tests for service status checking functions."""

    @patch("essence.chat.agent_communication.subprocess.run")
    def test_check_service_running_true(self, mock_run):
        """Test checking if a service is running (returns True)."""
        mock_run.return_value = MagicMock(stdout="container_id\n", returncode=0)

        result = check_service_running("telegram")

        assert result is True
        mock_run.assert_called_once()

    @patch("essence.chat.agent_communication.subprocess.run")
    def test_check_service_running_false(self, mock_run):
        """Test checking if a service is not running (returns False)."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        result = check_service_running("telegram")

        assert result is False

    @patch("essence.chat.agent_communication.subprocess.run")
    def test_check_service_running_timeout(self, mock_run):
        """Test handling timeout when checking service status."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("docker", 5)

        result = check_service_running("telegram")

        assert result is False

    @patch("essence.chat.agent_communication.check_service_running")
    def test_check_telegram_service_running(self, mock_check):
        """Test checking Telegram service specifically."""
        mock_check.return_value = True

        result = check_telegram_service_running()

        assert result is True
        mock_check.assert_called_once_with("telegram")

    @patch("essence.chat.agent_communication.check_service_running")
    def test_check_discord_service_running(self, mock_check):
        """Test checking Discord service specifically."""
        mock_check.return_value = True

        result = check_discord_service_running()

        assert result is True
        mock_check.assert_called_once_with("discord")


class TestSendMessageToUser:
    """Tests for send_message_to_user function."""

    def setup_method(self):
        """Reset message history before each test."""
        from essence.chat.message_history import reset_message_history

        reset_message_history()

    @patch("essence.chat.agent_communication.check_telegram_service_running")
    @patch("essence.chat.agent_communication.check_discord_service_running")
    @patch("essence.chat.agent_communication._send_telegram_message")
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"})
    def test_send_message_auto_telegram_available(
        self, mock_send_telegram, mock_check_discord, mock_check_telegram
    ):
        """Test sending message with AUTO channel (Telegram available)."""
        mock_check_telegram.return_value = False  # Service not running
        mock_check_discord.return_value = False
        mock_send_telegram.return_value = {"success": True, "message_id": "123"}

        result = send_message_to_user(
            user_id="12345",
            chat_id="67890",
            message="Test message",
            platform=CommunicationChannel.AUTO,
            require_service_stopped=False,  # Skip service check for testing
        )

        assert result["success"] is True
        mock_send_telegram.assert_called_once()

    @patch("essence.chat.agent_communication.check_telegram_service_running")
    @patch("essence.chat.agent_communication.check_discord_service_running")
    @patch("essence.chat.agent_communication._send_telegram_message")
    @patch("essence.chat.agent_communication._send_discord_message")
    @patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "test-token"}, clear=True)
    def test_send_message_auto_discord_fallback(
        self,
        mock_send_discord,
        mock_send_telegram,
        mock_check_discord,
        mock_check_telegram,
    ):
        """Test sending message with AUTO channel (Telegram unavailable, Discord fallback)."""
        mock_check_telegram.return_value = False
        mock_check_discord.return_value = False
        # Telegram not available (no token), so should fallback to Discord
        mock_send_discord.return_value = {"success": True, "message_id": "456"}

        result = send_message_to_user(
            user_id="12345",
            chat_id="67890",
            message="Test message",
            platform=CommunicationChannel.AUTO,
            require_service_stopped=False,
        )

        assert result["success"] is True
        mock_send_discord.assert_called_once()

    @patch("essence.chat.agent_communication.check_telegram_service_running")
    def test_send_message_service_running_error(self, mock_check_telegram):
        """Test that ServiceRunningError is raised when service is running."""
        mock_check_telegram.return_value = True  # Service is running

        with pytest.raises(ServiceRunningError):
            send_message_to_user(
                user_id="12345",
                chat_id="67890",
                message="Test message",
                platform=CommunicationChannel.TELEGRAM,
                require_service_stopped=True,
            )

    @patch("essence.chat.agent_communication.check_telegram_service_running")
    @patch("essence.chat.agent_communication._send_telegram_message")
    def test_send_message_validation(self, mock_send_telegram, mock_check_telegram):
        """Test that messages are validated before sending."""
        mock_check_telegram.return_value = False
        mock_send_telegram.return_value = {"success": True, "message_id": "123"}

        # Message that exceeds Telegram limit
        long_message = "x" * 5000

        result = send_message_to_user(
            user_id="12345",
            chat_id="67890",
            message=long_message,
            platform=CommunicationChannel.TELEGRAM,
            require_service_stopped=False,
        )

        # Should still attempt to send (validation is a warning, not a blocker)
        # But the message should be handled appropriately
        assert mock_send_telegram.called

    @patch("essence.chat.agent_communication.check_telegram_service_running")
    @patch("httpx.Client")
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"})
    def test_send_message_stored_in_history(
        self, mock_httpx_client, mock_check_telegram
    ):
        """Test that sent messages are stored in message history."""
        from essence.chat.message_history import get_message_history

        mock_check_telegram.return_value = False

        # Mock httpx client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 123}}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx_client.return_value = mock_client

        send_message_to_user(
            user_id="12345",
            chat_id="67890",
            message="Test message",
            platform=CommunicationChannel.TELEGRAM,
            require_service_stopped=False,
        )

        history = get_message_history()
        messages = history.get_messages(user_id="12345", platform="telegram")

        assert len(messages) == 1
        assert messages[0].message_content == "Test message"
        assert messages[0].message_type == "text"
        assert messages[0].rendering_metadata.get("sent_by_agent") is True


class TestHelperFunctions:
    """Tests for helper functions (ask_for_clarification, etc.)."""

    @patch("essence.chat.agent_communication.send_message_to_user")
    def test_ask_for_clarification(self, mock_send):
        """Test ask_for_clarification helper."""
        mock_send.return_value = {"success": True, "message_id": "123"}

        result = ask_for_clarification(
            user_id="12345",
            chat_id="67890",
            question="What do you mean?",
        )

        assert result["success"] is True
        mock_send.assert_called_once()
        # Check that the message contains the question
        call_args = mock_send.call_args
        assert "What do you mean?" in call_args[1]["message"]

    @patch("essence.chat.agent_communication.send_message_to_user")
    def test_request_help(self, mock_send):
        """Test request_help helper."""
        mock_send.return_value = {"success": True, "message_id": "123"}

        result = request_help(
            user_id="12345",
            chat_id="67890",
            issue="I'm stuck on task X",
        )

        assert result["success"] is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "I'm stuck on task X" in call_args[1]["message"]

    @patch("essence.chat.agent_communication.send_message_to_user")
    def test_report_progress(self, mock_send):
        """Test report_progress helper."""
        mock_send.return_value = {"success": True, "message_id": "123"}

        result = report_progress(
            user_id="12345",
            chat_id="67890",
            progress_message="Completed step 1 of 3",
        )

        assert result["success"] is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "Completed step 1 of 3" in call_args[1]["message"]

    @patch("essence.chat.agent_communication.send_message_to_user")
    def test_ask_for_feedback(self, mock_send):
        """Test ask_for_feedback helper."""
        mock_send.return_value = {"success": True, "message_id": "123"}

        result = ask_for_feedback(
            user_id="12345",
            chat_id="67890",
            feedback_question="Does this look correct?",
        )

        assert result["success"] is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "Does this look correct?" in call_args[1]["message"]
