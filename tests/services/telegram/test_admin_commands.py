"""Tests for admin commands."""
import pytest
import sys
import os
import importlib
import site
from unittest.mock import Mock, patch, AsyncMock, MagicMock

# Fix import conflict: ensure we import from installed python-telegram-bot, not local telegram dir
# Find site-packages directory with telegram
_site_packages = None
for sp_dir in list(site.getsitepackages()) + [site.getusersitepackages()]:
    if sp_dir and "site-packages" in sp_dir:
        _telegram_pkg_path = os.path.join(sp_dir, "telegram", "__init__.py")
        if os.path.exists(_telegram_pkg_path):
            _site_packages = sp_dir
            break

# Clear local telegram from module cache if it was imported
if "telegram" in sys.modules:
    mod = sys.modules["telegram"]
    if hasattr(mod, "__file__") and mod.__file__:
        if (
            "tests/services/telegram" in mod.__file__
            or "essence/services/telegram" in mod.__file__
        ):
            del sys.modules["telegram"]
            if "telegram.ext" in sys.modules:
                del sys.modules["telegram.ext"]

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
from telegram import Update, Message, User, Chat

# Restore original sys.path
sys.path[:] = _original_sys_path

from essence.services.telegram.admin_auth import (
    is_admin,
    require_admin,
    add_admin,
    remove_admin,
)
from essence.services.telegram.admin_db import (
    block_user,
    unblock_user,
    is_user_blocked,
    get_blocked_users,
    clear_conversation,
    clear_user_conversations,
    log_audit_action,
    get_audit_logs,
)


@pytest.fixture
def mock_update():
    """Create a mock Telegram update."""
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 123456789
    update.message = Mock(spec=Message)
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Create a mock Telegram context."""
    context = Mock()
    context.args = []
    return context


class TestAdminAuth:
    """Tests for admin authentication."""

    @patch("essence.services.telegram.admin_auth.get_db_connection")
    def test_is_admin_true(self, mock_conn):
        """Test is_admin returns True for admin user."""
        mock_cursor = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_cursor.cursor.return_value = mock_cursor
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = is_admin("123456789")
        assert result is True

    @patch("essence.services.telegram.admin_auth.get_db_connection")
    def test_is_admin_false(self, mock_conn):
        """Test is_admin returns False for non-admin user."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = is_admin("123456789")
        assert result is False

    @patch("essence.services.telegram.admin_auth.is_admin")
    def test_require_admin_success(self, mock_is_admin):
        """Test require_admin succeeds for admin user."""
        mock_is_admin.return_value = True
        result = require_admin("123456789")
        assert result is True

    @patch("essence.services.telegram.admin_auth.is_admin")
    def test_require_admin_failure(self, mock_is_admin):
        """Test require_admin raises PermissionError for non-admin."""
        mock_is_admin.return_value = False
        with pytest.raises(PermissionError):
            require_admin("123456789")

    @patch("essence.services.telegram.admin_auth.get_db_connection")
    def test_add_admin(self, mock_conn):
        """Test adding an admin user."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = add_admin("123456789")
        assert result is True
        mock_db.commit.assert_called_once()

    @patch("essence.services.telegram.admin_auth.get_db_connection")
    def test_remove_admin(self, mock_conn):
        """Test removing an admin user."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = remove_admin("123456789")
        assert result is True
        mock_db.commit.assert_called_once()


class TestAdminDB:
    """Tests for admin database operations."""

    @patch("essence.services.telegram.admin_db.get_db_connection")
    def test_block_user(self, mock_conn):
        """Test blocking a user."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = block_user("123456789", "admin123", "Test reason")
        assert result is True
        mock_db.commit.assert_called_once()

    @patch("essence.services.telegram.admin_db.get_db_connection")
    def test_unblock_user(self, mock_conn):
        """Test unblocking a user."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = unblock_user("123456789")
        assert result is True
        mock_db.commit.assert_called_once()

    @patch("essence.services.telegram.admin_db.get_db_connection")
    def test_is_user_blocked_true(self, mock_conn):
        """Test is_user_blocked returns True for blocked user."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = is_user_blocked("123456789")
        assert result is True

    @patch("essence.services.telegram.admin_db.get_db_connection")
    def test_is_user_blocked_false(self, mock_conn):
        """Test is_user_blocked returns False for non-blocked user."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = is_user_blocked("123456789")
        assert result is False

    @patch("essence.services.telegram.admin_db.get_db_connection")
    def test_clear_conversation(self, mock_conn):
        """Test clearing a conversation."""
        mock_cursor = Mock()
        mock_cursor.rowcount = 5
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = clear_conversation("conversation-id-123")
        assert result is True
        mock_db.commit.assert_called_once()

    @patch("essence.services.telegram.admin_db.get_db_connection")
    def test_clear_user_conversations(self, mock_conn):
        """Test clearing all conversations for a user."""
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [("conv1",), ("conv2",)]
        mock_cursor.rowcount = 2
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = clear_user_conversations("123456789")
        assert result == 2
        mock_db.commit.assert_called_once()

    @patch("essence.services.telegram.admin_db.get_db_connection")
    def test_log_audit_action(self, mock_conn):
        """Test logging an audit action."""
        mock_cursor = Mock()
        mock_db = Mock()
        mock_db.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_db

        result = log_audit_action(
            action="user_blocked",
            actor_user_id="admin123",
            target_user_id="123456789",
            details={"reason": "Test"},
        )
        assert result is True
        mock_db.commit.assert_called_once()


class TestAdminCommands:
    """Tests for admin command handlers."""

    @pytest.mark.asyncio
    @patch("handlers.admin_commands.require_admin")
    @patch("handlers.admin_commands.block_user")
    @patch("handlers.admin_commands.log_audit_action")
    async def test_block_command_success(
        self, mock_log, mock_block, mock_require, mock_update, mock_context
    ):
        """Test block command succeeds."""
        from handlers.admin_commands import block_command

        mock_require.return_value = True
        mock_block.return_value = True
        mock_context.args = ["123456789", "Test reason"]

        await block_command(mock_update, mock_context)

        mock_require.assert_called_once_with("123456789")
        mock_block.assert_called_once_with("123456789", "123456789", "Test reason")
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("handlers.admin_commands.require_admin")
    async def test_block_command_permission_denied(
        self, mock_require, mock_update, mock_context
    ):
        """Test block command fails for non-admin."""
        from handlers.admin_commands import block_command

        mock_require.side_effect = PermissionError("Not admin")

        await block_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "Access Denied" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    @patch("handlers.admin_commands.require_admin")
    @patch("handlers.admin_commands.unblock_user")
    @patch("handlers.admin_commands.log_audit_action")
    async def test_unblock_command_success(
        self, mock_log, mock_unblock, mock_require, mock_update, mock_context
    ):
        """Test unblock command succeeds."""
        from handlers.admin_commands import unblock_command

        mock_require.return_value = True
        mock_unblock.return_value = True
        mock_context.args = ["123456789"]

        await unblock_command(mock_update, mock_context)

        mock_require.assert_called_once_with("123456789")
        mock_unblock.assert_called_once_with("123456789")
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("handlers.admin_commands.require_admin")
    @patch("handlers.admin_commands.get_blocked_users")
    async def test_list_blocked_command(
        self, mock_get_blocked, mock_require, mock_update, mock_context
    ):
        """Test list blocked command."""
        from handlers.admin_commands import list_blocked_command

        mock_require.return_value = True
        mock_get_blocked.return_value = [
            {
                "user_id": "123456789",
                "blocked_by": "admin123",
                "reason": "Test reason",
                "created_at": "2024-01-01 00:00:00",
            }
        ]

        await list_blocked_command(mock_update, mock_context)

        mock_require.assert_called_once_with("123456789")
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("handlers.admin_commands.require_admin")
    @patch("handlers.admin_commands.clear_conversation")
    @patch("handlers.admin_commands.log_audit_action")
    async def test_clear_conversation_command(
        self, mock_log, mock_clear, mock_require, mock_update, mock_context
    ):
        """Test clear conversation command."""
        from handlers.admin_commands import clear_conversation_command

        mock_require.return_value = True
        mock_clear.return_value = True
        mock_context.args = ["conversation-id-123"]

        await clear_conversation_command(mock_update, mock_context)

        mock_require.assert_called_once_with("123456789")
        mock_clear.assert_called_once_with("conversation-id-123")
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("handlers.admin_commands.require_admin")
    @patch("handlers.admin_commands.clear_user_conversations")
    @patch("handlers.admin_commands.log_audit_action")
    async def test_clear_user_conversations_command(
        self, mock_log, mock_clear, mock_require, mock_update, mock_context
    ):
        """Test clear user conversations command."""
        from handlers.admin_commands import clear_user_conversations_command

        mock_require.return_value = True
        mock_clear.return_value = 3
        mock_context.args = ["123456789"]

        await clear_user_conversations_command(mock_update, mock_context)

        mock_require.assert_called_once_with("123456789")
        mock_clear.assert_called_once_with("123456789")
        mock_update.message.reply_text.assert_called_once()
