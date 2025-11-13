"""
Agent state models for June.

Provides data models for managing agent state, capabilities, metrics,
execution records, and plans.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class AgentStatus(str, Enum):
    """Agent status enumeration."""

    INIT = "init"
    ACTIVE = "active"
    IDLE = "idle"
    ERROR = "error"


class AgentExecutionOutcome(str, Enum):
    """Agent execution outcome enumeration."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class AgentCapabilities(BaseModel):
    """Agent capabilities model - tools and capabilities available to an agent."""

    tools: List[str] = Field(default_factory=list, description="List of available tools")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Tool metadata and configuration"
    )
    version: Optional[str] = Field(
        default=None, description="Version tracking for capabilities"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "tools": ["code_execution", "git_operations"],
                "metadata": {"version": "1.0"},
                "version": "1.0",
            }
        }


class AgentMetrics(BaseModel):
    """Agent performance metrics model."""

    tasks_completed: int = Field(default=0, description="Number of tasks completed")
    avg_execution_time: float = Field(
        default=0.0, description="Average execution time in seconds"
    )
    success_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Success rate (0.0 to 1.0)"
    )
    total_execution_time: float = Field(
        default=0.0, description="Total execution time in seconds"
    )
    tasks_succeeded: int = Field(default=0, description="Number of successful tasks")
    tasks_failed: int = Field(default=0, description="Number of failed tasks")

    def update_from_task(self, task_duration: float, success: bool) -> None:
        """Update metrics from a completed task."""
        self.tasks_completed += 1
        self.total_execution_time += task_duration

        if success:
            self.tasks_succeeded += 1
        else:
            self.tasks_failed += 1

        # Calculate average execution time
        if self.tasks_completed > 0:
            self.avg_execution_time = self.total_execution_time / self.tasks_completed

        # Calculate success rate
        if self.tasks_completed > 0:
            self.success_rate = self.tasks_succeeded / self.tasks_completed

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "tasks_completed": 10,
                "avg_execution_time": 5.5,
                "success_rate": 0.9,
                "total_execution_time": 55.0,
                "tasks_succeeded": 9,
                "tasks_failed": 1,
            }
        }


class AgentExecutionRecord(BaseModel):
    """Record of individual agent actions."""

    agent_id: str = Field(description="ID of the agent")
    task_id: Optional[str] = Field(
        default=None, description="Reference to task (may be external)"
    )
    action_type: str = Field(
        description="Type of action (e.g., 'task_started', 'task_completed', 'tool_used')"
    )
    outcome: Optional[AgentExecutionOutcome] = Field(
        default=None, description="Outcome of the action"
    )
    duration_ms: Optional[int] = Field(
        default=None, description="Duration in milliseconds"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional action metadata"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp of the record"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "agent_id": "agent-1",
                "task_id": "task-123",
                "action_type": "task_completed",
                "outcome": "success",
                "duration_ms": 5000,
                "metadata": {"tools_used": ["git", "pytest"]},
            }
        }


class AgentPlan(BaseModel):
    """Agent execution plan and strategy model."""

    agent_id: str = Field(description="ID of the agent")
    task_id: Optional[str] = Field(
        default=None, description="Reference to task (may be external)"
    )
    plan_type: str = Field(
        description="Type of plan (e.g., 'task_decomposition', 'execution_plan', 'strategy')"
    )
    plan_data: Dict[str, Any] = Field(
        default_factory=dict, description="Plan structure and details"
    )
    success_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Success rate if plan was reused"
    )
    execution_count: int = Field(
        default=0, description="Number of times plan was executed"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="When plan was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="When plan was last updated"
    )

    def increment_execution(self, success: bool) -> None:
        """Increment execution count and update success rate."""
        self.execution_count += 1
        self.updated_at = datetime.now()

        if self.execution_count > 0:
            if success:
                # Update success rate: weighted average
                # For simplicity, we'll calculate as successful_count / total_count
                # This assumes we track successful_count in plan_data or recalculate
                # In a more sophisticated version, we'd track successful_count separately
                if "successful_count" not in self.plan_data:
                    self.plan_data["successful_count"] = 0

                self.plan_data["successful_count"] += 1
                self.success_rate = (
                    self.plan_data["successful_count"] / self.execution_count
                )
            else:
                # Update successful_count even if it doesn't exist
                if "successful_count" not in self.plan_data:
                    self.plan_data["successful_count"] = 0
                self.success_rate = (
                    self.plan_data["successful_count"] / self.execution_count
                )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "agent_id": "agent-1",
                "task_id": "task-123",
                "plan_type": "execution_plan",
                "plan_data": {
                    "steps": ["step1", "step2", "step3"],
                    "strategy": "sequential",
                },
                "success_rate": 0.85,
                "execution_count": 20,
            }
        }


class AgentState(BaseModel):
    """Agent state model - stores current state of an agent."""

    agent_id: str = Field(description="Unique agent identifier")
    current_task_id: Optional[str] = Field(
        default=None, description="Reference to current task (may be in external TODO service)"
    )
    status: AgentStatus = Field(description="Current agent status")
    capabilities: List[AgentCapabilities] = Field(
        default_factory=list, description="List of agent capabilities"
    )
    metrics: AgentMetrics = Field(
        default_factory=AgentMetrics, description="Agent performance metrics"
    )
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Agent-specific configuration"
    )

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Any) -> AgentStatus:
        """Validate and convert status to enum."""
        if isinstance(v, str):
            try:
                return AgentStatus(v.lower())
            except ValueError:
                raise ValueError(
                    f"Invalid status '{v}'. Must be one of: {[s.value for s in AgentStatus]}"
                )
        return v

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "agent_id": "agent-1",
                "current_task_id": "task-123",
                "status": "active",
                "capabilities": [
                    {
                        "tools": ["code_execution", "git_operations"],
                        "metadata": {"version": "1.0"},
                    }
                ],
                "metrics": {
                    "tasks_completed": 10,
                    "avg_execution_time": 5.5,
                    "success_rate": 0.9,
                },
                "config": {"max_concurrent_tasks": 3},
            }
        }
