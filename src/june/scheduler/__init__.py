"""Scheduler — decides when work becomes runnable."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class WakeReason(str, Enum):
    SCHEDULE = "schedule"
    EVENT = "event"
    RETRY = "retry"
    DEPENDENCY = "dependency"
    MANUAL = "manual"
    GOAL = "goal"
    ISSUE = "issue"


@dataclass
class RunnableWork:
    """Unified runnable-work unit produced by the scheduler."""

    goal_id: str | None
    issue_id: str | None
    reason: WakeReason
    id: str = field(default_factory=lambda: str(uuid4()))
    payload: dict[str, Any] = field(default_factory=dict)
    coalesced_from: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Scheduler:
    """Owns wake/event/retry policy; does not imply execution capability."""

    def __init__(self) -> None:
        self._queue: list[RunnableWork] = []

    def enqueue(
        self,
        *,
        reason: WakeReason,
        goal_id: str | None = None,
        issue_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunnableWork:
        work = RunnableWork(
            goal_id=goal_id,
            issue_id=issue_id,
            reason=reason,
            payload=dict(payload or {}),
        )
        # Naive coalesce: drop duplicate active wake for same goal+reason.
        for existing in self._queue:
            if (
                existing.goal_id
                and existing.goal_id == work.goal_id
                and existing.reason is work.reason
            ):
                existing.coalesced_from.append(work.id)
                return existing
        self._queue.append(work)
        return work

    def next(self) -> RunnableWork | None:
        if not self._queue:
            return None
        return self._queue.pop(0)

    def pending(self) -> list[RunnableWork]:
        return list(self._queue)
