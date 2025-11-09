"""
Sandbox environment for safe code execution with resource limits.
"""

import logging
import resource
import subprocess
import sys
import os
import signal
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class ResourceLimits:
    """Resource limits for sandbox execution."""
    
    # CPU time limit (seconds)
    cpu_time_limit: float = 60.0
    
    # Memory limit (MB)
    memory_limit_mb: int = 512
    
    # Disk I/O limit (not directly enforceable, but monitored)
    max_file_size_mb: int = 10
    
    # Network access (blocked by default)
    allow_network: bool = False
    
    # Maximum number of processes
    max_processes: int = 5
    
    # Timeout for operations (seconds)
    timeout: float = 300.0


class SandboxEnvironment:
    """
    Sandbox environment for safe code execution with resource limits.
    
    Features:
    - CPU time limits
    - Memory limits
    - Process limits
    - Timeout controls
    - Network access control
    - Security boundaries
    """
    
    def __init__(
        self,
        project_paths: Optional[List[str]] = None,
        resource_limits: Optional[ResourceLimits] = None,
        enable_security: bool = True
    ):
        """
        Initialize sandbox environment.
        
        Args:
            project_paths: List of allowed project root paths
            resource_limits: Resource limits configuration
            enable_security: Whether to enable security restrictions
        """
        self.project_paths = [Path(p).resolve() for p in (project_paths or [])]
        self.resource_limits = resource_limits or ResourceLimits()
        self.enable_security = enable_security
        
        logger.info(
            f"SandboxEnvironment initialized: "
            f"cpu_limit={self.resource_limits.cpu_time_limit}s, "
            f"memory_limit={self.resource_limits.memory_limit_mb}MB, "
            f"timeout={self.resource_limits.timeout}s"
        )
    
    def _set_resource_limits(self) -> None:
        """Set resource limits for the current process."""
        try:
            # Set CPU time limit (soft and hard)
            cpu_limit = int(self.resource_limits.cpu_time_limit)
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (cpu_limit, cpu_limit)
            )
            
            # Set memory limit (RSS - Resident Set Size)
            memory_limit_bytes = self.resource_limits.memory_limit_mb * 1024 * 1024
            resource.setrlimit(
                resource.RLIMIT_RSS,
                (memory_limit_bytes, memory_limit_bytes)
            )
            
            # Set process limit
            resource.setrlimit(
                resource.RLIMIT_NPROC,
                (self.resource_limits.max_processes, self.resource_limits.max_processes)
            )
            
            # Set file size limit
            file_size_limit = self.resource_limits.max_file_size_mb * 1024 * 1024
            resource.setrlimit(
                resource.RLIMIT_FSIZE,
                (file_size_limit, file_size_limit)
            )
            
            logger.debug("Resource limits set successfully")
        except (ValueError, OSError) as e:
            logger.warning(f"Failed to set some resource limits: {e}")
            # Continue execution - some limits may not be supported on all systems
    
    def _create_preexec_fn(self):
        """Create a preexec_fn function for subprocess."""
        limits = self.resource_limits
        
        def set_limits():
            """Set resource limits in child process."""
            try:
                # Set CPU time limit
                cpu_limit = int(limits.cpu_time_limit)
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
                
                # Set memory limit
                memory_limit_bytes = limits.memory_limit_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_RSS, (memory_limit_bytes, memory_limit_bytes))
                
                # Set process limit
                resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes))
                
                # Set file size limit
                file_size_limit = limits.max_file_size_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_FSIZE, (file_size_limit, file_size_limit))
            except (ValueError, OSError) as e:
                logger.warning(f"Failed to set resource limits in child: {e}")
        
        return set_limits if self.enable_security else None
    
    def _validate_path(self, path: Path) -> bool:
        """
        Validate that a path is within allowed project directories.
        
        Args:
            path: Path to validate
            
        Returns:
            True if path is allowed, False otherwise
        """
        if not self.enable_security:
            return True
        
        if not self.project_paths:
            return True  # No restrictions if no project paths specified
        
        resolved_path = path.resolve()
        
        # Check if path is within any allowed project directory
        for project_path in self.project_paths:
            try:
                resolved_path.relative_to(project_path)
                return True
            except ValueError:
                continue
        
        return False
    
    @contextmanager
    def execute_in_sandbox(
        self,
        work_dir: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None
    ):
        """
        Context manager for executing code in sandbox environment.
        
        Args:
            work_dir: Working directory for execution
            env: Environment variables (network access removed if not allowed)
            
        Yields:
            Execution context with resource limits applied
        """
        # Set up working directory
        if work_dir:
            work_dir = Path(work_dir).resolve()
            if not self._validate_path(work_dir):
                raise ValueError(f"Working directory {work_dir} is not within allowed project paths")
        else:
            work_dir = self.project_paths[0] if self.project_paths else Path.cwd()
        
        # Set up environment
        execution_env = os.environ.copy()
        if env:
            execution_env.update(env)
        
        # Block network access if not allowed
        if not self.resource_limits.allow_network:
            # Remove network-related environment variables
            network_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
            for var in network_vars:
                execution_env.pop(var, None)
        
        # Save original resource limits
        original_limits = {}
        try:
            for limit_type in [resource.RLIMIT_CPU, resource.RLIMIT_RSS, resource.RLIMIT_NPROC, resource.RLIMIT_FSIZE]:
                original_limits[limit_type] = resource.getrlimit(limit_type)
        except Exception as e:
            logger.warning(f"Failed to get original resource limits: {e}")
        
        try:
            # Set resource limits
            self._set_resource_limits()
            
            # Change to working directory
            original_cwd = os.getcwd()
            os.chdir(work_dir)
            
            try:
                yield {
                    "work_dir": work_dir,
                    "env": execution_env
                }
            finally:
                # Restore original working directory
                os.chdir(original_cwd)
                
                # Restore original resource limits
                try:
                    for limit_type, (soft, hard) in original_limits.items():
                        resource.setrlimit(limit_type, (soft, hard))
                except Exception as e:
                    logger.warning(f"Failed to restore resource limits: {e}")
        except Exception as e:
            logger.error(f"Error in sandbox execution: {e}", exc_info=True)
            raise
    
    def execute_command(
        self,
        command: List[str],
        work_dir: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
        capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Execute a shell command in sandbox environment.
        
        Args:
            command: Command and arguments as list
            work_dir: Working directory
            env: Environment variables
            input_data: Input data to send to process
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            CompletedProcess with result
            
        Raises:
            subprocess.TimeoutExpired: If command exceeds timeout
            ValueError: If command is blocked by security
        """
        # Validate command
        if self.enable_security:
            self._validate_command(command)
        
        # Set up working directory
        if work_dir:
            work_dir = Path(work_dir).resolve()
            if not self._validate_path(work_dir):
                raise ValueError(f"Working directory {work_dir} is not within allowed project paths")
        else:
            work_dir = self.project_paths[0] if self.project_paths else Path.cwd()
        
        # Set up environment
        execution_env = os.environ.copy()
        if env:
            execution_env.update(env)
        
        # Block network access if not allowed
        if not self.resource_limits.allow_network:
            network_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
            for var in network_vars:
                execution_env.pop(var, None)
        
        # Execute command with timeout
        try:
            preexec_fn = self._create_preexec_fn()
            result = subprocess.run(
                command,
                cwd=work_dir,
                env=execution_env,
                input=input_data.encode() if input_data else None,
                capture_output=capture_output,
                text=True,
                timeout=self.resource_limits.timeout,
                preexec_fn=preexec_fn
            )
            return result
        except subprocess.TimeoutExpired:
            logger.warning(f"Command {command} timed out after {self.resource_limits.timeout}s")
            raise
    
    def _validate_command(self, command: List[str]) -> None:
        """
        Validate command is safe to execute.
        
        Args:
            command: Command to validate
            
        Raises:
            ValueError: If command is blocked
        """
        if not command:
            raise ValueError("Empty command")
        
        cmd_str = " ".join(command).lower()
        
        # Block dangerous operations
        dangerous_patterns = [
            "rm -rf /",
            "rm -rf /",
            "format c:",
            "mkfs",
            "dd if=",
            ":(){ :|:& };:",  # Fork bomb
            "> /dev/sda",
        ]
        
        for pattern in dangerous_patterns:
            if pattern in cmd_str:
                raise ValueError(f"Dangerous command blocked: {pattern}")
        
        # Block network access if not allowed
        if not self.resource_limits.allow_network:
            network_commands = ["curl", "wget", "nc", "netcat", "ssh", "scp", "rsync"]
            if any(cmd in command[0].lower() for cmd in network_commands):
                raise ValueError(f"Network command blocked: {command[0]}")
    
    def execute_python_code(
        self,
        code: str,
        work_dir: Optional[Path] = None,
        globals_dict: Optional[Dict[str, Any]] = None,
        locals_dict: Optional[Dict[str, Any]] = None,
        capture_output: bool = True
    ) -> Dict[str, Any]:
        """
        Execute Python code in sandbox environment.
        
        Args:
            code: Python code to execute
            work_dir: Working directory
            globals_dict: Global namespace
            locals_dict: Local namespace
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            Dict with 'success', 'output', 'error', 'result' keys
        """
        import io
        import contextlib
        
        # Set up working directory
        if work_dir:
            work_dir = Path(work_dir).resolve()
            if not self._validate_path(work_dir):
                return {
                    "success": False,
                    "output": "",
                    "error": f"Working directory {work_dir} is not within allowed project paths",
                    "result": None
                }
        else:
            work_dir = self.project_paths[0] if self.project_paths else Path.cwd()
        
        # Set up namespaces
        exec_globals = {
            "__builtins__": __builtins__,
            "__name__": "__main__",
            "__file__": str(work_dir / "<exec>"),
        }
        if globals_dict:
            exec_globals.update(globals_dict)
        
        exec_locals = locals_dict or {}
        
        # Capture output
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        result_value = None
        error = None
        
        try:
            with self.execute_in_sandbox(work_dir=work_dir):
                # Redirect stdout/stderr
                with contextlib.redirect_stdout(stdout_capture if capture_output else sys.stdout), \
                     contextlib.redirect_stderr(stderr_capture if capture_output else sys.stderr):
                    
                    # Execute code
                    try:
                        code_obj = compile(code, "<exec>", "exec")
                        exec(code_obj, exec_globals, exec_locals)
                        
                        # Try to get result from locals
                        if "result" in exec_locals:
                            result_value = exec_locals["result"]
                    except Exception as e:
                        error = str(e)
                        logger.error(f"Error executing Python code: {e}", exc_info=True)
        
        except Exception as e:
            error = str(e)
            logger.error(f"Error in sandbox execution: {e}", exc_info=True)
        
        stdout_text = stdout_capture.getvalue() if capture_output else ""
        stderr_text = stderr_capture.getvalue() if capture_output else ""
        
        return {
            "success": error is None,
            "output": stdout_text,
            "error": error or stderr_text,
            "result": result_value
        }
