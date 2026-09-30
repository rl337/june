"""Persistent goals — first-class June state that outlives sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class GoalStatus(str, Enum):
    ACTIVE = "active"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Goal:
    """Durable goal identity and wake/completion state."""

    title: str
    completion_criteria: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: GoalStatus = GoalStatus.ACTIVE
    priority: int = 0
    triggers: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    run_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class GoalStore:
    """In-memory goal store for scaffolding; replace with durable persistence."""

    def __init__(self) -> None:
        self._goals: dict[str, Goal] = {}

    def put(self, goal: Goal) -> Goal:
        goal.updated_at = datetime.now(timezone.utc)
        self._goals[goal.id] = goal
        return goal

    def get(self, goal_id: str) -> Goal | None:
        return self._goals.get(goal_id)

    def list(self, *, status: GoalStatus | None = None) -> list[Goal]:
        goals = list(self._goals.values())
        if status is not None:
            goals = [g for g in goals if g.status is status]
        return sorted(goals, key=lambda g: (-g.priority, g.created_at))
