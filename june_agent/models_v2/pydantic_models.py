from pydantic import BaseModel, Field, validator
from typing import Optional, List
import uuid
import datetime

# --- Pydantic Models ---
# These models define the data structures for API requests and responses,
# and for transferring data between service layers and domain objects.
# They use Pydantic for data validation and serialization.

class TaskBase(BaseModel):
    """Base Pydantic model for Task attributes. Used for common fields in TaskCreate and TaskSchema."""
    description: str
    status: str = Field(default="pending")
    phase: Optional[str] = Field(default="assessment")
    result: Optional[str] = None
    error_message: Optional[str] = None
    initiative_id: Optional[str] = None # ID of the parent initiative, if any.
    parent_task_id: Optional[str] = None # ID of the parent task, if this is a subtask.

class TaskCreate(TaskBase):
    """Pydantic model for creating a new Task. Inherits all fields from TaskBase."""
    # Currently, no additional fields beyond TaskBase are needed for creation.
    # initiative_id is expected to be passed separately to service creation methods for clarity,
    # but it's part of TaskBase for cases where it might be included in a broader DTO.
    pass

class TaskUpdate(BaseModel):
    """Pydantic model for updating an existing Task. All fields are optional for partial updates."""
    description: Optional[str] = None
    status: Optional[str] = None
    phase: Optional[str] = None
    result: Optional[str] = None
    error_message: Optional[str] = None
    # initiative_id and parent_task_id are typically not changed after task creation via this model.

class TaskSchema(TaskBase):
    """Pydantic model for representing a Task in API responses (reading Task data)."""
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    subtask_ids: List[str] = Field(default_factory=list) # IDs of subtasks associated with this task.

    class Config:
        """Pydantic configuration options."""
        from_attributes = True # Enables creating this schema from ORM objects directly.

class InitiativeBase(BaseModel):
    """Base Pydantic model for Initiative attributes."""
    name: str
    description: Optional[str] = None
    status: str = Field(default="pending") # Default status for new initiatives.

class InitiativeCreate(InitiativeBase):
    """Pydantic model for creating a new Initiative."""
    pass

class InitiativeUpdate(BaseModel):
    """Pydantic model for updating an existing Initiative. All fields are optional."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class InitiativeSchema(InitiativeBase):
    """Pydantic model for representing an Initiative in API responses."""
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    task_ids: List[str] = Field(default_factory=list) # IDs of tasks associated with this initiative.

    class Config:
        """Pydantic configuration options."""
        from_attributes = True # Enables creating this schema from ORM objects directly.

# To handle potential circular dependencies if TaskSchema needs InitiativeSchema and vice-versa
# For now, task_ids and subtask_ids are just List[str] which is simpler.
# If they were List[InitiativeSchema] or List[TaskSchema], we'd need:
# TaskSchema.update_forward_refs()
# InitiativeSchema.update_forward_refs()
