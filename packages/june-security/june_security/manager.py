"""
Security Manager - High-level interface that integrates all security components.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .audit import AuditEventType, AuditLogger
from .monitoring import SecurityMonitor, SecurityThreat
from .sandbox import SandboxManager
from .validator import OperationType, SecurityValidator, ValidationResult

logger = logging.getLogger(__name__)


class SecurityManager:
    """
    High-level security manager that integrates all security components.

    Provides a unified interface for:
    - Validating operations before execution
    - Logging all operations for auditing
    - Monitoring for security threats
    - Managing sandboxed execution environments
    """

    def __init__(
        self,
        allowed_project_paths: list,
        audit_log_file: Optional[str] = None,
        enable_sandboxing: bool = True,
        enable_monitoring: bool = True,
        enable_audit_logging: bool = True,
    ):
        """
        Initialize security manager with all components.

        Args:
            allowed_project_paths: List of allowed project root paths
            audit_log_file: Path to audit log file (optional)
            enable_sandboxing: Whether to enable sandboxing
            enable_monitoring: Whether to enable security monitoring
            enable_audit_logging: Whether to enable audit logging
        """
        # Initialize validator
        self.validator = SecurityValidator(
            allowed_project_paths=allowed_project_paths,
            block_dangerous_commands=True,
            require_path_validation=True,
            block_force_push_main=True,
        )

        # Initialize audit logger
        self.audit_logger = None
        if enable_audit_logging:
            self.audit_logger = AuditLogger(
                log_file=audit_log_file,
                enable_file_logging=True,
                enable_console_logging=True,
            )

        # Initialize security monitor
        self.monitor = None
        if enable_monitoring:
            self.monitor = SecurityMonitor(
                suspicious_pattern_threshold=3,
                time_window_minutes=5,
                enable_auto_response=True,
            )

        # Initialize sandbox manager
        self.sandbox_manager = None
        if enable_sandboxing:
            self.sandbox_manager = SandboxManager(
                base_sandbox_dir=None,  # Use default temp directory
                enable_resource_limits=True,
                max_memory_mb=1024,
                max_cpu_time_seconds=300,
            )

        logger.info("SecurityManager initialized with all security components")

    def validate_operation(
        self,
        agent_id: str,
        operation: Dict[str, Any],
        operation_type: Optional[OperationType] = None,
    ) -> Tuple[ValidationResult, Optional[SecurityThreat]]:
        """
        Validate an operation before execution.

        Args:
            agent_id: Agent identifier
            operation: Operation to validate (dict with command/file_path/git_command)
            operation_type: Type of operation (auto-detected if not provided)

        Returns:
            Tuple of (validation_result, security_threat_if_detected)
        """
        # Validate operation
        validation_result = self.validator.validate_operation(operation, operation_type)

        # Extract operation string for logging
        operation_str = (
            operation.get("command")
            or operation.get("git_command")
            or operation.get("file_path")
            or str(operation)
        )

        # Analyze with security monitor
        threat = None
        if self.monitor:
            is_safe, threat = self.monitor.analyze_operation(
                agent_id=agent_id,
                operation=operation_str,
                allowed=bool(validation_result),
                operation_type=operation_type.value if operation_type else "unknown",
                details=operation,
            )

            if threat:
                validation_result = ValidationResult(
                    False, f"Security threat detected: {threat.threat_type}", "error"
                )

        # Log operation
        if self.audit_logger:
            self.audit_logger.log_operation(
                agent_id=agent_id,
                operation_type=operation_type.value if operation_type else "unknown",
                operation=operation_str,
                allowed=bool(validation_result),
                reason=validation_result.reason if not validation_result else None,
                details=operation,
            )

        # Log security violation if blocked
        if not validation_result and self.audit_logger:
            violation_type = threat.threat_type if threat else "validation_failed"
            self.audit_logger.log_security_violation(
                agent_id=agent_id,
                violation_type=violation_type,
                operation=operation_str,
                details={
                    "reason": validation_result.reason,
                    "threat": str(threat) if threat else None,
                },
            )

        return validation_result, threat

    def validate_command(
        self,
        agent_id: str,
        command: str,
        operation_type: OperationType = OperationType.COMMAND,
    ) -> Tuple[ValidationResult, Optional[SecurityThreat]]:
        """
        Validate a command before execution.

        Args:
            agent_id: Agent identifier
            command: Command to validate
            operation_type: Type of operation

        Returns:
            Tuple of (validation_result, security_threat_if_detected)
        """
        return self.validate_operation(
            agent_id=agent_id,
            operation={"command": command},
            operation_type=operation_type,
        )

    def validate_file_path(
        self,
        agent_id: str,
        file_path: str,
        operation_type: OperationType = OperationType.FILE_READ,
    ) -> Tuple[ValidationResult, Optional[SecurityThreat]]:
        """
        Validate a file path.

        Args:
            agent_id: Agent identifier
            file_path: File path to validate
            operation_type: Type of file operation

        Returns:
            Tuple of (validation_result, security_threat_if_detected)
        """
        return self.validate_operation(
            agent_id=agent_id,
            operation={"file_path": file_path},
            operation_type=operation_type,
        )

    def validate_git_operation(
        self, agent_id: str, git_command: str
    ) -> Tuple[ValidationResult, Optional[SecurityThreat]]:
        """
        Validate a git operation.

        Args:
            agent_id: Agent identifier
            git_command: Git command to validate

        Returns:
            Tuple of (validation_result, security_threat_if_detected)
        """
        return self.validate_operation(
            agent_id=agent_id,
            operation={"git_command": git_command},
            operation_type=OperationType.GIT_OPERATION,
        )

    def log_command_execution(
        self,
        agent_id: str,
        command: str,
        success: bool,
        output: Optional[str] = None,
        exit_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Log a command execution.

        Args:
            agent_id: Agent identifier
            command: Command that was executed
            success: Whether command succeeded
            output: Command output
            exit_code: Command exit code
            details: Additional execution details
        """
        if self.audit_logger:
            self.audit_logger.log_command_execution(
                agent_id=agent_id,
                command=command,
                success=success,
                output=output,
                exit_code=exit_code,
                details=details,
            )

    def get_security_statistics(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get security statistics.

        Args:
            agent_id: Filter by agent ID (optional)

        Returns:
            Dictionary with security statistics
        """
        stats = {}

        if self.monitor:
            if agent_id:
                stats["agent_statistics"] = self.monitor.get_agent_statistics(agent_id)
            else:
                stats["threats"] = len(self.monitor.get_threats())

        if self.audit_logger and agent_id:
            # Get recent audit logs for agent
            logs = self.audit_logger.get_audit_logs(agent_id=agent_id, limit=100)
            stats["recent_operations"] = len(logs)
            stats["security_violations"] = len(
                [
                    log
                    for log in logs
                    if log.get("event_type") == AuditEventType.SECURITY_VIOLATION.value
                ]
            )

        return stats

    def get_detected_threats(
        self, agent_id: Optional[str] = None, limit: int = 100
    ) -> list:
        """
        Get detected security threats.

        Args:
            agent_id: Filter by agent ID (optional)
            limit: Maximum number of threats to return

        Returns:
            List of security threats
        """
        if self.monitor:
            return self.monitor.get_threats(agent_id=agent_id, limit=limit)
        return []

    def get_sandbox_manager(self) -> Optional[SandboxManager]:
        """Get sandbox manager instance."""
        return self.sandbox_manager

    def get_validator(self) -> SecurityValidator:
        """Get security validator instance."""
        return self.validator

    def get_audit_logger(self) -> Optional[AuditLogger]:
        """Get audit logger instance."""
        return self.audit_logger

    def get_monitor(self) -> Optional[SecurityMonitor]:
        """Get security monitor instance."""
        return self.monitor
