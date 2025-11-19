"""
June Security Module - Comprehensive security and safety measures for agent execution.

This module provides:
- Operation validation (block dangerous commands)
- Path validation (prevent directory traversal)
- Git operation validation
- Audit logging
- Security monitoring
- Sandboxed execution environments
"""

from .audit import AuditEventType, AuditLogger
from .encryption import (
    EncryptionManager,
    generate_encryption_key,
    get_encryption_manager,
)
from .input_validation import (
    InputValidationError,
    InputValidator,
    get_input_validator,
    set_input_validator,
)
from .manager import SecurityManager
from .monitoring import SecurityMonitor, SecurityThreat, ThreatLevel
from .recovery import RecoveryAction, RecoveryManager
from .sandbox import SandboxManager
from .validator import OperationType, SecurityValidator, ValidationResult

__all__ = [
    "SecurityValidator",
    "ValidationResult",
    "OperationType",
    "AuditLogger",
    "AuditEventType",
    "SecurityMonitor",
    "SecurityThreat",
    "ThreatLevel",
    "SandboxManager",
    "RecoveryManager",
    "RecoveryAction",
    "SecurityManager",
    "InputValidator",
    "InputValidationError",
    "get_input_validator",
    "set_input_validator",
    "EncryptionManager",
    "get_encryption_manager",
    "generate_encryption_key",
]

__version__ = "0.1.0"
