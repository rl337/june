"""
Security Validator - Validates agent operations to prevent malicious or dangerous actions.
"""

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of operations that can be validated."""
    COMMAND = "command"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    GIT_OPERATION = "git_operation"
    NETWORK = "network"
    PROCESS = "process"


class ValidationResult:
    """Result of a security validation check."""
    
    def __init__(self, allowed: bool, reason: Optional[str] = None, severity: str = "error"):
        self.allowed = allowed
        self.reason = reason or ("Operation allowed" if allowed else "Operation blocked")
        self.severity = severity  # "error", "warning", "info"
    
    def __bool__(self):
        return self.allowed
    
    def __repr__(self):
        status = "ALLOWED" if self.allowed else "BLOCKED"
        return f"ValidationResult({status}, reason='{self.reason}', severity='{self.severity}')"


class SecurityValidator:
    """
    Validates agent operations to prevent malicious or dangerous actions.
    
    Features:
    - Block dangerous commands (rm -rf, etc.)
    - Validate file paths (prevent escaping project directories)
    - Validate git operations (commit message quality, prevent force push to main)
    - Sanitize user inputs
    """
    
    # Dangerous command patterns that should be blocked
    DANGEROUS_COMMAND_PATTERNS = [
        r'\brm\s+(-rf|-r\s+-f|-\s*[rf]+)\s+',  # rm -rf
        r'\brm\s+.*\/\s*$',  # rm /
        r'\bdd\s+if=',  # dd (disk destroyer)
        r'\bmkfs\s+',  # mkfs (format filesystem)
        r'\bfdisk\s+',  # fdisk
        r'\bformat\s+',  # format (Windows)
        r'\bchmod\s+[0-7]{3}\s+',  # chmod with octal (may be legitimate but risky)
        r'>\s*/dev/(sd[a-z]|hd[a-z]|nvme)',  # Redirect to block device
        r'\bcp\s+.*\s+/dev/',  # Copy to device
        r'\b:\s*\(\)\s*\{\s*:\s*\|\s*:\s*&?\s*\}\s*;',  # Fork bomb
        r'\bcurl\s+.*\|\s*(bash|sh)\s*$',  # curl | bash (piping to shell)
        r'\bwget\s+.*\|\s*(bash|sh)\s*$',  # wget | bash
    ]
    
    # Dangerous file operations
    CRITICAL_PATHS = [
        '/etc/passwd',
        '/etc/shadow',
        '/etc/hosts',
        '/proc/sys',
        '/sys',
        '/boot',
        '/root',
    ]
    
    # Dangerous git operations
    DANGEROUS_GIT_PATTERNS = [
        r'\bgit\s+push\s+.*--force',  # Force push
        r'\bgit\s+push\s+.*-f\s+',  # Force push shorthand
        r'\bgit\s+reset\s+--hard\s+origin/(main|master)',  # Hard reset to main/master
        r'\bgit\s+checkout\s+--force',  # Force checkout
    ]
    
    def __init__(
        self,
        allowed_project_paths: List[str],
        block_dangerous_commands: bool = True,
        require_path_validation: bool = True,
        block_force_push_main: bool = True
    ):
        """
        Initialize security validator.
        
        Args:
            allowed_project_paths: List of allowed project root paths
            block_dangerous_commands: Whether to block dangerous commands
            require_path_validation: Whether to validate file paths
            block_force_push_main: Whether to block force push to main/master branches
        """
        self.allowed_project_paths = [Path(p).resolve() for p in allowed_project_paths]
        self.block_dangerous_commands = block_dangerous_commands
        self.require_path_validation = require_path_validation
        self.block_force_push_main = block_force_push_main
        
        # Compile regex patterns for performance
        self.dangerous_command_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.DANGEROUS_COMMAND_PATTERNS
        ]
        self.dangerous_git_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.DANGEROUS_GIT_PATTERNS
        ]
        
        logger.info(f"SecurityValidator initialized with {len(self.allowed_project_paths)} allowed project paths")
    
    def validate_command(self, command: str, operation_type: OperationType = OperationType.COMMAND) -> ValidationResult:
        """
        Validate a command before execution.
        
        Args:
            command: The command to validate
            operation_type: Type of operation
            
        Returns:
            ValidationResult indicating if command is allowed
        """
        if not command or not command.strip():
            return ValidationResult(False, "Empty command", "error")
        
        command = command.strip()
        
        # Check for dangerous commands
        if self.block_dangerous_commands:
            for pattern in self.dangerous_command_regex:
                if pattern.search(command):
                    return ValidationResult(
                        False,
                        f"Dangerous command pattern detected: {pattern.pattern}",
                        "error"
                    )
        
        # Check for dangerous git operations
        if operation_type == OperationType.GIT_OPERATION and self.block_force_push_main:
            for pattern in self.dangerous_git_regex:
                if pattern.search(command):
                    return ValidationResult(
                        False,
                        f"Dangerous git operation detected: {pattern.pattern}",
                        "error"
                    )
        
        # Additional validation based on operation type
        if operation_type == OperationType.FILE_DELETE:
            # Extra validation for file deletion
            if 'rm' in command.lower() and not self._is_safe_delete_command(command):
                return ValidationResult(
                    False,
                    "Unsafe file deletion command",
                    "error"
                )
        
        return ValidationResult(True, "Command validation passed")
    
    def validate_file_path(self, file_path: str, operation_type: OperationType = OperationType.FILE_READ) -> ValidationResult:
        """
        Validate a file path to prevent directory traversal and access to unauthorized locations.
        
        Args:
            file_path: The file path to validate
            operation_type: Type of file operation
            
        Returns:
            ValidationResult indicating if path is allowed
        """
        if not file_path or not file_path.strip():
            return ValidationResult(False, "Empty file path", "error")
        
        try:
            # Resolve the path
            resolved_path = Path(file_path).resolve()
            
            # Check if path is within allowed project directories
            if self.require_path_validation:
                is_allowed = False
                for allowed_path in self.allowed_project_paths:
                    try:
                        # Check if resolved_path is within allowed_path
                        resolved_path.relative_to(allowed_path)
                        is_allowed = True
                        break
                    except ValueError:
                        # Path is not within this allowed path
                        continue
                
                if not is_allowed:
                    return ValidationResult(
                        False,
                        f"File path outside allowed project directories: {file_path}",
                        "error"
                    )
            
            # Check for dangerous critical paths
            path_str = str(resolved_path)
            for critical_path in self.CRITICAL_PATHS:
                if path_str.startswith(critical_path):
                    return ValidationResult(
                        False,
                        f"Access to critical system path blocked: {path_str}",
                        "error"
                    )
            
            # Check for directory traversal attempts
            if '..' in file_path or file_path.startswith('/') and not any(
                str(resolved_path).startswith(str(allowed)) for allowed in self.allowed_project_paths
            ):
                # Additional check for resolved path
                if not any(
                    str(resolved_path).startswith(str(allowed)) for allowed in self.allowed_project_paths
                ):
                    return ValidationResult(
                        False,
                        f"Potential directory traversal detected: {file_path}",
                        "error"
                    )
            
            # Write operations get stricter validation
            if operation_type == OperationType.FILE_WRITE:
                # Block writes to critical files even within project
                critical_project_files = ['.git/config', '.git/HEAD', '.env']
                for critical_file in critical_project_files:
                    if critical_file in path_str:
                        return ValidationResult(
                            False,
                            f"Write to critical file blocked: {critical_file}",
                            "error"
                        )
            
            return ValidationResult(True, "File path validation passed")
            
        except Exception as e:
            logger.error(f"Error validating file path {file_path}: {e}", exc_info=True)
            return ValidationResult(False, f"Error validating path: {str(e)}", "error")
    
    def validate_git_operation(
        self,
        git_command: str,
        operation_type: OperationType = OperationType.GIT_OPERATION
    ) -> ValidationResult:
        """
        Validate a git operation.
        
        Args:
            git_command: The git command to validate
            operation_type: Type of operation
            
        Returns:
            ValidationResult indicating if git operation is allowed
        """
        # First validate as a command
        command_result = self.validate_command(git_command, operation_type)
        if not command_result:
            return command_result
        
        # Additional git-specific validation
        git_command_lower = git_command.lower().strip()
        
        # Block force push to main/master branches
        if self.block_force_push_main:
            force_patterns = [
                r'push\s+.*--force\s+origin/(main|master)',
                r'push\s+.*-f\s+origin/(main|master)',
                r'push\s+origin\s+(main|master)\s+--force',
                r'push\s+origin\s+(main|master)\s+-f',
            ]
            for pattern in force_patterns:
                if re.search(pattern, git_command_lower):
                    return ValidationResult(
                        False,
                        f"Force push to main/master branch blocked: {git_command}",
                        "error"
                    )
        
        # Validate commit message quality (if commit operation)
        if 'commit' in git_command_lower:
            # Extract commit message if present
            # Basic validation - commit messages should not be empty or too short
            commit_msg_match = re.search(r'-m\s+["\']?([^"\']+)["\']?', git_command_lower)
            if commit_msg_match:
                commit_msg = commit_msg_match.group(1)
                if len(commit_msg.strip()) < 3:
                    return ValidationResult(
                        False,
                        "Commit message too short (minimum 3 characters)",
                        "error"
                    )
                # Block suspicious commit messages
                suspicious_patterns = ['wip', 'test', 'fix', 'update', 'change']
                if commit_msg.lower().strip() in suspicious_patterns:
                    return ValidationResult(
                        False,
                        f"Commit message too generic: '{commit_msg}'",
                        "warning"
                    )
        
        return ValidationResult(True, "Git operation validation passed")
    
    def sanitize_input(self, user_input: str) -> str:
        """
        Sanitize user input to prevent injection attacks.
        
        Args:
            user_input: User input to sanitize
            
        Returns:
            Sanitized input
        """
        if not user_input:
            return ""
        
        # Remove null bytes
        sanitized = user_input.replace('\x00', '')
        
        # Remove control characters except newline and tab
        sanitized = ''.join(
            char for char in sanitized
            if ord(char) >= 32 or char in ['\n', '\t']
        )
        
        # Limit length to prevent DoS
        max_length = 100000  # 100KB
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
            logger.warning(f"Input truncated to {max_length} characters")
        
        return sanitized
    
    def _is_safe_delete_command(self, command: str) -> bool:
        """
        Check if a delete command is relatively safe.
        
        Args:
            command: The delete command
            
        Returns:
            True if command appears safe, False otherwise
        """
        # Very basic safety check - in production, this should be more sophisticated
        # Safe if it doesn't target root, critical paths, or use -rf without confirmation
        command_lower = command.lower()
        
        # Unsafe patterns
        unsafe_patterns = [
            r'rm\s+.*\s+/$',  # rm something /
            r'rm\s+-rf\s+',  # rm -rf (no confirmation)
            r'rm\s+.*\s+/\s*$',  # rm something /
        ]
        
        for pattern in unsafe_patterns:
            if re.search(pattern, command_lower):
                return False
        
        return True
    
    def validate_operation(
        self,
        operation: Dict[str, Any],
        operation_type: Optional[OperationType] = None
    ) -> ValidationResult:
        """
        Validate a complete operation with all its components.
        
        Args:
            operation: Dictionary containing operation details
                - command: Command to execute
                - file_path: File path (if file operation)
                - git_command: Git command (if git operation)
            operation_type: Type of operation (auto-detected if not provided)
            
        Returns:
            ValidationResult indicating if operation is allowed
        """
        # Auto-detect operation type if not provided
        if operation_type is None:
            if 'git_command' in operation or ('command' in operation and 'git' in operation.get('command', '').lower()):
                operation_type = OperationType.GIT_OPERATION
            elif 'file_path' in operation:
                if 'write' in operation.get('action', '').lower() or 'write' in operation.get('operation', '').lower():
                    operation_type = OperationType.FILE_WRITE
                elif 'delete' in operation.get('action', '').lower() or 'delete' in operation.get('operation', '').lower():
                    operation_type = OperationType.FILE_DELETE
                else:
                    operation_type = OperationType.FILE_READ
            else:
                operation_type = OperationType.COMMAND
        
        results = []
        
        # Validate command if present
        if 'command' in operation:
            result = self.validate_command(operation['command'], operation_type)
            results.append(result)
            if not result:
                return result
        
        # Validate git command if present
        if 'git_command' in operation:
            result = self.validate_git_operation(operation['git_command'], operation_type)
            results.append(result)
            if not result:
                return result
        
        # Validate file path if present
        if 'file_path' in operation:
            result = self.validate_file_path(operation['file_path'], operation_type)
            results.append(result)
            if not result:
                return result
        
        # All validations passed
        return ValidationResult(True, "All validations passed")
