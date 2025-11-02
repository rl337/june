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

from .validator import SecurityValidator, ValidationResult, OperationType
from .audit import AuditLogger, AuditEventType
from .monitoring import SecurityMonitor, SecurityThreat, ThreatLevel
from .sandbox import SandboxManager
from .recovery import RecoveryManager, RecoveryAction
from .manager import SecurityManager

__all__ = [
    'SecurityValidator',
    'ValidationResult',
    'OperationType',
    'AuditLogger',
    'AuditEventType',
    'SecurityMonitor',
    'SecurityThreat',
    'ThreatLevel',
    'SandboxManager',
    'RecoveryManager',
    'RecoveryAction',
    'SecurityManager',
]

__version__ = "0.1.0"
