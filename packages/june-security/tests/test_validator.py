"""Tests for SecurityValidator."""

import tempfile
from pathlib import Path

import pytest
from june_security import OperationType, SecurityValidator, ValidationResult


class TestSecurityValidator:
    """Test SecurityValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.validator = SecurityValidator(
            allowed_project_paths=[str(self.temp_dir)],
            block_dangerous_commands=True,
            require_path_validation=True,
            block_force_push_main=True,
        )

    def test_block_dangerous_command_rm_rf(self):
        """Test that rm -rf commands are blocked."""
        result = self.validator.validate_command("rm -rf /")
        assert not result
        assert "dangerous" in result.reason.lower()

    def test_block_dangerous_command_dd(self):
        """Test that dd commands are blocked."""
        result = self.validator.validate_command("dd if=/dev/zero of=/dev/sda")
        assert not result

    def test_allow_safe_command(self):
        """Test that safe commands are allowed."""
        result = self.validator.validate_command("ls -la")
        assert result
        assert result.allowed

    def test_validate_file_path_within_project(self):
        """Test that file paths within project are allowed."""
        test_file = self.temp_dir / "test.py"
        result = self.validator.validate_file_path(str(test_file))
        assert result
        assert result.allowed

    def test_block_file_path_outside_project(self):
        """Test that file paths outside project are blocked."""
        result = self.validator.validate_file_path("/etc/passwd")
        assert not result
        assert "outside" in result.reason.lower() or "critical" in result.reason.lower()

    def test_block_path_traversal(self):
        """Test that path traversal attempts are blocked."""
        result = self.validator.validate_file_path(
            str(self.temp_dir / ".." / "etc" / "passwd")
        )
        assert not result

    def test_block_force_push_to_main(self):
        """Test that force push to main/master is blocked."""
        result = self.validator.validate_git_operation("git push origin main --force")
        assert not result
        assert "force push" in result.reason.lower()

    def test_allow_normal_git_push(self):
        """Test that normal git push is allowed."""
        result = self.validator.validate_git_operation("git push origin feature-branch")
        assert result

    def test_block_short_commit_message(self):
        """Test that very short commit messages are blocked."""
        result = self.validator.validate_git_operation('git commit -m "x"')
        assert not result
        assert "short" in result.reason.lower()

    def test_sanitize_input(self):
        """Test input sanitization."""
        malicious_input = "test\x00string\nwith\0null\0bytes"
        sanitized = self.validator.sanitize_input(malicious_input)
        assert "\x00" not in sanitized
        assert "\n" in sanitized  # Newlines are allowed

    def test_validate_complete_operation(self):
        """Test validating a complete operation."""
        operation = {
            "command": "cat test.py",
            "file_path": str(self.temp_dir / "test.py"),
        }
        result = self.validator.validate_operation(operation)
        assert result
