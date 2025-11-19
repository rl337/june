"""
Mock Code Execution Environment

Simulates code execution for safe testing without running actual code.
"""

import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ExecutionResult:
    """Result of code execution."""

    def __init__(
        self,
        success: bool,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        execution_time: float = 0.0,
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.execution_time = execution_time


class MockExecutionEnvironment:
    """Mock code execution environment for agent testing."""

    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize mock execution environment.

        Args:
            base_path: Base path for execution (creates temp if None)
        """
        if base_path:
            self.base_path = Path(base_path)
        else:
            self.temp_dir = tempfile.mkdtemp()
            self.base_path = Path(self.temp_dir)

        self.base_path.mkdir(parents=True, exist_ok=True)

        # Track executions
        self.executions: List[Dict[str, Any]] = []

        # Mock file system
        self.files: Dict[str, str] = {}

        # Command handlers
        self.command_handlers: Dict[str, Callable] = {
            "pytest": self._mock_pytest,
            "python": self._mock_python,
            "git": self._mock_git,
            "ls": self._mock_ls,
            "cat": self._mock_cat,
            "echo": self._mock_echo,
        }

    def execute_command(
        self, command: str, cwd: Optional[str] = None
    ) -> ExecutionResult:
        """
        Execute a command in the mock environment.

        Args:
            command: Command to execute
            cwd: Working directory

        Returns:
            ExecutionResult
        """
        parts = command.split()
        if not parts:
            return ExecutionResult(success=False, stderr="Empty command", returncode=1)

        cmd_name = parts[0]
        args = parts[1:]

        self.executions.append(
            {"command": command, "cwd": cwd or str(self.base_path), "args": args}
        )

        # Check if command is blocked
        if cmd_name in ["rm", "rmdir"] and "-rf" in args:
            return ExecutionResult(
                success=False,
                stderr="Dangerous operation blocked: recursive delete",
                returncode=1,
            )

        # Route to handler
        if cmd_name in self.command_handlers:
            try:
                return self.command_handlers[cmd_name](args, cwd)
            except Exception as e:
                return ExecutionResult(success=False, stderr=str(e), returncode=1)
        else:
            # Default: command not found
            return ExecutionResult(
                success=False, stderr=f"Command not found: {cmd_name}", returncode=127
            )

    def _mock_pytest(self, args: List[str], cwd: Optional[str]) -> ExecutionResult:
        """Mock pytest execution."""
        # Simulate test execution
        test_file = None
        for arg in args:
            if arg.endswith(".py") and "test" in arg:
                test_file = arg
                break

        if test_file and test_file in self.files:
            # Simulate test pass
            return ExecutionResult(
                success=True,
                stdout="test_passing PASSED\ntest_another PASSED\n\n2 passed in 0.01s",
                returncode=0,
                execution_time=0.5,
            )
        else:
            # No tests found
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="ERROR: could not find test files",
                returncode=5,
            )

    def _mock_python(self, args: List[str], cwd: Optional[str]) -> ExecutionResult:
        """Mock Python execution."""
        script = args[0] if args else None

        if script and script in self.files:
            # Execute mock script
            code = self.files[script]
            if "print" in code:
                output = "Hello, World!"
                if "print(" in code:
                    # Extract print argument
                    start = code.find("print(") + 6
                    end = code.find(")", start)
                    if end > start:
                        output = code[start:end].strip("\"'")
                return ExecutionResult(success=True, stdout=output, returncode=0)

        return ExecutionResult(
            success=False, stderr=f"File not found: {script}", returncode=1
        )

    def _mock_git(self, args: List[str], cwd: Optional[str]) -> ExecutionResult:
        """Mock git command."""
        if not args:
            return ExecutionResult(
                success=False, stderr="git: missing command", returncode=1
            )

        subcommand = args[0]

        if subcommand == "status":
            return ExecutionResult(
                success=True,
                stdout="On branch main\nnothing to commit, working tree clean",
                returncode=0,
            )
        elif subcommand == "status" and "--short" in args:
            return ExecutionResult(success=True, stdout="", returncode=0)
        elif subcommand == "diff":
            return ExecutionResult(success=True, stdout="", returncode=0)
        elif subcommand == "commit":
            # Validate commit message
            if "-m" in args:
                msg_idx = args.index("-m")
                if msg_idx + 1 < len(args):
                    message = args[msg_idx + 1]
                    if len(message) < 3:
                        return ExecutionResult(
                            success=False,
                            stderr="Aborting commit due to empty commit message",
                            returncode=1,
                        )
                    return ExecutionResult(
                        success=True,
                        stdout=f"[main abc1234] {message}\n 1 file changed, 1 insertion(+)",
                        returncode=0,
                    )

        return ExecutionResult(success=True, returncode=0)

    def _mock_ls(self, args: List[str], cwd: Optional[str]) -> ExecutionResult:
        """Mock ls command."""
        path = args[0] if args else "."
        files = list(self.files.keys())
        return ExecutionResult(success=True, stdout="\n".join(files), returncode=0)

    def _mock_cat(self, args: List[str], cwd: Optional[str]) -> ExecutionResult:
        """Mock cat command."""
        if not args:
            return ExecutionResult(
                success=False, stderr="cat: missing file operand", returncode=1
            )

        filename = args[0]
        if filename in self.files:
            return ExecutionResult(
                success=True, stdout=self.files[filename], returncode=0
            )
        else:
            return ExecutionResult(
                success=False,
                stderr=f"cat: {filename}: No such file or directory",
                returncode=1,
            )

    def _mock_echo(self, args: List[str], cwd: Optional[str]) -> ExecutionResult:
        """Mock echo command."""
        message = " ".join(args)
        return ExecutionResult(success=True, stdout=message, returncode=0)

    def write_file(self, path: str, content: str):
        """
        Write a file in the mock environment.

        Args:
            path: File path
            content: File content
        """
        full_path = self.base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

        # Also store in files dict for quick access
        self.files[path] = content

    def read_file(self, path: str) -> Optional[str]:
        """
        Read a file from the mock environment.

        Args:
            path: File path

        Returns:
            File content or None if not found
        """
        full_path = self.base_path / path
        if full_path.exists():
            return full_path.read_text()
        return self.files.get(path)

    def cleanup(self):
        """Clean up temporary directory."""
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            import shutil

            shutil.rmtree(self.temp_dir)


class ExecutionSimulator:
    """Simulator for code execution in agent tests."""

    @staticmethod
    def create_mock_env(base_path: Optional[str] = None) -> MockExecutionEnvironment:
        """
        Create a mock execution environment.

        Args:
            base_path: Base path (creates temp if None)

        Returns:
            MockExecutionEnvironment instance
        """
        return MockExecutionEnvironment(base_path=base_path)
