"""Session locking for agent coordination."""

import asyncio
import fcntl
import logging
import os
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class SessionLock:
    """Manages locks for agent sessions to prevent concurrent execution."""
    
    def __init__(self, lock_dir: Path):
        """Initialize session lock manager.
        
        Args:
            lock_dir: Directory where lock files are stored
        """
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, int] = {}  # session_id -> file descriptor
    
    def _get_lock_file(self, session_id: str) -> Path:
        """Get lock file path for a session."""
        return self.lock_dir / f"{session_id}.lock"
    
    async def acquire(self, session_id: str, timeout: float = 30.0) -> bool:
        """Acquire a lock for a session.
        
        Args:
            session_id: Session identifier
            timeout: Maximum time to wait for lock (seconds)
            
        Returns:
            True if lock was acquired, False otherwise
        """
        lock_file = self._get_lock_file(session_id)
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        start_time = datetime.utcnow()
        
        while True:
            try:
                # Try to open and lock the file
                fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL)
                
                # Write lock metadata
                lock_data = {
                    "session_id": session_id,
                    "acquired_at": datetime.utcnow().isoformat(),
                    "pid": os.getpid()
                }
                os.write(fd, json.dumps(lock_data).encode())
                os.fsync(fd)
                
                self._locks[session_id] = fd
                logger.debug(f"Acquired lock for session {session_id}")
                return True
                
            except FileExistsError:
                # Lock file exists, check if it's stale
                if await self._is_lock_stale(lock_file, timeout):
                    # Remove stale lock
                    try:
                        lock_file.unlink()
                        continue
                    except OSError:
                        pass
                
                # Check if we've exceeded timeout
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                if elapsed >= timeout:
                    logger.warning(f"Timeout waiting for lock on session {session_id}")
                    return False
                
                # Wait a bit before retrying
                await asyncio.sleep(0.1)
                
            except OSError as e:
                logger.error(f"Error acquiring lock for session {session_id}: {e}")
                return False
    
    async def release(self, session_id: str) -> bool:
        """Release a lock for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if lock was released, False otherwise
        """
        if session_id not in self._locks:
            return False
        
        try:
            fd = self._locks[session_id]
            os.close(fd)
            del self._locks[session_id]
            
            lock_file = self._get_lock_file(session_id)
            if lock_file.exists():
                lock_file.unlink()
            
            logger.debug(f"Released lock for session {session_id}")
            return True
            
        except OSError as e:
            logger.error(f"Error releasing lock for session {session_id}: {e}")
            return False
    
    async def _is_lock_stale(self, lock_file: Path, timeout: float) -> bool:
        """Check if a lock file is stale (process no longer exists).
        
        Args:
            lock_file: Path to lock file
            timeout: Timeout in seconds
            
        Returns:
            True if lock is stale
        """
        try:
            # Read lock metadata
            with open(lock_file, 'r') as f:
                lock_data = json.load(f)
            
            pid = lock_data.get("pid")
            if pid:
                # Check if process exists
                try:
                    os.kill(pid, 0)  # Signal 0 just checks if process exists
                    return False
                except ProcessLookupError:
                    # Process doesn't exist, lock is stale
                    return True
            
            # Check if lock file is older than timeout
            acquired_at_str = lock_data.get("acquired_at")
            if acquired_at_str:
                acquired_at = datetime.fromisoformat(acquired_at_str)
                age = (datetime.utcnow() - acquired_at).total_seconds()
                return age > timeout
            
            return True
            
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            # If we can't read the lock file, consider it stale
            return True
    
    async def is_locked(self, session_id: str) -> bool:
        """Check if a session is currently locked.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session is locked
        """
        lock_file = self._get_lock_file(session_id)
        if not lock_file.exists():
            return False
        
        # Check if lock is stale
        if await self._is_lock_stale(lock_file, timeout=3600.0):
            return False
        
        return True
    
    async def cleanup_stale_locks(self) -> int:
        """Clean up stale lock files.
        
        Returns:
            Number of locks cleaned up
        """
        cleaned = 0
        for lock_file in self.lock_dir.glob("*.lock"):
            if await self._is_lock_stale(lock_file, timeout=3600.0):
                try:
                    lock_file.unlink()
                    cleaned += 1
                except OSError:
                    pass
        
        return cleaned

