"""
Mock Git Operations

Simulates git operations for safe testing without affecting real repositories.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, MagicMock


class MockGit:
    """Mock git operations for testing."""

    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize mock git repository.

        Args:
            repo_path: Path to repository (creates temp dir if None)
        """
        if repo_path:
            self.repo_path = Path(repo_path)
        else:
            self.temp_dir = tempfile.mkdtemp()
            self.repo_path = Path(self.temp_dir)

        self._init_repo()

        # Track operations
        self.commands: List[str] = []
        self.commits: List[Dict] = []
        self.branches: List[str] = ["main"]
        self.current_branch = "main"
        self.status_output = ""

    def _init_repo(self):
        """Initialize mock git repository."""
        if not self.repo_path.exists():
            self.repo_path.mkdir(parents=True, exist_ok=True)

        # Create .git directory
        git_dir = self.repo_path / ".git"
        git_dir.mkdir(exist_ok=True)

        # Create HEAD file
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

        # Create refs/heads
        (git_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)

    def status(self) -> str:
        """Get git status output."""
        self.commands.append("git status")
        return self.status_output

    def status_short(self) -> str:
        """Get short git status output."""
        self.commands.append("git status --short")
        return self.status_output

    def diff(self) -> str:
        """Get git diff output."""
        self.commands.append("git diff")
        return ""

    def commit(self, message: str) -> bool:
        """
        Mock commit operation.

        Args:
            message: Commit message

        Returns:
            True if successful
        """
        self.commands.append(f"git commit -m '{message}'")

        # Validate commit message
        if not message or len(message.strip()) < 3:
            return False

        commit = {
            "message": message,
            "branch": self.current_branch,
            "timestamp": "2025-11-02T10:00:00Z",
        }
        self.commits.append(commit)
        return True

    def push(self, remote: str = "origin", branch: Optional[str] = None) -> bool:
        """
        Mock push operation.

        Args:
            remote: Remote name
            branch: Branch name (uses current branch if None)

        Returns:
            True if successful
        """
        branch_name = branch or self.current_branch
        self.commands.append(f"git push {remote} {branch_name}")
        return True

    def checkout(self, branch: str, create: bool = False) -> bool:
        """
        Mock checkout operation.

        Args:
            branch: Branch name
            create: Create branch if it doesn't exist

        Returns:
            True if successful
        """
        if create or branch in self.branches:
            self.current_branch = branch
            if create and branch not in self.branches:
                self.branches.append(branch)
            self.commands.append(f"git checkout {branch}")
            return True
        return False

    def branch(self, branch: Optional[str] = None, create: bool = False) -> bool:
        """
        Mock branch operation.

        Args:
            branch: Branch name (None to list branches)
            create: Create branch

        Returns:
            True if successful
        """
        if branch:
            if create:
                if branch not in self.branches:
                    self.branches.append(branch)
                self.commands.append(f"git branch {branch}")
                return True
        return True

    def set_status(self, status: str):
        """Set mock status output."""
        self.status_output = status

    def cleanup(self):
        """Clean up temporary directory if created."""
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            import shutil

            shutil.rmtree(self.temp_dir)


class GitSimulator:
    """Simulator for git operations in agent tests."""

    @staticmethod
    def create_mock_repo(path: Optional[str] = None) -> MockGit:
        """
        Create a mock git repository.

        Args:
            path: Repository path (creates temp if None)

        Returns:
            MockGit instance
        """
        return MockGit(repo_path=path)

    @staticmethod
    def patch_git_operations(mock_git: MockGit):
        """
        Patch subprocess to use mock git.

        Args:
            mock_git: MockGit instance to use
        """

        def mock_run(cmd, *args, **kwargs):
            """Mock subprocess.run for git commands."""
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if cmd_str.startswith("git status --short"):
                result = Mock()
                result.returncode = 0
                result.stdout = mock_git.status_short()
                result.stderr = ""
                return result
            elif cmd_str.startswith("git status"):
                result = Mock()
                result.returncode = 0
                result.stdout = mock_git.status()
                result.stderr = ""
                return result
            elif cmd_str.startswith("git diff"):
                result = Mock()
                result.returncode = 0
                result.stdout = mock_git.diff()
                result.stderr = ""
                return result
            elif cmd_str.startswith("git commit"):
                # Extract message
                message = ""
                if "-m" in cmd_str:
                    parts = cmd_str.split("-m")
                    if len(parts) > 1:
                        message = parts[1].strip().strip("'\"")

                success = mock_git.commit(message)
                result = Mock()
                result.returncode = 0 if success else 1
                result.stdout = "Commit successful" if success else "Commit failed"
                result.stderr = ""
                return result
            elif cmd_str.startswith("git push"):
                success = mock_git.push()
                result = Mock()
                result.returncode = 0 if success else 1
                result.stdout = "Push successful" if success else "Push failed"
                result.stderr = ""
                return result
            elif cmd_str.startswith("git checkout"):
                # Extract branch name
                branch = cmd_str.split()[-1]
                success = mock_git.checkout(branch)
                result = Mock()
                result.returncode = 0 if success else 1
                result.stdout = (
                    f"Switched to branch '{branch}'" if success else "Checkout failed"
                )
                result.stderr = ""
                return result
            else:
                # Default: return success
                result = Mock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
                return result

        return mock_run
