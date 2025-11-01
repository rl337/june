"""
Client library for TODO service.

Provides a convenient interface for agents to interact with the TODO service.
"""
import httpx
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """Task data class."""
    id: int
    title: str
    task_type: str
    task_instruction: str
    verification_instruction: str
    task_status: str
    verification_status: str
    assigned_agent: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    notes: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create Task from dictionary."""
        return cls(**data)


class TodoClient:
    """Client for interacting with TODO service."""
    
    def __init__(self, base_url: str = "http://todo-service:8004"):
        """Initialize TODO client.
        
        Args:
            base_url: Base URL of TODO service
        """
        self.base_url = base_url.rstrip("/")
    
    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Make HTTP request to TODO service."""
        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json() if response.content else {}
        except httpx.HTTPError as e:
            logger.error(f"TODO service request failed: {e}")
            raise
    
    def create_task(
        self,
        title: str,
        task_type: str,
        task_instruction: str,
        verification_instruction: str,
        notes: Optional[str] = None
    ) -> Task:
        """Create a new task."""
        data = {
            "title": title,
            "task_type": task_type,
            "task_instruction": task_instruction,
            "verification_instruction": verification_instruction,
            "notes": notes
        }
        result = self._request("POST", "/tasks", json=data)
        return Task.from_dict(result)
    
    def get_task(self, task_id: int) -> Task:
        """Get a task by ID."""
        result = self._request("GET", f"/tasks/{task_id}")
        return Task.from_dict(result)
    
    def query_tasks(
        self,
        task_type: Optional[str] = None,
        task_status: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        limit: int = 100
    ) -> List[Task]:
        """Query tasks with filters."""
        params = {"limit": limit}
        if task_type:
            params["task_type"] = task_type
        if task_status:
            params["task_status"] = task_status
        if assigned_agent:
            params["assigned_agent"] = assigned_agent
        
        result = self._request("GET", "/tasks", params=params)
        return [Task.from_dict(task) for task in result]
    
    def lock_task(self, task_id: int, agent_id: str) -> bool:
        """Lock a task for an agent (set to in_progress)."""
        try:
            self._request("POST", f"/tasks/{task_id}/lock", json={"agent_id": agent_id})
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return False  # Task already locked
            raise
    
    def unlock_task(self, task_id: int):
        """Unlock a task (set back to available)."""
        self._request("POST", f"/tasks/{task_id}/unlock")
    
    def complete_task(self, task_id: int, notes: Optional[str] = None):
        """Mark a task as complete."""
        data = {"notes": notes} if notes else {}
        self._request("POST", f"/tasks/{task_id}/complete", json=data)
    
    def verify_task(self, task_id: int):
        """Mark a task as verified."""
        self._request("POST", f"/tasks/{task_id}/verify")
    
    def get_available_tasks(self, agent_type: str, limit: int = 10) -> List[Task]:
        """
        Get available tasks for an agent type.
        
        Args:
            agent_type: 'breakdown' or 'implementation'
            limit: Maximum number of tasks to return
        """
        result = self._request("GET", f"/agents/{agent_type}/available-tasks", params={"limit": limit})
        return [Task.from_dict(task) for task in result["tasks"]]
    
    def create_relationship(
        self,
        parent_task_id: int,
        child_task_id: int,
        relationship_type: str
    ):
        """Create a relationship between two tasks."""
        data = {
            "parent_task_id": parent_task_id,
            "child_task_id": child_task_id,
            "relationship_type": relationship_type
        }
        self._request("POST", "/relationships", json=data)
    
    def add_followup_task(
        self,
        parent_task_id: int,
        title: str,
        task_type: str,
        task_instruction: str,
        verification_instruction: str,
        notes: Optional[str] = None
    ) -> Task:
        """Complete a task and add a followup task."""
        data = {
            "title": title,
            "task_type": task_type,
            "task_instruction": task_instruction,
            "verification_instruction": verification_instruction,
            "notes": notes
        }
        result = self._request("POST", f"/tasks/{parent_task_id}/add-followup", json=data)
        return Task.from_dict({"id": result["followup_task_id"]})


# Convenience function for agents
def get_todo_client(base_url: Optional[str] = None) -> TodoClient:
    """Get a TODO client instance."""
    if base_url is None:
        import os
        base_url = os.getenv("TODO_SERVICE_URL", "http://todo-service:8004")
    return TodoClient(base_url)

