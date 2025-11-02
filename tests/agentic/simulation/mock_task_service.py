"""
Mock Task Service

Simulates TODO MCP Service for agent testing without requiring real service.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    """Task status enumeration."""
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Task type enumeration."""
    CONCRETE = "concrete"
    ABSTRACT = "abstract"
    EPIC = "epic"


@dataclass
class Task:
    """Task data structure."""
    id: int
    project_id: int
    title: str
    task_type: TaskType
    task_instruction: str
    verification_instruction: str
    task_status: TaskStatus
    verification_status: str
    assigned_agent: Optional[str]
    created_at: str
    updated_at: str
    completed_at: Optional[str]
    notes: Optional[str]
    priority: str = "medium"
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    started_at: Optional[str] = None


@dataclass
class TaskUpdate:
    """Task update data structure."""
    id: int
    task_id: int
    agent_id: str
    content: str
    update_type: str
    created_at: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class Project:
    """Project data structure."""
    id: int
    name: str
    description: str
    origin_url: str
    local_path: str
    created_at: str
    updated_at: str


class MockTaskService:
    """Mock TODO MCP Service for testing."""
    
    def __init__(self):
        """Initialize mock service with empty data."""
        self.tasks: Dict[int, Task] = {}
        self.projects: Dict[int, Project] = {}
        self.updates: Dict[int, List[TaskUpdate]] = {}
        self.task_id_counter = 1
        self.update_id_counter = 1
        
        # Track operations
        self.reserve_calls: List[Dict] = []
        self.complete_calls: List[Dict] = []
        self.unlock_calls: List[Dict] = []
    
    def create_project(
        self,
        name: str,
        description: str,
        origin_url: str,
        local_path: str
    ) -> Project:
        """
        Create a new project.
        
        Args:
            name: Project name
            description: Project description
            origin_url: Origin URL
            local_path: Local path
            
        Returns:
            Created project
        """
        project_id = len(self.projects) + 1
        now = datetime.now().isoformat()
        
        project = Project(
            id=project_id,
            name=name,
            description=description,
            origin_url=origin_url,
            local_path=local_path,
            created_at=now,
            updated_at=now
        )
        
        self.projects[project_id] = project
        return project
    
    def create_task(
        self,
        project_id: int,
        title: str,
        task_type: TaskType,
        task_instruction: str,
        verification_instruction: str,
        agent_id: str,
        priority: str = "medium"
    ) -> Task:
        """
        Create a new task.
        
        Args:
            project_id: Project ID
            title: Task title
            task_type: Task type
            task_instruction: Task instructions
            verification_instruction: Verification instructions
            agent_id: Creating agent ID
            priority: Task priority
            
        Returns:
            Created task
        """
        task_id = self.task_id_counter
        self.task_id_counter += 1
        
        now = datetime.now().isoformat()
        
        task = Task(
            id=task_id,
            project_id=project_id,
            title=title,
            task_type=task_type,
            task_instruction=task_instruction,
            verification_instruction=verification_instruction,
            task_status=TaskStatus.AVAILABLE,
            verification_status="unverified",
            assigned_agent=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
            notes=None,
            priority=priority
        )
        
        self.tasks[task_id] = task
        self.updates[task_id] = []
        return task
    
    def list_available_tasks(
        self,
        agent_type: str,
        project_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Task]:
        """
        List available tasks.
        
        Args:
            agent_type: Agent type ('implementation' or 'breakdown')
            project_id: Filter by project ID
            limit: Maximum tasks to return
            
        Returns:
            List of available tasks
        """
        tasks = []
        for task in self.tasks.values():
            if task.task_status != TaskStatus.AVAILABLE:
                continue
            
            if project_id and task.project_id != project_id:
                continue
            
            # Filter by agent type (simple logic)
            if agent_type == "implementation" and task.task_type != TaskType.CONCRETE:
                continue
            if agent_type == "breakdown" and task.task_type == TaskType.CONCRETE:
                continue
            
            tasks.append(task)
        
        return tasks[:limit]
    
    def reserve_task(self, task_id: int, agent_id: str) -> Dict[str, Any]:
        """
        Reserve a task.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID
            
        Returns:
            Task context dictionary
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        if task.task_status != TaskStatus.AVAILABLE:
            raise ValueError(f"Task {task_id} is not available (status: {task.task_status})")
        
        # Reserve the task
        task.task_status = TaskStatus.IN_PROGRESS
        task.assigned_agent = agent_id
        task.started_at = datetime.now().isoformat()
        task.updated_at = datetime.now().isoformat()
        
        self.reserve_calls.append({"task_id": task_id, "agent_id": agent_id})
        
        # Return task context
        project = self.projects.get(task.project_id)
        updates = self.updates.get(task_id, [])
        
        return {
            "success": True,
            "task": asdict(task),
            "project": asdict(project) if project else None,
            "updates": [asdict(u) for u in updates],
            "ancestry": []
        }
    
    def get_task_context(self, task_id: int) -> Dict[str, Any]:
        """
        Get full task context.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task context dictionary
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        project = self.projects.get(task.project_id)
        updates = self.updates.get(task_id, [])
        
        return {
            "success": True,
            "task": asdict(task),
            "project": asdict(project) if project else None,
            "updates": [asdict(u) for u in updates],
            "ancestry": [],
            "recent_changes": []
        }
    
    def add_task_update(
        self,
        task_id: int,
        agent_id: str,
        content: str,
        update_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add task update.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID
            content: Update content
            update_type: Update type
            metadata: Optional metadata
            
        Returns:
            Success status and update ID
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        update_id = self.update_id_counter
        self.update_id_counter += 1
        
        update = TaskUpdate(
            id=update_id,
            task_id=task_id,
            agent_id=agent_id,
            content=content,
            update_type=update_type,
            created_at=datetime.now().isoformat(),
            metadata=metadata
        )
        
        if task_id not in self.updates:
            self.updates[task_id] = []
        
        self.updates[task_id].append(update)
        
        return {
            "success": True,
            "update_id": update_id,
            "task_id": task_id
        }
    
    def complete_task(
        self,
        task_id: int,
        agent_id: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete a task.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID
            notes: Completion notes
            
        Returns:
            Success status
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        if task.assigned_agent != agent_id:
            raise ValueError(f"Task {task_id} is assigned to {task.assigned_agent}, not {agent_id}")
        
        task.task_status = TaskStatus.COMPLETE
        task.completed_at = datetime.now().isoformat()
        task.updated_at = datetime.now().isoformat()
        task.notes = notes
        
        self.complete_calls.append({"task_id": task_id, "agent_id": agent_id, "notes": notes})
        
        return {
            "success": True,
            "task_id": task_id
        }
    
    def unlock_task(self, task_id: int, agent_id: str) -> Dict[str, Any]:
        """
        Unlock a task.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID
            
        Returns:
            Success status
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        if task.assigned_agent != agent_id:
            raise ValueError(f"Task {task_id} is assigned to {task.assigned_agent}, not {agent_id}")
        
        task.task_status = TaskStatus.AVAILABLE
        task.assigned_agent = None
        task.updated_at = datetime.now().isoformat()
        
        self.unlock_calls.append({"task_id": task_id, "agent_id": agent_id})
        
        return {
            "success": True,
            "task_id": task_id
        }
    
    def query_tasks(
        self,
        task_status: Optional[str] = None,
        agent_id: Optional[str] = None,
        project_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Task]:
        """
        Query tasks by criteria.
        
        Args:
            task_status: Filter by status
            agent_id: Filter by assigned agent
            project_id: Filter by project
            limit: Maximum tasks to return
            
        Returns:
            List of matching tasks
        """
        tasks = []
        
        for task in self.tasks.values():
            if task_status and task.task_status.value != task_status:
                continue
            
            if agent_id and task.assigned_agent != agent_id:
                continue
            
            if project_id and task.project_id != project_id:
                continue
            
            tasks.append(task)
        
        return tasks[:limit]
