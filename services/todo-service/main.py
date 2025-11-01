"""
TODO Service - REST API for task management.

Provides endpoints for agents to:
- Query tasks (by type, status, etc.)
- Lock tasks (mark in_progress)
- Update tasks (complete, verify, etc.)
- Create tasks and relationships
"""
import os
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from database import TodoDatabase, TaskType, TaskStatus, VerificationStatus, RelationshipType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
db_path = os.getenv("TODO_DB_PATH", "/home/rlee/june_data/todo_service/todos.db")
db = TodoDatabase(db_path)

# Create FastAPI app
app = FastAPI(
    title="TODO Service",
    description="Task management service for AI agents",
    version="0.1.0"
)


# Pydantic models for request/response
class TaskCreate(BaseModel):
    title: str = Field(..., description="Task title")
    task_type: str = Field(..., description="Task type: concrete, abstract, or epic")
    task_instruction: str = Field(..., description="What to do")
    verification_instruction: str = Field(..., description="How to verify completion (idempotent)")
    notes: Optional[str] = Field(None, description="Optional notes")


class TaskUpdate(BaseModel):
    task_status: Optional[str] = None
    verification_status: Optional[str] = None
    notes: Optional[str] = None


class RelationshipCreate(BaseModel):
    parent_task_id: int = Field(..., description="Parent task ID")
    child_task_id: int = Field(..., description="Child task ID")
    relationship_type: str = Field(..., description="Relationship type: subtask, blocking, blocked_by, followup, related")


class TaskResponse(BaseModel):
    """Task response model."""
    id: int
    title: str
    task_type: str
    task_instruction: str
    verification_instruction: str
    task_status: str
    verification_status: str
    assigned_agent: Optional[str]
    created_at: str
    updated_at: str
    completed_at: Optional[str]
    notes: Optional[str]


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "todo-service"}


@app.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate):
    """Create a new task."""
    if task.task_type not in ["concrete", "abstract", "epic"]:
        raise HTTPException(status_code=400, detail="Invalid task_type. Must be: concrete, abstract, or epic")
    
    task_id = db.create_task(
        title=task.title,
        task_type=task.task_type,
        task_instruction=task.task_instruction,
        verification_instruction=task.verification_instruction,
        notes=task.notes
    )
    
    created_task = db.get_task(task_id)
    if not created_task:
        raise HTTPException(status_code=500, detail="Failed to retrieve created task")
    
    return TaskResponse(**created_task)


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    """Get a task by ID."""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskResponse(**task)


@app.get("/tasks", response_model=List[TaskResponse])
async def query_tasks(
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    task_status: Optional[str] = Query(None, description="Filter by task status"),
    assigned_agent: Optional[str] = Query(None, description="Filter by assigned agent"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results")
):
    """Query tasks with filters."""
    if task_type and task_type not in ["concrete", "abstract", "epic"]:
        raise HTTPException(status_code=400, detail="Invalid task_type")
    if task_status and task_status not in ["available", "in_progress", "complete", "blocked", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid task_status")
    
    tasks = db.query_tasks(
        task_type=task_type,
        task_status=task_status,
        assigned_agent=assigned_agent,
        limit=limit
    )
    return [TaskResponse(**task) for task in tasks]


@app.post("/tasks/{task_id}/lock")
async def lock_task(task_id: int, agent_id: str = Body(..., embed=True)):
    """Lock a task for an agent (set to in_progress)."""
    success = db.lock_task(task_id, agent_id)
    if not success:
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} is not available (may be already locked or have different status)"
        )
    return {"message": f"Task {task_id} locked by agent {agent_id}", "task_id": task_id}


@app.post("/tasks/{task_id}/unlock")
async def unlock_task(task_id: int):
    """Unlock a task (set back to available)."""
    db.unlock_task(task_id)
    return {"message": f"Task {task_id} unlocked", "task_id": task_id}


@app.post("/tasks/{task_id}/complete")
async def complete_task(task_id: int, notes: Optional[str] = Body(None, embed=True)):
    """Mark a task as complete."""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    db.complete_task(task_id, notes=notes)
    return {"message": f"Task {task_id} marked as complete", "task_id": task_id}


@app.post("/tasks/{task_id}/verify")
async def verify_task(task_id: int):
    """Mark a task as verified (verification check passed)."""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    if task["task_status"] != "complete":
        raise HTTPException(status_code=400, detail="Task must be complete before verification")
    
    db.verify_task(task_id)
    return {"message": f"Task {task_id} verified", "task_id": task_id}


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, update: TaskUpdate):
    """Update a task (partial update)."""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # Update fields if provided
    if update.task_status:
        if update.task_status not in ["available", "in_progress", "complete", "blocked", "cancelled"]:
            raise HTTPException(status_code=400, detail="Invalid task_status")
        # Use database methods for status changes
        if update.task_status == "complete":
            db.complete_task(task_id, notes=update.notes)
        elif update.task_status == "available":
            db.unlock_task(task_id)
        else:
            # Direct update for other statuses
            conn = db._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tasks 
                    SET task_status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (update.task_status, task_id))
                conn.commit()
            finally:
                conn.close()
    
    if update.verification_status:
        if update.verification_status not in ["unverified", "verified"]:
            raise HTTPException(status_code=400, detail="Invalid verification_status")
        if update.verification_status == "verified":
            db.verify_task(task_id)
        else:
            conn = db._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tasks 
                    SET verification_status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (update.verification_status, task_id))
                conn.commit()
            finally:
                conn.close()
    
    if update.notes:
        conn = db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks 
                SET notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (update.notes, task_id))
            conn.commit()
        finally:
            conn.close()
    
    updated_task = db.get_task(task_id)
    return TaskResponse(**updated_task)


@app.post("/relationships")
async def create_relationship(relationship: RelationshipCreate):
    """Create a relationship between two tasks."""
    if relationship.relationship_type not in ["subtask", "blocking", "blocked_by", "followup", "related"]:
        raise HTTPException(status_code=400, detail="Invalid relationship_type")
    
    # Verify both tasks exist
    parent = db.get_task(relationship.parent_task_id)
    child = db.get_task(relationship.child_task_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"Parent task {relationship.parent_task_id} not found")
    if not child:
        raise HTTPException(status_code=404, detail=f"Child task {relationship.child_task_id} not found")
    
    try:
        rel_id = db.create_relationship(
            parent_task_id=relationship.parent_task_id,
            child_task_id=relationship.child_task_id,
            relationship_type=relationship.relationship_type
        )
        return {"message": "Relationship created", "relationship_id": rel_id}
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail=f"Relationship already exists: {str(e)}")


@app.get("/tasks/{task_id}/relationships")
async def get_task_relationships(task_id: int, relationship_type: Optional[str] = None):
    """Get relationships for a task."""
    relationships = db.get_related_tasks(task_id, relationship_type)
    return {"task_id": task_id, "relationships": relationships}


@app.get("/tasks/{task_id}/blocking")
async def get_blocking_tasks(task_id: int):
    """Get tasks that are blocking the given task."""
    blocking = db.get_blocking_tasks(task_id)
    return {"task_id": task_id, "blocking_tasks": blocking}


@app.get("/agents/{agent_type}/available-tasks")
async def get_available_tasks_for_agent(
    agent_type: str,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results")
):
    """
    Get available tasks for an agent type.
    
    - 'breakdown': Returns abstract/epic tasks that need to be broken down
    - 'implementation': Returns concrete tasks ready for implementation
    """
    if agent_type not in ["breakdown", "implementation"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid agent_type. Must be: breakdown or implementation"
        )
    
    tasks = db.get_available_tasks_for_agent(agent_type, limit=limit)
    return {"agent_type": agent_type, "tasks": [TaskResponse(**task) for task in tasks]}


@app.post("/tasks/{task_id}/add-followup")
async def add_followup_task(task_id: int, followup: TaskCreate):
    """Complete a task and add a followup task."""
    # Verify parent task exists
    parent = db.get_task(task_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"Parent task {task_id} not found")
    
    # Create followup task
    followup_id = db.create_task(
        title=followup.title,
        task_type=followup.task_type,
        task_instruction=followup.task_instruction,
        verification_instruction=followup.verification_instruction,
        notes=followup.notes
    )
    
    # Create followup relationship
    db.create_relationship(
        parent_task_id=task_id,
        child_task_id=followup_id,
        relationship_type="followup"
    )
    
    return {
        "message": f"Followup task created and linked to task {task_id}",
        "parent_task_id": task_id,
        "followup_task_id": followup_id
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("TODO_SERVICE_PORT", "8004"))
    uvicorn.run(app, host="0.0.0.0", port=port)

