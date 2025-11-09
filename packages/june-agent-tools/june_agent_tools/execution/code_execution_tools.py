"""
Code execution tools for executing Python code and shell commands safely.
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from june_agent_tools.tool import Tool, ToolResult
from june_agent_tools.execution.sandbox import SandboxEnvironment, ResourceLimits

logger = logging.getLogger(__name__)


class ExecutePythonCodeTool(Tool):
    """Tool for executing Python code dynamically in a sandbox environment."""
    
    def __init__(self, sandbox: Optional[SandboxEnvironment] = None):
        """
        Initialize Python code execution tool.
        
        Args:
            sandbox: Sandbox environment (creates default if not provided)
        """
        self.sandbox = sandbox or SandboxEnvironment()
    
    @property
    def name(self) -> str:
        return "execute_python_code"
    
    @property
    def description(self) -> str:
        return (
            "Execute Python code dynamically in a safe sandbox environment. "
            "Code runs with resource limits (CPU, memory, timeout) and security restrictions. "
            "Returns stdout, stderr, and any result value."
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute"
                },
                "work_dir": {
                    "type": "string",
                    "description": "Working directory for code execution",
                    "default": "."
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (overrides sandbox default)",
                    "default": 60,
                    "minimum": 1,
                    "maximum": 300
                },
                "memory_limit_mb": {
                    "type": "integer",
                    "description": "Memory limit in MB (overrides sandbox default)",
                    "default": 512,
                    "minimum": 64,
                    "maximum": 2048
                },
                "capture_output": {
                    "type": "boolean",
                    "description": "Capture stdout/stderr",
                    "default": True
                }
            },
            "required": ["code"]
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate code execution parameters."""
        if "code" not in params:
            return False
        code = params["code"]
        if not isinstance(code, str) or not code.strip():
            return False
        
        # Check for dangerous operations
        code_lower = code.lower()
        dangerous_patterns = [
            "import os; os.system",
            "import subprocess; subprocess",
            "__import__('os')",
            "__import__(\"os\")",
            "eval(",
            "exec(",
            "compile(",
        ]
        
        # Block dangerous patterns
        for pattern in dangerous_patterns:
            if pattern in code_lower:
                # Block direct os.system calls
                if "os.system" in code_lower or "os.popen" in code_lower:
                    return False
                # Block eval/exec/compile
                if "eval(" in code_lower or "exec(" in code_lower or "compile(" in code_lower:
                    return False
        
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute Python code in sandbox."""
        code = params["code"]
        work_dir = params.get("work_dir", ".")
        timeout = params.get("timeout", 60)
        memory_limit_mb = params.get("memory_limit_mb", 512)
        capture_output = params.get("capture_output", True)
        
        try:
            work_dir_path = Path(work_dir).resolve()
            
            # Create sandbox with custom limits
            resource_limits = ResourceLimits(
                cpu_time_limit=timeout,
                memory_limit_mb=memory_limit_mb,
                timeout=timeout
            )
            sandbox = SandboxEnvironment(
                project_paths=self.sandbox.project_paths,
                resource_limits=resource_limits,
                enable_security=self.sandbox.enable_security
            )
            
            # Execute code
            result = sandbox.execute_python_code(
                code=code,
                work_dir=work_dir_path,
                capture_output=capture_output
            )
            
            if result["success"]:
                output_lines = []
                if result["output"]:
                    output_lines.append("STDOUT:")
                    output_lines.append(result["output"])
                if result["error"]:
                    output_lines.append("STDERR:")
                    output_lines.append(result["error"])
                if result["result"] is not None:
                    output_lines.append(f"RESULT: {result['result']}")
                
                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "result": result["result"],
                        "has_output": bool(result["output"]),
                        "has_error": bool(result["error"])
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=result["error"] or "Code execution failed",
                    metadata={
                        "result": result["result"],
                        "has_output": bool(result["output"])
                    }
                )
        except Exception as e:
            logger.error(f"Error executing Python code: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error executing Python code: {str(e)}"
            )


class ExecuteShellCommandTool(Tool):
    """Tool for executing shell commands safely in a sandbox environment."""
    
    def __init__(self, sandbox: Optional[SandboxEnvironment] = None):
        """
        Initialize shell command execution tool.
        
        Args:
            sandbox: Sandbox environment (creates default if not provided)
        """
        self.sandbox = sandbox or SandboxEnvironment()
    
    @property
    def name(self) -> str:
        return "execute_shell_command"
    
    @property
    def description(self) -> str:
        return (
            "Execute shell commands safely in a sandbox environment. "
            "Commands run with resource limits (CPU, memory, timeout) and security restrictions. "
            "Dangerous operations (rm -rf /, etc.) are blocked. "
            "Returns stdout, stderr, and exit code."
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute"
                },
                "work_dir": {
                    "type": "string",
                    "description": "Working directory for command execution",
                    "default": "."
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds",
                    "default": 60,
                    "minimum": 1,
                    "maximum": 300
                },
                "memory_limit_mb": {
                    "type": "integer",
                    "description": "Memory limit in MB",
                    "default": 512,
                    "minimum": 64,
                    "maximum": 2048
                },
                "allow_network": {
                    "type": "boolean",
                    "description": "Allow network access (default: False)",
                    "default": False
                },
                "input_data": {
                    "type": "string",
                    "description": "Input data to send to command (stdin)"
                }
            },
            "required": ["command"]
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate shell command parameters."""
        if "command" not in params:
            return False
        command = params["command"]
        if not isinstance(command, str) or not command.strip():
            return False
        
        # Basic validation - detailed validation happens in sandbox
        command_lower = command.lower().strip()
        
        # Block obviously dangerous commands
        if command_lower.startswith("rm -rf /") or command_lower.startswith("rm -r /"):
            return False
        
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute shell command in sandbox."""
        command_str = params["command"]
        work_dir = params.get("work_dir", ".")
        timeout = params.get("timeout", 60)
        memory_limit_mb = params.get("memory_limit_mb", 512)
        allow_network = params.get("allow_network", False)
        input_data = params.get("input_data")
        
        try:
            work_dir_path = Path(work_dir).resolve()
            
            # Parse command into list
            import shlex
            command = shlex.split(command_str)
            
            # Create sandbox with custom limits
            resource_limits = ResourceLimits(
                cpu_time_limit=timeout,
                memory_limit_mb=memory_limit_mb,
                timeout=timeout,
                allow_network=allow_network
            )
            sandbox = SandboxEnvironment(
                project_paths=self.sandbox.project_paths,
                resource_limits=resource_limits,
                enable_security=self.sandbox.enable_security
            )
            
            # Execute command
            result = sandbox.execute_command(
                command=command,
                work_dir=work_dir_path,
                input_data=input_data,
                capture_output=True
            )
            
            output_lines = []
            if result.stdout:
                output_lines.append("STDOUT:")
                output_lines.append(result.stdout)
            if result.stderr:
                output_lines.append("STDERR:")
                output_lines.append(result.stderr)
            output_lines.append(f"EXIT CODE: {result.returncode}")
            
            success = result.returncode == 0
            
            return ToolResult(
                success=success,
                output="\n".join(output_lines),
                error=None if success else f"Command failed with exit code {result.returncode}",
                metadata={
                    "exit_code": result.returncode,
                    "command": command_str,
                    "has_stdout": bool(result.stdout),
                    "has_stderr": bool(result.stderr)
                }
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds"
            )
        except ValueError as e:
            # Security validation failed
            return ToolResult(
                success=False,
                output="",
                error=f"Command blocked by security: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error executing shell command: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error executing shell command: {str(e)}",
                metadata={
                    "exit_code": None,
                    "command": command_str,
                    "has_stdout": False,
                    "has_stderr": False
                }
            )
