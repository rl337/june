"""Tests for SecurityManager."""

import pytest
import tempfile
from pathlib import Path

from june_security import SecurityManager, OperationType


class TestSecurityManager:
    """Test SecurityManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.security_manager = SecurityManager(
            allowed_project_paths=[str(self.temp_dir)],
            enable_sandboxing=False,  # Disable for faster tests
            enable_monitoring=True,
            enable_audit_logging=True,
        )

    def test_validate_command_allowed(self):
        """Test validating an allowed command."""
        result, threat = self.security_manager.validate_command(
            agent_id="test-agent", command="ls -la"
        )
        assert result
        assert threat is None

    def test_validate_command_blocked(self):
        """Test validating a blocked command."""
        result, threat = self.security_manager.validate_command(
            agent_id="test-agent", command="rm -rf /"
        )
        assert not result
        # May or may not have a threat depending on monitoring

    def test_validate_file_path(self):
        """Test validating a file path."""
        test_file = self.temp_dir / "test.py"
        result, threat = self.security_manager.validate_file_path(
            agent_id="test-agent",
            file_path=str(test_file),
            operation_type=OperationType.FILE_READ,
        )
        assert result

    def test_log_command_execution(self):
        """Test logging command execution."""
        # Should not raise
        self.security_manager.log_command_execution(
            agent_id="test-agent",
            command="ls -la",
            success=True,
            output="test output",
            exit_code=0,
        )

    def test_get_security_statistics(self):
        """Test getting security statistics."""
        stats = self.security_manager.get_security_statistics(agent_id="test-agent")
        assert isinstance(stats, dict)

    def test_get_detected_threats(self):
        """Test getting detected threats."""
        threats = self.security_manager.get_detected_threats()
        assert isinstance(threats, list)
