from sqlalchemy import Column, String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship, backref # Added backref
from sqlalchemy.ext.declarative import declarative_base
import uuid # For default ID generation
import datetime # For default timestamps

Base = declarative_base() # Base class for SQLAlchemy ORM models.

def generate_uuid() -> str:
    """Generates a hexadecimal UUID string."""
    return uuid.uuid4().hex

class InitiativeORM(Base):
    """SQLAlchemy ORM model for an Initiative."""
    __tablename__ = "initiatives"

    id = Column(String, primary_key=True, default=generate_uuid, help_text="Primary key, UUID hex string.")
    name = Column(String, nullable=False, help_text="Name of the initiative.")
    description = Column(Text, nullable=True, help_text="Optional detailed description of the initiative.")
    status = Column(String, default="pending", nullable=False, help_text="Current status of the initiative (e.g., pending, active, completed).")

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, help_text="Timestamp of creation (UTC).")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False, help_text="Timestamp of last update (UTC), automatically updated.")

    # Relationship to tasks: one initiative has many tasks.
    # - `back_populates="initiative"`: Links to the 'initiative' attribute in TaskORM.
    # - `cascade="all, delete-orphan"`: If an initiative is deleted, its associated tasks are also deleted.
    #   If a task is removed from an initiative's `tasks` collection (and session is flushed),
    #   it becomes an orphan and is deleted if not associated with another parent via other means (not applicable here).
    tasks = relationship("TaskORM", back_populates="initiative", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<InitiativeORM(id='{self.id}', name='{self.name}')>"

class TaskORM(Base):
    """SQLAlchemy ORM model for a Task."""
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=generate_uuid, help_text="Primary key, UUID hex string.")
    description = Column(Text, nullable=False, help_text="Detailed description of the task.")
    status = Column(String, default="pending", nullable=False, help_text="Current status of the task (e.g., pending, assessing, completed).")
    phase = Column(String, default="assessment", nullable=True, help_text="Current processing phase of the task (e.g., assessment, execution). Can be null.")
    result = Column(Text, nullable=True, help_text="Outcome or result of the task if completed.")
    error_message = Column(Text, nullable=True, help_text="Error message if the task failed.")

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, help_text="Timestamp of creation (UTC).")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False, help_text="Timestamp of last update (UTC), automatically updated.")

    # Foreign key to InitiativeORM: Links this task to an initiative.
    initiative_id = Column(String, ForeignKey("initiatives.id"), nullable=True, help_text="ID of the parent initiative, if any.")
    # Relationship back to InitiativeORM.
    # - `back_populates="tasks"`: Links to the 'tasks' attribute in InitiativeORM.
    initiative = relationship("InitiativeORM", back_populates="tasks")

    # Self-referential relationship for subtasks: Links this task to a parent task.
    parent_task_id = Column(String, ForeignKey("tasks.id"), nullable=True, help_text="ID of the parent task, if this is a subtask.")

    # 'subtasks' lists children of the current task (tasks where parent_task_id is this task's id).
    # 'parent_task' attribute will be automatically created on TaskORM by `backref`,
    # referring to the parent TaskORM instance (the task whose id is parent_task_id).
    # - `cascade="all, delete-orphan"`: If a parent task is deleted, its subtasks are also deleted.
    # - `remote_side=[id]`: Specifies that the 'id' column of TaskORM is the "remote side" for the parent part of the relationship.
    #   This means `parent_task` will join where `TaskORM.parent_task_id == parent.id`.
    subtasks = relationship(
        "TaskORM",
        cascade="all, delete-orphan",
        backref=backref("parent_task", remote_side=[id])
    )

    def __repr__(self):
        return f"<TaskORM(id='{self.id}', description='{self.description[:30]}...')>"
