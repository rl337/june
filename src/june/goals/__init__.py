"""Persistent goals — first-class June state that outlives sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


class GoalStatus(str, Enum):
    ACTIVE = "active"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GoalTransition:
    from_status: str
    to_status: str
    reason: str
    at: str
    actor: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Goal:
    """Durable goal identity, wake/completion state, and steering history."""

    title: str
    completion_criteria: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: GoalStatus = GoalStatus.ACTIVE
    priority: int = 0
    triggers: list[str] = field(default_factory=list)
    subscriptions: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    run_ids: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Goal:
        payload = dict(data)
        payload["status"] = GoalStatus(payload.get("status", GoalStatus.ACTIVE.value))
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


class GoalStore:
    """Durable goal store with recorded steering transitions."""

    def __init__(self, store: JsonStore | None = None) -> None:
        self._memory: dict[str, Goal] = {}
        self._store = store

    def put(self, goal: Goal) -> Goal:
        goal.updated_at = datetime.now(timezone.utc).isoformat()
        self._memory[goal.id] = goal
        if self._store is not None:
            self._store.put_item("goals", goal.id, goal.to_dict())
        return goal

    def get(self, goal_id: str) -> Goal | None:
        if goal_id in self._memory:
            return self._memory[goal_id]
        if self._store is None:
            return None
        raw = self._store.get_item("goals", goal_id)
        if raw is None:
            return None
        goal = Goal.from_dict(raw)
        self._memory[goal.id] = goal
        return goal

    def list(self, *, status: GoalStatus | None = None) -> list[Goal]:
        if self._store is not None:
            for raw in self._store.list_items("goals"):
                goal = Goal.from_dict(raw)
                self._memory.setdefault(goal.id, goal)
        goals = list(self._memory.values())
        if status is not None:
            goals = [g for g in goals if g.status is status]
        return sorted(goals, key=lambda g: (-g.priority, g.created_at))

    def transition(
        self,
        goal_id: str,
        status: GoalStatus,
        *,
        reason: str,
        actor: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> Goal | None:
        goal = self.get(goal_id)
        if goal is None:
            return None
        transition = GoalTransition(
            from_status=goal.status.value,
            to_status=status.value,
            reason=reason,
            at=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            metadata=dict(metadata or {}),
        )
        goal.transitions.append(asdict(transition))
        goal.status = status
        return self.put(goal)

    def link_run(self, goal_id: str, run_id: str) -> Goal | None:
        goal = self.get(goal_id)
        if goal is None:
            return None
        if run_id not in goal.run_ids:
            goal.run_ids.append(run_id)
        return self.put(goal)

    def steer(self, goal_id: str, note: str, *, actor: str = "user") -> Goal | None:
        """Record explicit user steering at an orchestration boundary."""
        goal = self.get(goal_id)
        if goal is None:
            return None
        return self.transition(
            goal_id,
            goal.status,
            reason=f"steering:{note}",
            actor=actor,
            metadata={"steering": note},
        )
