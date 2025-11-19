"""
Audit Logger - Logs all agent operations for security auditing and compliance.
"""

import json
import logging
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""

    COMMAND_EXECUTION = "command_execution"
    FILE_OPERATION = "file_operation"
    GIT_OPERATION = "git_operation"
    SECURITY_VIOLATION = "security_violation"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    OPERATION_ALLOWED = "operation_allowed"
    OPERATION_BLOCKED = "operation_blocked"


class AuditLogger:
    """
    Logs all agent operations for security auditing and compliance.

    Features:
    - Log all operations with full context
    - Track security violations
    - Provide audit trail for compliance
    - Export audit logs for analysis
    """

    def __init__(
        self,
        log_file: Optional[str] = None,
        enable_file_logging: bool = True,
        enable_console_logging: bool = True,
    ):
        """
        Initialize audit logger.

        Args:
            log_file: Path to audit log file (optional, defaults to audit.log in current directory)
            enable_file_logging: Whether to log to file
            enable_console_logging: Whether to log to console
        """
        self.enable_file_logging = enable_file_logging
        self.enable_console_logging = enable_console_logging

        if log_file:
            self.log_file_path = Path(log_file)
        else:
            # Default to audit.log in current directory
            self.log_file_path = Path("audit.log")

        # Ensure log directory exists
        if self.enable_file_logging:
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"AuditLogger initialized (file: {self.log_file_path}, file_logging: {enable_file_logging})"
        )

    def log_event(
        self,
        event_type: AuditEventType,
        agent_id: str,
        operation: str,
        result: str,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
    ):
        """
        Log an audit event.

        Args:
            event_type: Type of audit event
            agent_id: Agent identifier
            operation: Description of operation
            result: Result of operation (allowed/blocked/success/failure)
            details: Additional details about the operation
            severity: Severity level (info/warning/error/critical)
        """
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type.value,
            "agent_id": agent_id,
            "operation": operation,
            "result": result,
            "severity": severity,
            "details": details or {},
        }

        # Log to console if enabled
        if self.enable_console_logging:
            log_message = (
                f"[AUDIT] {audit_entry['timestamp']} | "
                f"{event_type.value.upper()} | "
                f"Agent: {agent_id} | "
                f"Operation: {operation} | "
                f"Result: {result}"
            )

            if severity == "critical" or severity == "error":
                logger.error(log_message)
            elif severity == "warning":
                logger.warning(log_message)
            else:
                logger.info(log_message)

        # Log to file if enabled
        if self.enable_file_logging:
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(audit_entry) + "\n")
            except Exception as e:
                logger.error(f"Failed to write audit log entry: {e}", exc_info=True)

    def log_operation(
        self,
        agent_id: str,
        operation_type: str,
        operation: str,
        allowed: bool,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Log an agent operation.

        Args:
            agent_id: Agent identifier
            operation_type: Type of operation (command/file/git/etc.)
            operation: The operation that was attempted
            allowed: Whether the operation was allowed
            reason: Reason for allowing/blocking
            details: Additional operation details
        """
        event_type = (
            AuditEventType.OPERATION_ALLOWED
            if allowed
            else AuditEventType.OPERATION_BLOCKED
        )
        result = "allowed" if allowed else "blocked"
        severity = "warning" if not allowed else "info"

        log_details = details or {}
        log_details.update({"operation_type": operation_type, "reason": reason})

        self.log_event(
            event_type=event_type,
            agent_id=agent_id,
            operation=operation,
            result=result,
            details=log_details,
            severity=severity,
        )

    def log_security_violation(
        self,
        agent_id: str,
        violation_type: str,
        operation: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Log a security violation.

        Args:
            agent_id: Agent identifier
            violation_type: Type of security violation
            operation: The operation that triggered the violation
            details: Additional violation details
        """
        self.log_event(
            event_type=AuditEventType.SECURITY_VIOLATION,
            agent_id=agent_id,
            operation=operation,
            result="blocked",
            details={"violation_type": violation_type, **(details or {})},
            severity="error",
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
            output: Command output (truncated if too long)
            exit_code: Command exit code
            details: Additional execution details
        """
        log_details = details or {}
        if output:
            # Truncate output if too long (keep first 1000 chars)
            if len(output) > 1000:
                log_details["output"] = output[:1000] + "... (truncated)"
            else:
                log_details["output"] = output
        if exit_code is not None:
            log_details["exit_code"] = exit_code

        self.log_event(
            event_type=AuditEventType.COMMAND_EXECUTION,
            agent_id=agent_id,
            operation=command,
            result="success" if success else "failure",
            details=log_details,
            severity="error" if not success else "info",
        )

    def get_audit_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        agent_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs with optional filtering.

        Args:
            start_time: Start time for log retrieval
            end_time: End time for log retrieval
            agent_id: Filter by agent ID
            event_type: Filter by event type
            limit: Maximum number of logs to return

        Returns:
            List of audit log entries
        """
        if not self.enable_file_logging or not self.log_file_path.exists():
            return []

        logs = []
        try:
            with open(self.log_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        # Apply filters
                        if (
                            start_time
                            and datetime.fromisoformat(entry["timestamp"]) < start_time
                        ):
                            continue
                        if (
                            end_time
                            and datetime.fromisoformat(entry["timestamp"]) > end_time
                        ):
                            continue
                        if agent_id and entry.get("agent_id") != agent_id:
                            continue
                        if event_type and entry.get("event_type") != event_type.value:
                            continue

                        logs.append(entry)

                        if len(logs) >= limit:
                            break

                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Failed to parse audit log entry: {e}")
                        continue
        except Exception as e:
            logger.error(f"Failed to read audit logs: {e}", exc_info=True)

        return logs
