"""
Git operation tools with validation.
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from june_agent_tools.tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class GitStatusTool(Tool):
    """Tool for getting git status."""
    
    @property
    def name(self) -> str:
        return "git_status"
    
    @property
    def description(self) -> str:
        return "Get git repository status (modified, staged, untracked files)"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository root",
                    "default": "."
                },
                "short": {
                    "type": "boolean",
                    "description": "Use short format output",
                    "default": True
                }
            },
            "required": []
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate repo_path parameter."""
        repo_path = params.get("repo_path", ".")
        if not isinstance(repo_path, str):
            return False
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute git status command."""
        repo_path = Path(params.get("repo_path", ".")).resolve()
        short = params.get("short", True)
        
        try:
            if not (repo_path / ".git").exists() and not (repo_path.parent / ".git").exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Not a git repository: {repo_path}"
                )
            
            cmd = ["git", "status"]
            if short:
                cmd.append("--short")
            
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Git status failed: {result.stderr}"
                )
            
            return ToolResult(
                success=True,
                output=result.stdout,
                metadata={
                    "repo_path": str(repo_path),
                    "exit_code": result.returncode
                }
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Git status command timed out"
            )
        except Exception as e:
            logger.error(f"Error running git status: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error running git status: {str(e)}"
            )


class GitCommitTool(Tool):
    """Tool for committing changes with message validation."""
    
    @property
    def name(self) -> str:
        return "git_commit"
    
    @property
    def description(self) -> str:
        return "Commit changes with validated commit message"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository root",
                    "default": "."
                },
                "message": {
                    "type": "string",
                    "description": "Commit message (must be descriptive, min 10 chars)"
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific files to commit (optional, commits all staged if not provided)"
                },
                "stage_all": {
                    "type": "boolean",
                    "description": "Stage all changes before committing",
                    "default": False
                }
            },
            "required": ["message"]
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate commit parameters."""
        if "message" not in params:
            return False
        message = params["message"]
        if not isinstance(message, str) or len(message.strip()) < 10:
            return False
        
        # Reject generic messages
        generic_messages = ["fix", "update", "change", "wip", "test", "commit"]
        if message.strip().lower() in generic_messages:
            return False
        
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute git commit."""
        repo_path = Path(params.get("repo_path", ".")).resolve()
        message = params["message"]
        files = params.get("files", [])
        stage_all = params.get("stage_all", False)
        
        try:
            if not (repo_path / ".git").exists() and not (repo_path.parent / ".git").exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Not a git repository: {repo_path}"
                )
            
            # Stage files if needed
            if stage_all:
                stage_result = subprocess.run(
                    ["git", "add", "-A"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if stage_result.returncode != 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Failed to stage files: {stage_result.stderr}"
                    )
            elif files:
                stage_result = subprocess.run(
                    ["git", "add"] + files,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if stage_result.returncode != 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Failed to stage files: {stage_result.stderr}"
                    )
            
            # Commit
            commit_result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if commit_result.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Git commit failed: {commit_result.stderr}"
                )
            
            return ToolResult(
                success=True,
                output=commit_result.stdout,
                metadata={
                    "repo_path": str(repo_path),
                    "message": message,
                    "exit_code": commit_result.returncode
                }
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Git commit command timed out"
            )
        except Exception as e:
            logger.error(f"Error running git commit: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error running git commit: {str(e)}"
            )


class GitPushTool(Tool):
    """Tool for pushing to remote repository."""
    
    @property
    def name(self) -> str:
        return "git_push"
    
    @property
    def description(self) -> str:
        return "Push commits to remote repository (force push to main/master blocked)"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository root",
                    "default": "."
                },
                "remote": {
                    "type": "string",
                    "description": "Remote name",
                    "default": "origin"
                },
                "branch": {
                    "type": "string",
                    "description": "Branch to push",
                    "default": "current branch"
                }
            },
            "required": []
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate push parameters."""
        # Force push to main/master is blocked by security validator
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute git push."""
        repo_path = Path(params.get("repo_path", ".")).resolve()
        remote = params.get("remote", "origin")
        branch = params.get("branch")
        
        try:
            if not (repo_path / ".git").exists() and not (repo_path.parent / ".git").exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Not a git repository: {repo_path}"
                )
            
            # Get current branch if not specified
            if not branch:
                branch_result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if branch_result.returncode != 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Failed to get current branch: {branch_result.stderr}"
                    )
                branch = branch_result.stdout.strip()
            
            # Build push command
            push_cmd = ["git", "push", remote, branch]
            
            push_result = subprocess.run(
                push_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if push_result.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Git push failed: {push_result.stderr}"
                )
            
            return ToolResult(
                success=True,
                output=push_result.stdout,
                metadata={
                    "repo_path": str(repo_path),
                    "remote": remote,
                    "branch": branch,
                    "exit_code": push_result.returncode
                }
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Git push command timed out"
            )
        except Exception as e:
            logger.error(f"Error running git push: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error running git push: {str(e)}"
            )


class GitBranchTool(Tool):
    """Tool for creating and switching branches."""
    
    @property
    def name(self) -> str:
        return "git_branch"
    
    @property
    def description(self) -> str:
        return "Create or switch git branches"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository root",
                    "default": "."
                },
                "action": {
                    "type": "string",
                    "enum": ["create", "switch", "list"],
                    "description": "Branch action to perform"
                },
                "branch_name": {
                    "type": "string",
                    "description": "Branch name (required for create/switch)"
                }
            },
            "required": ["action"]
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate branch parameters."""
        action = params.get("action")
        if action not in ["create", "switch", "list"]:
            return False
        if action in ["create", "switch"] and "branch_name" not in params:
            return False
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute git branch operation."""
        repo_path = Path(params.get("repo_path", ".")).resolve()
        action = params["action"]
        branch_name = params.get("branch_name")
        
        try:
            if not (repo_path / ".git").exists() and not (repo_path.parent / ".git").exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Not a git repository: {repo_path}"
                )
            
            if action == "list":
                result = subprocess.run(
                    ["git", "branch"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            elif action == "create":
                result = subprocess.run(
                    ["git", "checkout", "-b", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            elif action == "switch":
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown action: {action}"
                )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Git branch operation failed: {result.stderr}"
                )
            
            return ToolResult(
                success=True,
                output=result.stdout,
                metadata={
                    "repo_path": str(repo_path),
                    "action": action,
                    "branch_name": branch_name,
                    "exit_code": result.returncode
                }
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Git branch command timed out"
            )
        except Exception as e:
            logger.error(f"Error running git branch: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error running git branch: {str(e)}"
            )


class GitDiffTool(Tool):
    """Tool for getting git diff."""
    
    @property
    def name(self) -> str:
        return "git_diff"
    
    @property
    def description(self) -> str:
        return "Get git diff (changes between commits, working directory, etc.)"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository root",
                    "default": "."
                },
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes",
                    "default": False
                },
                "file": {
                    "type": "string",
                    "description": "Specific file to diff (optional)"
                }
            },
            "required": []
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate diff parameters."""
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute git diff."""
        repo_path = Path(params.get("repo_path", ".")).resolve()
        staged = params.get("staged", False)
        file = params.get("file")
        
        try:
            if not (repo_path / ".git").exists() and not (repo_path.parent / ".git").exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Not a git repository: {repo_path}"
                )
            
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--staged")
            if file:
                cmd.append(file)
            
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Git diff returns non-zero exit code if there are no changes
            # This is normal, so we check stderr for actual errors
            if result.stderr and "fatal" in result.stderr.lower():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Git diff failed: {result.stderr}"
                )
            
            return ToolResult(
                success=True,
                output=result.stdout,
                metadata={
                    "repo_path": str(repo_path),
                    "staged": staged,
                    "file": file,
                    "has_changes": bool(result.stdout.strip())
                }
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Git diff command timed out"
            )
        except Exception as e:
            logger.error(f"Error running git diff: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error running git diff: {str(e)}"
            )
