from pydantic import BaseModel, Field, validator
from typing import Optional, List
import uuid
import datetime

# --- Pydantic Models ---

class TaskBase(BaseModel):
    description: str
    status: str = Field(default="pending")
    phase: Optional[str] = Field(default="assessment")
    result: Optional[str] = None
    error_message: Optional[str] = None
    initiative_id: Optional[str] = None # Handled by relationship in ORM, but useful for creation
    parent_task_id: Optional[str] = None # Same as above

class TaskCreate(TaskBase):
    pass # Specific fields for creation if different from base

class TaskUpdate(BaseModel): # For partial updates
    description: Optional[str] = None
    status: Optional[str] = None
    phase: Optional[str] = None
    result: Optional[str] = None
    error_message: Optional[str] = None
    # initiative_id and parent_task_id are usually not changed after creation

class TaskSchema(TaskBase): # Pydantic model for reading/returning Task data
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    subtask_ids: List[str] = [] # Will be populated from ORM relationship

    class Config:
        orm_mode = True # To enable reading data from ORM models directly

class InitiativeBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = Field(default="pending")

class InitiativeCreate(InitiativeBase):
    pass

class InitiativeUpdate(BaseModel): # For partial updates
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class InitiativeSchema(InitiativeBase): # Pydantic model for reading/returning Initiative data
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    task_ids: List[str] = [] # Will be populated from ORM relationship

    class Config:
        orm_mode = True

# To handle potential circular dependencies if TaskSchema needs InitiativeSchema and vice-versa
# For now, task_ids and subtask_ids are just List[str] which is simpler.
# If they were List[InitiativeSchema] or List[TaskSchema], we'd need:
# TaskSchema.update_forward_refs()
# InitiativeSchema.update_forward_refs()
