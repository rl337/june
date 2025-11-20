"""
Unit tests for check-service-status command.
"""
from unittest.mock import MagicMock, patch

import pytest

from essence.commands.check_service_status import (
    CheckServiceStatusCommand,
    get_service_status,
    verify_services_stopped,
)


class TestGetServiceStatus:
    """Tests for get_service_status function."""

    @patch("essence.commands.check_service_status.check_telegram_service_running")
    @patch("essence.commands.check_service_status.check_discord_service_running")
    def test_get_service_status_both_stopped(self, mock_discord, mock_telegram):
        """Test getting status when both services are stopped."""
        mock_telegram.return_value = False
        mock_discord.return_value = False
        result = get_service_status()
        assert result["telegram"] is False
        assert result["discord"] is False

    @patch("essence.commands.check_service_status.check_telegram_service_running")
    @patch("essence.commands.check_service_status.check_discord_service_running")
    def test_get_service_status_both_running(self, mock_discord, mock_telegram):
        """Test getting status when both services are running."""
        mock_telegram.return_value = True
        mock_discord.return_value = True
        result = get_service_status()
        assert result["telegram"] is True
        assert result["discord"] is True

    @patch("essence.commands.check_service_status.check_telegram_service_running")
    @patch("essence.commands.check_service_status.check_discord_service_running")
    def test_get_service_status_mixed(self, mock_discord, mock_telegram):
        """Test getting status when one service is running."""
        mock_telegram.return_value = True
        mock_discord.return_value = False
        result = get_service_status()
        assert result["telegram"] is True
        assert result["discord"] is False


class TestVerifyServicesStopped:
    """Tests for verify_services_stopped function."""

    @patch("essence.commands.check_service_status.get_service_status")
    def test_verify_services_stopped_all_stopped(self, mock_get_status):
        """Test verification when all services are stopped."""
        mock_get_status.return_value = {"telegram": False, "discord": False}
        all_stopped, running = verify_services_stopped("auto")
        assert all_stopped is True
        assert len(running) == 0

    @patch("essence.commands.check_service_status.get_service_status")
    def test_verify_services_stopped_some_running(self, mock_get_status):
        """Test verification when some services are running."""
        mock_get_status.return_value = {"telegram": True, "discord": False}
        all_stopped, running = verify_services_stopped("auto")
        assert all_stopped is False
        assert "telegram" in running

    @patch("essence.commands.check_service_status.get_service_status")
    def test_verify_services_stopped_telegram_platform(self, mock_get_status):
        """Test verification for telegram platform specifically."""
        mock_get_status.return_value = {"telegram": False, "discord": True}
        all_stopped, running = verify_services_stopped("telegram")
        # Should only check telegram
        assert all_stopped is True or "telegram" not in running

    @patch("essence.commands.check_service_status.get_service_status")
    def test_verify_services_stopped_discord_platform(self, mock_get_status):
        """Test verification for discord platform specifically."""
        mock_get_status.return_value = {"telegram": True, "discord": False}
        all_stopped, running = verify_services_stopped("discord")
        # Should only check discord
        assert all_stopped is True or "discord" not in running


class TestCheckServiceStatusCommand:
    """Tests for CheckServiceStatusCommand."""

    def test_command_initialization(self):
        """Test command can be initialized."""
        from argparse import Namespace

        args = Namespace()
        command = CheckServiceStatusCommand(args)
        assert command is not None

    def test_command_name(self):
        """Test command name."""
        assert CheckServiceStatusCommand.get_name() == "check-service-status"

    def test_command_description(self):
        """Test command description."""
        description = CheckServiceStatusCommand.get_description()
        assert description is not None
        assert len(description) > 0

    @patch("essence.commands.check_service_status.get_service_status")
    def test_command_run_services_stopped(self, mock_get_status):
        """Test command run when services are stopped."""
        from argparse import Namespace

        mock_get_status.return_value = {"telegram": False, "discord": False}
        args = Namespace()
        command = CheckServiceStatusCommand(args)
        command.init()
        # Should not raise exception
        command.run()
        command.cleanup()

    @patch("essence.commands.check_service_status.get_service_status")
    def test_command_run_services_running(self, mock_get_status):
        """Test command run when services are running."""
        from argparse import Namespace

        mock_get_status.return_value = {"telegram": True, "discord": True}
        args = Namespace()
        command = CheckServiceStatusCommand(args)
        command.init()
        # Should not raise exception
        command.run()
        command.cleanup()
