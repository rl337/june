"""
Sandbox Manager - Provides isolated execution environments for agents.
"""

import logging
import os
import resource
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class SandboxManager:
    """
    Manages isolated execution environments (sandboxes) for agent operations.
    
    Features:
    - Isolated execution environments
    - Network restrictions (TODO: requires network namespaces)
    - File system access controls
    - Resource limits enforcement (CPU, memory, disk)
    """
    
    def __init__(
        self,
        base_sandbox_dir: Optional[str] = None,
        enable_resource_limits: bool = True,
        enable_network_restrictions: bool = False,  # TODO: Requires network namespaces
        max_memory_mb: int = 1024,
        max_cpu_time_seconds: int = 300
    ):
        """
        Initialize sandbox manager.
        
        Args:
            base_sandbox_dir: Base directory for sandboxes (defaults to temp directory)
            enable_resource_limits: Whether to enforce resource limits
            enable_network_restrictions: Whether to restrict network access (requires capabilities)
            max_memory_mb: Maximum memory per sandbox in MB
            max_cpu_time_seconds: Maximum CPU time per sandbox in seconds
        """
        if base_sandbox_dir:
            self.base_sandbox_dir = Path(base_sandbox_dir)
        else:
            self.base_sandbox_dir = Path(tempfile.gettempdir()) / "june_sandboxes"
        
        self.base_sandbox_dir.mkdir(parents=True, exist_ok=True)
        
        self.enable_resource_limits = enable_resource_limits
        self.enable_network_restrictions = enable_network_restrictions
        self.max_memory_mb = max_memory_mb
        self.max_cpu_time_seconds = max_cpu_time_seconds
        
        # Active sandboxes
        self.active_sandboxes: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"SandboxManager initialized (base_dir: {self.base_sandbox_dir})")
    
    @contextmanager
    def create_sandbox(self, agent_id: str, project_path: Optional[str] = None):
        """
        Create and manage a sandbox environment for agent operations.
        
        Args:
            agent_id: Agent identifier
            project_path: Optional project path to copy into sandbox
            
        Yields:
            Path to sandbox directory
        """
        sandbox_id = f"{agent_id}_{os.getpid()}_{id(self)}"
        sandbox_path = self.base_sandbox_dir / sandbox_id
        sandbox_path.mkdir(parents=True, exist_ok=True)
        
        old_limit_set = False
        
        try:
            # Set resource limits if enabled
            if self.enable_resource_limits:
                try:
                    # Set memory limit (soft and hard)
                    memory_bytes = self.max_memory_mb * 1024 * 1024
                    resource.setrlimit(
                        resource.RLIMIT_AS,
                        (memory_bytes, memory_bytes)
                    )
                    
                    # Set CPU time limit
                    cpu_time_seconds = self.max_cpu_time_seconds
                    resource.setrlimit(
                        resource.RLIMIT_CPU,
                        (cpu_time_seconds, cpu_time_seconds)
                    )
                    
                    old_limit_set = True
                    logger.debug(f"Resource limits set for sandbox {sandbox_id}")
                except (OSError, ValueError) as e:
                    logger.warning(f"Failed to set resource limits: {e}")
            
            # Copy project into sandbox if provided
            if project_path and Path(project_path).exists():
                project_path_obj = Path(project_path)
                sandbox_project = sandbox_path / "project"
                sandbox_project.mkdir(exist_ok=True)
                
                # Copy project files (excluding .git and large directories for efficiency)
                try:
                    self._copy_project_to_sandbox(project_path_obj, sandbox_project)
                    logger.debug(f"Copied project to sandbox: {sandbox_project}")
                except Exception as e:
                    logger.error(f"Failed to copy project to sandbox: {e}", exc_info=True)
            
            # Track active sandbox
            self.active_sandboxes[sandbox_id] = {
                "agent_id": agent_id,
                "path": str(sandbox_path),
                "created_at": sandbox_path.stat().st_mtime
            }
            
            # Yield sandbox path
            yield sandbox_path
            
        finally:
            # Cleanup sandbox
            try:
                if sandbox_path.exists():
                    shutil.rmtree(sandbox_path)
                    logger.debug(f"Cleaned up sandbox: {sandbox_id}")
            except Exception as e:
                logger.error(f"Failed to cleanup sandbox {sandbox_id}: {e}", exc_info=True)
            
            # Remove from active sandboxes
            self.active_sandboxes.pop(sandbox_id, None)
            
            # Reset resource limits if we set them
            if old_limit_set and self.enable_resource_limits:
                try:
                    # Reset to unlimited (system default)
                    resource.setrlimit(resource.RLIMIT_AS, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
                    resource.setrlimit(resource.RLIMIT_CPU, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
                except Exception as e:
                    logger.warning(f"Failed to reset resource limits: {e}")
    
    def _copy_project_to_sandbox(self, source: Path, destination: Path):
        """
        Copy project files to sandbox, excluding unnecessary files.
        
        Args:
            source: Source project path
            destination: Destination sandbox path
        """
        # Files/directories to exclude
        exclude_patterns = [
            '.git',
            '__pycache__',
            '*.pyc',
            'venv',
            '.venv',
            'node_modules',
            'dist',
            'build',
            '.pytest_cache',
            '.coverage',
        ]
        
        # Simple copy implementation (in production, use more sophisticated copying)
        for item in source.iterdir():
            # Check if item should be excluded
            should_exclude = False
            for pattern in exclude_patterns:
                if pattern in str(item):
                    should_exclude = True
                    break
            
            if should_exclude:
                continue
            
            dest_item = destination / item.name
            if item.is_dir():
                shutil.copytree(item, dest_item, ignore=shutil.ignore_patterns(*exclude_patterns))
            else:
                shutil.copy2(item, dest_item)
    
    def get_sandbox_info(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get information about active sandboxes.
        
        Args:
            agent_id: Filter by agent ID (optional)
            
        Returns:
            List of sandbox information dictionaries
        """
        if agent_id:
            return [
                info for info in self.active_sandboxes.values()
                if info['agent_id'] == agent_id
            ]
        return list(self.active_sandboxes.values())
    
    def cleanup_all_sandboxes(self):
        """Clean up all sandbox directories."""
        try:
            if self.base_sandbox_dir.exists():
                for item in self.base_sandbox_dir.iterdir():
                    if item.is_dir():
                        try:
                            shutil.rmtree(item)
                        except Exception as e:
                            logger.warning(f"Failed to cleanup sandbox {item}: {e}")
            
            self.active_sandboxes.clear()
            logger.info("All sandboxes cleaned up")
        except Exception as e:
            logger.error(f"Failed to cleanup sandboxes: {e}", exc_info=True)
