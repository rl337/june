"""
Database schema and management for TODO service.
"""
import sqlite3
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Task type enumeration."""
    CONCRETE = "concrete"
    ABSTRACT = "abstract"
    EPIC = "epic"


class TaskStatus(Enum):
    """Task status enumeration."""
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class VerificationStatus(Enum):
    """Verification status enumeration."""
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class RelationshipType(Enum):
    """Task relationship type enumeration."""
    SUBTASK = "subtask"
    BLOCKING = "blocking"
    BLOCKED_BY = "blocked_by"
    FOLLOWUP = "followup"
    RELATED = "related"


class TodoDatabase:
    """SQLite database for TODO management."""
    
    def __init__(self, db_path: str):
        """Initialize database connection and create schema if needed."""
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_schema()
    
    def _ensure_db_directory(self):
        """Ensure database directory exists."""
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign keys
        return conn
    
    def _init_schema(self):
        """Initialize database schema."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Tasks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    task_type TEXT NOT NULL CHECK(task_type IN ('concrete', 'abstract', 'epic')),
                    task_instruction TEXT NOT NULL,
                    verification_instruction TEXT NOT NULL,
                    task_status TEXT NOT NULL DEFAULT 'available' 
                        CHECK(task_status IN ('available', 'in_progress', 'complete', 'blocked', 'cancelled')),
                    verification_status TEXT NOT NULL DEFAULT 'unverified'
                        CHECK(verification_status IN ('unverified', 'verified')),
                    assigned_agent TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    notes TEXT
                )
            """)
            
            # Task relationships table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_task_id INTEGER NOT NULL,
                    child_task_id INTEGER NOT NULL,
                    relationship_type TEXT NOT NULL
                        CHECK(relationship_type IN ('subtask', 'blocking', 'blocked_by', 'followup', 'related')),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (child_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    UNIQUE(parent_task_id, child_task_id, relationship_type)
                )
            """)
            
            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(task_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_agent)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_parent ON task_relationships(parent_task_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_child ON task_relationships(child_task_id)")
            
            conn.commit()
            logger.info(f"Database schema initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise
        finally:
            conn.close()
    
    def create_task(
        self,
        title: str,
        task_type: str,
        task_instruction: str,
        verification_instruction: str,
        notes: Optional[str] = None
    ) -> int:
        """Create a new task and return its ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (title, task_type, task_instruction, verification_instruction, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (title, task_type, task_instruction, verification_instruction, notes))
            task_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Created task {task_id}: {title}")
            return task_id
        finally:
            conn.close()
    
    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get a task by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()
    
    def query_tasks(
        self,
        task_type: Optional[str] = None,
        task_status: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query tasks with filters."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            
            if task_type:
                conditions.append("task_type = ?")
                params.append(task_type)
            if task_status:
                conditions.append("task_status = ?")
                params.append(task_status)
            if assigned_agent:
                conditions.append("assigned_agent = ?")
                params.append(assigned_agent)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query = f"SELECT * FROM tasks {where_clause} ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def lock_task(self, task_id: int, agent_id: str) -> bool:
        """Lock a task for an agent (set to in_progress). Returns True if successful."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Only lock if task is available
            cursor.execute("""
                UPDATE tasks 
                SET task_status = 'in_progress', 
                    assigned_agent = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND task_status = 'available'
            """, (agent_id, task_id))
            success = cursor.rowcount > 0
            conn.commit()
            if success:
                logger.info(f"Task {task_id} locked by agent {agent_id}")
            return success
        finally:
            conn.close()
    
    def unlock_task(self, task_id: int):
        """Unlock a task (set back to available)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks 
                SET task_status = 'available',
                    assigned_agent = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (task_id,))
            conn.commit()
            logger.info(f"Task {task_id} unlocked")
        finally:
            conn.close()
    
    def complete_task(self, task_id: int, notes: Optional[str] = None):
        """Mark a task as complete."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks 
                SET task_status = 'complete',
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    notes = COALESCE(?, notes)
                WHERE id = ?
            """, (notes, task_id))
            conn.commit()
            logger.info(f"Task {task_id} marked as complete")
        finally:
            conn.close()
    
    def verify_task(self, task_id: int) -> bool:
        """Mark a task as verified (verification check passed)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks 
                SET verification_status = 'verified',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (task_id,))
            conn.commit()
            logger.info(f"Task {task_id} verified")
            return True
        finally:
            conn.close()
    
    def create_relationship(
        self,
        parent_task_id: int,
        child_task_id: int,
        relationship_type: str
    ) -> int:
        """Create a relationship between two tasks."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO task_relationships (parent_task_id, child_task_id, relationship_type)
                VALUES (?, ?, ?)
            """, (parent_task_id, child_task_id, relationship_type))
            rel_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Created relationship {relationship_type} from task {parent_task_id} to {child_task_id}")
            
            # Auto-update blocking status
            if relationship_type == "blocked_by":
                cursor.execute("""
                    UPDATE tasks SET task_status = 'blocked', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (parent_task_id,))
                conn.commit()
            
            return rel_id
        finally:
            conn.close()
    
    def get_related_tasks(self, task_id: int, relationship_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get tasks related to a given task."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = ["(parent_task_id = ? OR child_task_id = ?)"]
            params = [task_id, task_id]
            
            if relationship_type:
                conditions.append("relationship_type = ?")
                params.append(relationship_type)
            
            query = f"""
                SELECT tr.*, 
                       t1.title as parent_title,
                       t2.title as child_title
                FROM task_relationships tr
                JOIN tasks t1 ON tr.parent_task_id = t1.id
                JOIN tasks t2 ON tr.child_task_id = t2.id
                WHERE {' AND '.join(conditions)}
            """
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_blocking_tasks(self, task_id: int) -> List[Dict[str, Any]]:
        """Get tasks that are blocking the given task."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.* FROM tasks t
                JOIN task_relationships tr ON t.id = tr.parent_task_id
                WHERE tr.child_task_id = ? AND tr.relationship_type = 'blocked_by'
            """, (task_id,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_available_tasks_for_agent(
        self,
        agent_type: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get available tasks for an agent type.
        
        - 'breakdown': Returns abstract/epic tasks that need to be broken down
        - 'implementation': Returns concrete tasks ready for implementation
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if agent_type == "breakdown":
                # Abstract or epic tasks that are available and have no blocking tasks
                cursor.execute("""
                    SELECT t.* FROM tasks t
                    LEFT JOIN task_relationships tr ON t.id = tr.child_task_id 
                        AND tr.relationship_type = 'blocked_by'
                    WHERE t.task_status = 'available'
                        AND t.task_type IN ('abstract', 'epic')
                        AND tr.id IS NULL
                    ORDER BY t.created_at ASC
                    LIMIT ?
                """, (limit,))
            elif agent_type == "implementation":
                # Concrete tasks that are available and have no blocking tasks
                cursor.execute("""
                    SELECT t.* FROM tasks t
                    LEFT JOIN task_relationships tr ON t.id = tr.child_task_id 
                        AND tr.relationship_type = 'blocked_by'
                    WHERE t.task_status = 'available'
                        AND t.task_type = 'concrete'
                        AND tr.id IS NULL
                    ORDER BY t.created_at ASC
                    LIMIT ?
                """, (limit,))
            else:
                return []
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

