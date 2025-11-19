"""
Security Monitor - Detects suspicious patterns and security threats.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Threat severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityThreat:
    """Represents a detected security threat."""

    def __init__(
        self,
        threat_type: str,
        threat_level: ThreatLevel,
        description: str,
        agent_id: str,
        operation: str,
        timestamp: datetime,
        details: Optional[Dict] = None,
    ):
        self.threat_type = threat_type
        self.threat_level = threat_level
        self.description = description
        self.agent_id = agent_id
        self.operation = operation
        self.timestamp = timestamp
        self.details = details or {}

    def __repr__(self):
        return (
            f"SecurityThreat(type={self.threat_type}, level={self.threat_level.value}, "
            f"agent={self.agent_id}, operation='{self.operation[:50]}...')"
        )


class SecurityMonitor:
    """
    Monitors agent operations for suspicious patterns and security threats.

    Features:
    - Detect suspicious patterns
    - Alert on security violations
    - Track security events
    - Automated response to threats
    """

    def __init__(
        self,
        suspicious_pattern_threshold: int = 3,
        time_window_minutes: int = 5,
        enable_auto_response: bool = True,
    ):
        """
        Initialize security monitor.

        Args:
            suspicious_pattern_threshold: Number of similar suspicious operations to trigger alert
            time_window_minutes: Time window for pattern detection
            enable_auto_response: Whether to automatically respond to threats
        """
        self.suspicious_pattern_threshold = suspicious_pattern_threshold
        self.time_window_minutes = time_window_minutes
        self.enable_auto_response = enable_auto_response

        # Track operations per agent
        self.agent_operations: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Track blocked operations
        self.blocked_operations: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # Detected threats
        self.detected_threats: List[SecurityThreat] = []

        # Suspicious patterns to detect
        self.suspicious_patterns = [
            self._detect_rapid_failed_operations,
            self._detect_repeated_blocked_operations,
            self._detect_path_traversal_attempts,
            self._detect_command_injection_attempts,
            self._detect_mass_file_deletions,
        ]

        logger.info("SecurityMonitor initialized")

    def analyze_operation(
        self,
        agent_id: str,
        operation: str,
        allowed: bool,
        operation_type: str = "command",
        details: Optional[Dict] = None,
    ) -> Tuple[bool, Optional[SecurityThreat]]:
        """
        Analyze an operation for security threats.

        Args:
            agent_id: Agent identifier
            operation: The operation that was attempted
            allowed: Whether the operation was allowed
            operation_type: Type of operation
            details: Additional operation details

        Returns:
            Tuple of (is_safe, threat_if_any)
        """
        timestamp = datetime.utcnow()

        # Record operation
        self.agent_operations[agent_id].append(
            {
                "timestamp": timestamp,
                "operation": operation,
                "operation_type": operation_type,
                "allowed": allowed,
                "details": details or {},
            }
        )

        # Record blocked operations
        if not allowed:
            self.blocked_operations[agent_id].append(
                {
                    "timestamp": timestamp,
                    "operation": operation,
                    "operation_type": operation_type,
                    "details": details or {},
                }
            )

        # Check for threats
        threat = self._detect_threats(
            agent_id, operation, allowed, operation_type, timestamp
        )

        if threat:
            self.detected_threats.append(threat)

            # Auto-response if enabled
            if self.enable_auto_response and threat.threat_level in [
                ThreatLevel.HIGH,
                ThreatLevel.CRITICAL,
            ]:
                self._auto_respond_to_threat(threat)

            return False, threat

        return True, None

    def _detect_threats(
        self,
        agent_id: str,
        operation: str,
        allowed: bool,
        operation_type: str,
        timestamp: datetime,
    ) -> Optional[SecurityThreat]:
        """Detect security threats using pattern matching."""

        for pattern_checker in self.suspicious_patterns:
            threat = pattern_checker(
                agent_id, operation, allowed, operation_type, timestamp
            )
            if threat:
                return threat

        return None

    def _detect_rapid_failed_operations(
        self,
        agent_id: str,
        operation: str,
        allowed: bool,
        operation_type: str,
        timestamp: datetime,
    ) -> Optional[SecurityThreat]:
        """Detect rapid failed operations (possible brute force attempt)."""

        # Check recent operations for this agent
        recent_ops = [
            op
            for op in self.agent_operations[agent_id]
            if (timestamp - op["timestamp"]).total_seconds()
            < self.time_window_minutes * 60
            and not op["allowed"]
        ]

        if len(recent_ops) >= self.suspicious_pattern_threshold:
            return SecurityThreat(
                threat_type="rapid_failed_operations",
                threat_level=ThreatLevel.MEDIUM,
                description=f"Agent attempted {len(recent_ops)} failed operations in {self.time_window_minutes} minutes",
                agent_id=agent_id,
                operation=operation,
                timestamp=timestamp,
                details={
                    "failed_count": len(recent_ops),
                    "time_window": self.time_window_minutes,
                },
            )

        return None

    def _detect_repeated_blocked_operations(
        self,
        agent_id: str,
        operation: str,
        allowed: bool,
        operation_type: str,
        timestamp: datetime,
    ) -> Optional[SecurityThreat]:
        """Detect repeated attempts at blocked operations."""

        if not allowed:
            # Check if similar operations were blocked recently
            recent_blocked = [
                op
                for op in self.blocked_operations[agent_id]
                if (timestamp - op["timestamp"]).total_seconds()
                < self.time_window_minutes * 60
            ]

            # Check for similar patterns
            operation_lower = operation.lower()
            similar_blocked = [
                op
                for op in recent_blocked
                if self._operations_similar(operation_lower, op["operation"].lower())
            ]

            if len(similar_blocked) >= self.suspicious_pattern_threshold:
                return SecurityThreat(
                    threat_type="repeated_blocked_operations",
                    threat_level=ThreatLevel.HIGH,
                    description=f"Agent repeatedly attempted similar blocked operations",
                    agent_id=agent_id,
                    operation=operation,
                    timestamp=timestamp,
                    details={"similar_attempts": len(similar_blocked)},
                )

        return None

    def _detect_path_traversal_attempts(
        self,
        agent_id: str,
        operation: str,
        allowed: bool,
        operation_type: str,
        timestamp: datetime,
    ) -> Optional[SecurityThreat]:
        """Detect path traversal attempts."""

        # Check for path traversal patterns
        path_traversal_patterns = [
            r"\.\./",
            r"\.\.\\",
            r"/\.\./",
            r"\\\.\.\\",
            r"/etc/passwd",
            r"/etc/shadow",
            r"/proc/",
            r"/sys/",
        ]

        for pattern in path_traversal_patterns:
            if re.search(pattern, operation, re.IGNORECASE):
                return SecurityThreat(
                    threat_type="path_traversal_attempt",
                    threat_level=ThreatLevel.HIGH,
                    description=f"Path traversal pattern detected in operation",
                    agent_id=agent_id,
                    operation=operation,
                    timestamp=timestamp,
                    details={"pattern": pattern},
                )

        return None

    def _detect_command_injection_attempts(
        self,
        agent_id: str,
        operation: str,
        allowed: bool,
        operation_type: str,
        timestamp: datetime,
    ) -> Optional[SecurityThreat]:
        """Detect command injection attempts."""

        # Check for command injection patterns
        injection_patterns = [
            r";\s*(rm|cat|ls|chmod|chown)",
            r"\|\s*(bash|sh|python|perl)",
            r"`.*(rm|cat|ls|chmod|chown)",
            r"\$\{.*\}",
            r"\$\(.*\)",
        ]

        for pattern in injection_patterns:
            if re.search(pattern, operation, re.IGNORECASE):
                return SecurityThreat(
                    threat_type="command_injection_attempt",
                    threat_level=ThreatLevel.CRITICAL,
                    description=f"Command injection pattern detected",
                    agent_id=agent_id,
                    operation=operation,
                    timestamp=timestamp,
                    details={"pattern": pattern},
                )

        return None

    def _detect_mass_file_deletions(
        self,
        agent_id: str,
        operation: str,
        allowed: bool,
        operation_type: str,
        timestamp: datetime,
    ) -> Optional[SecurityThreat]:
        """Detect mass file deletion attempts."""

        if "rm" in operation.lower() or "delete" in operation.lower():
            # Check for mass deletion patterns
            recent_ops = [
                op
                for op in self.agent_operations[agent_id]
                if (timestamp - op["timestamp"]).total_seconds()
                < self.time_window_minutes * 60
                and (
                    "rm" in op["operation"].lower()
                    or "delete" in op["operation"].lower()
                )
            ]

            if len(recent_ops) >= 5:  # Threshold for mass deletion
                return SecurityThreat(
                    threat_type="mass_deletion_attempt",
                    threat_level=ThreatLevel.CRITICAL,
                    description=f"Agent attempted {len(recent_ops)} file deletion operations in short time",
                    agent_id=agent_id,
                    operation=operation,
                    timestamp=timestamp,
                    details={"deletion_count": len(recent_ops)},
                )

        return None

    def _operations_similar(self, op1: str, op2: str) -> bool:
        """Check if two operations are similar."""
        # Simple similarity check - operations with same command type and similar structure
        # In production, use more sophisticated similarity metrics

        # Extract command name (first word)
        cmd1 = op1.split()[0] if op1.split() else ""
        cmd2 = op2.split()[0] if op2.split() else ""

        if cmd1 != cmd2:
            return False

        # Check if operations have similar length and structure
        length_diff = abs(len(op1) - len(op2)) / max(len(op1), len(op2))

        return length_diff < 0.3  # 30% length difference threshold

    def _auto_respond_to_threat(self, threat: SecurityThreat):
        """Automatically respond to detected threats."""
        logger.warning(f"Auto-responding to threat: {threat}")

        # In production, this would:
        # - Temporarily suspend agent
        # - Send alerts
        # - Trigger incident response procedures
        # - Log to security incident database

        # For now, just log a warning
        logger.critical(
            f"SECURITY THREAT DETECTED: {threat.threat_type} "
            f"(Level: {threat.threat_level.value}) "
            f"from agent {threat.agent_id}. "
            f"Operation: {threat.operation}"
        )

    def get_threats(
        self,
        agent_id: Optional[str] = None,
        threat_level: Optional[ThreatLevel] = None,
        limit: int = 100,
    ) -> List[SecurityThreat]:
        """
        Get detected security threats.

        Args:
            agent_id: Filter by agent ID
            threat_level: Filter by threat level
            limit: Maximum number of threats to return

        Returns:
            List of security threats
        """
        threats = self.detected_threats

        if agent_id:
            threats = [t for t in threats if t.agent_id == agent_id]

        if threat_level:
            threats = [t for t in threats if t.threat_level == threat_level]

        # Sort by timestamp (newest first) and limit
        threats.sort(key=lambda t: t.timestamp, reverse=True)

        return threats[:limit]

    def get_agent_statistics(self, agent_id: str) -> Dict:
        """
        Get security statistics for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary with security statistics
        """
        ops = list(self.agent_operations[agent_id])
        blocked = list(self.blocked_operations[agent_id])
        threats = [t for t in self.detected_threats if t.agent_id == agent_id]

        return {
            "total_operations": len(ops),
            "blocked_operations": len(blocked),
            "allowed_operations": len(ops) - len(blocked),
            "detected_threats": len(threats),
            "threats_by_level": {
                level.value: len([t for t in threats if t.threat_level == level])
                for level in ThreatLevel
            },
        }
