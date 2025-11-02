"""
Type definitions for June MCP Client.
"""
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass


@dataclass
class Task:
    """Task data structure."""
    id: int
    project_id: Optional[int]
    title: str
    task_type: Literal["concrete", "abstract", "epic"]
    task_instruction: str
    verification_instruction: str
    task_status: Literal["available", "in_progress", "complete", "blocked", "cancelled"]
    verification_status: Literal["unverified", "verified", "failed"]
    assigned_agent: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create Task from dictionary."""
        return cls(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Task to dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "task_type": self.task_type,
            "task_instruction": self.task_instruction,
            "verification_instruction": self.verification_instruction,
            "task_status": self.task_status,
            "verification_status": self.verification_status,
            "assigned_agent": self.assigned_agent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "notes": self.notes,
            "priority": self.priority,
            "estimated_hours": self.estimated_hours,
            "actual_hours": self.actual_hours,
        }


@dataclass
class Project:
    """Project data structure."""
    id: int
    name: str
    description: Optional[str] = None
    origin_url: Optional[str] = None
    local_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        """Create Project from dictionary."""
        return cls(**data)


@dataclass
class TaskContext:
    """Full task context including project, updates, and ancestry."""
    task: Task
    project: Optional[Project] = None
    updates: List[Dict[str, Any]] = None
    ancestry: List[Task] = None
    recent_changes: List[Dict[str, Any]] = None
    stale_warning: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize default values."""
        if self.updates is None:
            self.updates = []
        if self.ancestry is None:
            self.ancestry = []
        if self.recent_changes is None:
            self.recent_changes = []
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskContext":
        """Create TaskContext from dictionary."""
        task = Task.from_dict(data["task"])
        project = Project.from_dict(data["project"]) if data.get("project") else None
        updates = data.get("updates", [])
        ancestry = [Task.from_dict(t) for t in data.get("ancestry", [])]
        recent_changes = data.get("recent_changes", [])
        stale_warning = data.get("stale_warning")
        
        return cls(
            task=task,
            project=project,
            updates=updates,
            ancestry=ancestry,
            recent_changes=recent_changes,
            stale_warning=stale_warning,
        )


@dataclass
class AgentPerformance:
    """Agent performance statistics."""
    agent_id: str
    tasks_completed: int
    tasks_created: int
    average_completion_hours: Optional[float] = None
    success_rate: Optional[float] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentPerformance":
        """Create AgentPerformance from dictionary."""
        return cls(**data)
