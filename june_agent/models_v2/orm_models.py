from sqlalchemy import Column, String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship, backref # Added backref
from sqlalchemy.ext.declarative import declarative_base
import uuid # For default ID generation
import datetime # For default timestamps

Base = declarative_base()

def generate_uuid():
    return uuid.uuid4().hex

class InitiativeORM(Base):
    __tablename__ = "initiatives"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="pending", nullable=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    # Relationship to tasks: one initiative has many tasks
    tasks = relationship("TaskORM", back_populates="initiative", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<InitiativeORM(id='{self.id}', name='{self.name}')>"

class TaskORM(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=generate_uuid)
    description = Column(Text, nullable=False)
    status = Column(String, default="pending", nullable=False)
    phase = Column(String, default="assessment", nullable=True) # Can be null if task is e.g. completed
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True) # Added from previous fixes

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    # Foreign key to Initiative
    initiative_id = Column(String, ForeignKey("initiatives.id"), nullable=True) # Can be nullable if a task isn't part of an initiative
    # Relationship back to Initiative
    initiative = relationship("InitiativeORM", back_populates="tasks")

    # Self-referential relationship for subtasks
    parent_task_id = Column(String, ForeignKey("tasks.id"), nullable=True)

    # 'subtasks' lists children of the current task.
    # 'parent_task' attribute will be added to TaskORM by backref, referring to the parent.
    subtasks = relationship(
        "TaskORM",
        cascade="all, delete-orphan",
        backref=backref("parent_task", remote_side=[id]) # remote_side is the parent's primary key column (TaskORM.id)
    )

    def __repr__(self):
        return f"<TaskORM(id='{self.id}', description='{self.description[:30]}...')>"
