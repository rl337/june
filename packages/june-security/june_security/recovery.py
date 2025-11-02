"""
Recovery and Rollback System - Automatic rollback on failures and recovery procedures.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RecoveryAction(Enum):
    """Types of recovery actions."""
    ROLLBACK = "rollback"
    RESTORE = "restore"
    BACKUP = "backup"
    VERIFY = "verify"


class RecoveryManager:
    """
    Manages rollback, recovery, and backup operations.
    
    Features:
    - Automatic rollback on failures
    - Backup before destructive operations
    - Recovery procedures
    - State restoration
    """
    
    def __init__(
        self,
        backup_dir: Optional[str] = None,
        enable_auto_backup: bool = True,
        enable_auto_rollback: bool = True
    ):
        """
        Initialize recovery manager.
        
        Args:
            backup_dir: Directory for storing backups (defaults to .june_backups)
            enable_auto_backup: Whether to automatically backup before destructive operations
            enable_auto_rollback: Whether to automatically rollback on failures
        """
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            self.backup_dir = Path(".june_backups")
        
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.enable_auto_backup = enable_auto_backup
        self.enable_auto_rollback = enable_auto_rollback
        
        # Track backups
        self.backups: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"RecoveryManager initialized (backup_dir: {self.backup_dir})")
    
    def create_backup(
        self,
        project_path: str,
        backup_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> str:
        """
        Create a backup of project state.
        
        Args:
            project_path: Path to project directory
            backup_name: Optional backup name (auto-generated if not provided)
            description: Optional backup description
            
        Returns:
            Backup ID
        """
        project_path_obj = Path(project_path)
        if not project_path_obj.exists():
            raise ValueError(f"Project path does not exist: {project_path}")
        
        if not backup_name:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"
        
        backup_path = self.backup_dir / backup_name
        
        try:
            # Create backup directory
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # Copy project to backup (excluding .git for efficiency)
            project_dest = backup_path / "project"
            shutil.copytree(
                project_path_obj,
                project_dest,
                ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', 'venv', '.venv', 'node_modules')
            )
            
            # Save backup metadata
            backup_id = str(backup_path.name)
            self.backups[backup_id] = {
                "backup_id": backup_id,
                "backup_path": str(backup_path),
                "project_path": project_path,
                "created_at": datetime.utcnow().isoformat(),
                "description": description or "",
                "size": self._get_directory_size(backup_path)
            }
            
            logger.info(f"Created backup: {backup_id} at {backup_path}")
            
            return backup_id
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}", exc_info=True)
            raise
    
    def restore_backup(
        self,
        backup_id: str,
        restore_path: Optional[str] = None,
        overwrite: bool = False
    ) -> bool:
        """
        Restore a backup.
        
        Args:
            backup_id: Backup ID to restore
            restore_path: Path to restore to (uses original project path if not provided)
            overwrite: Whether to overwrite existing files
            
        Returns:
            True if restore succeeded
        """
        if backup_id not in self.backups:
            raise ValueError(f"Backup not found: {backup_id}")
        
        backup_info = self.backups[backup_id]
        backup_path = Path(backup_info["backup_path"])
        
        if not backup_path.exists():
            raise ValueError(f"Backup directory does not exist: {backup_path}")
        
        restore_to = restore_path or backup_info["project_path"]
        restore_path_obj = Path(restore_to)
        
        if restore_path_obj.exists() and not overwrite:
            raise ValueError(f"Restore path exists and overwrite=False: {restore_to}")
        
        try:
            # Remove existing restore path if overwriting
            if restore_path_obj.exists() and overwrite:
                shutil.rmtree(restore_path_obj)
            
            # Restore from backup
            project_backup = backup_path / "project"
            if project_backup.exists():
                shutil.copytree(project_backup, restore_path_obj)
                logger.info(f"Restored backup {backup_id} to {restore_to}")
                return True
            else:
                logger.error(f"Backup project directory not found: {project_backup}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to restore backup {backup_id}: {e}", exc_info=True)
            raise
    
    def rollback_git_state(
        self,
        project_path: str,
        commit_hash: Optional[str] = None
    ) -> bool:
        """
        Rollback git state to a previous commit.
        
        Args:
            project_path: Path to project directory
            commit_hash: Commit hash to rollback to (defaults to HEAD~1)
            
        Returns:
            True if rollback succeeded
        """
        project_path_obj = Path(project_path)
        git_dir = project_path_obj / ".git"
        
        if not git_dir.exists():
            logger.warning(f"Not a git repository: {project_path}")
            return False
        
        try:
            if commit_hash:
                # Rollback to specific commit
                result = subprocess.run(
                    ["git", "reset", "--hard", commit_hash],
                    cwd=project_path_obj,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            else:
                # Rollback to previous commit
                result = subprocess.run(
                    ["git", "reset", "--hard", "HEAD~1"],
                    cwd=project_path_obj,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            
            if result.returncode == 0:
                logger.info(f"Git rollback successful: {project_path}")
                return True
            else:
                logger.error(f"Git rollback failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Git rollback timed out: {project_path}")
            return False
        except Exception as e:
            logger.error(f"Git rollback error: {e}", exc_info=True)
            return False
    
    def verify_backup(self, backup_id: str) -> bool:
        """
        Verify a backup is valid.
        
        Args:
            backup_id: Backup ID to verify
            
        Returns:
            True if backup is valid
        """
        if backup_id not in self.backups:
            return False
        
        backup_info = self.backups[backup_id]
        backup_path = Path(backup_info["backup_path"])
        
        if not backup_path.exists():
            return False
        
        project_backup = backup_path / "project"
        return project_backup.exists() and project_backup.is_dir()
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """
        List all available backups.
        
        Returns:
            List of backup information dictionaries
        """
        return list(self.backups.values())
    
    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """
        Clean up old backups, keeping only the most recent N.
        
        Args:
            keep_count: Number of backups to keep
            
        Returns:
            Number of backups removed
        """
        if len(self.backups) <= keep_count:
            return 0
        
        # Sort backups by creation time
        sorted_backups = sorted(
            self.backups.items(),
            key=lambda x: x[1]["created_at"],
            reverse=True
        )
        
        # Remove old backups
        removed_count = 0
        for backup_id, backup_info in sorted_backups[keep_count:]:
            try:
                backup_path = Path(backup_info["backup_path"])
                if backup_path.exists():
                    shutil.rmtree(backup_path)
                del self.backups[backup_id]
                removed_count += 1
            except Exception as e:
                logger.warning(f"Failed to remove backup {backup_id}: {e}")
        
        logger.info(f"Cleaned up {removed_count} old backups")
        return removed_count
    
    def _get_directory_size(self, path: Path) -> int:
        """Calculate total size of directory in bytes."""
        total_size = 0
        try:
            for item in path.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
        except Exception as e:
            logger.warning(f"Failed to calculate directory size: {e}")
        return total_size
    
    def auto_backup_before_destructive_operation(
        self,
        project_path: str,
        operation_description: str
    ) -> Optional[str]:
        """
        Automatically create backup before destructive operation.
        
        Args:
            project_path: Path to project
            operation_description: Description of operation
            
        Returns:
            Backup ID if backup was created
        """
        if not self.enable_auto_backup:
            return None
        
        try:
            backup_id = self.create_backup(
                project_path=project_path,
                description=f"Auto-backup before: {operation_description}"
            )
            logger.info(f"Auto-backup created: {backup_id} for operation: {operation_description}")
            return backup_id
        except Exception as e:
            logger.error(f"Failed to create auto-backup: {e}", exc_info=True)
            return None
    
    def auto_rollback_on_failure(
        self,
        project_path: str,
        backup_id: Optional[str] = None
    ) -> bool:
        """
        Automatically rollback on failure.
        
        Args:
            project_path: Path to project
            backup_id: Optional backup ID to restore from
            
        Returns:
            True if rollback succeeded
        """
        if not self.enable_auto_rollback:
            return False
        
        if backup_id:
            # Restore from specific backup
            try:
                return self.restore_backup(backup_id, restore_path=project_path, overwrite=True)
            except Exception as e:
                logger.error(f"Failed to restore from backup {backup_id}: {e}", exc_info=True)
                return False
        else:
            # Try git rollback
            return self.rollback_git_state(project_path)
