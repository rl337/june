"""Scheduler — decides when work becomes runnable."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


class WakeReason(str, Enum):
    SCHEDULE = "schedule"
    EVENT = "event"
    RETRY = "retry"
    DEPENDENCY = "dependency"
    MANUAL = "manual"
    GOAL = "goal"
    ISSUE = "issue"
    KNOWLEDGE = "knowledge"
    STEERING = "steering"


@dataclass
class ScheduleSpec:
    """Clock schedule that can wake a goal/issue."""

    id: str = field(default_factory=lambda: str(uuid4()))
    goal_id: str | None = None
    issue_id: str | None = None
    interval_seconds: int = 3600
    next_run_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    enabled: bool = True
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunnableWork:
    """Unified runnable-work unit produced by the scheduler."""

    goal_id: str | None
    issue_id: str | None
    reason: WakeReason
    id: str = field(default_factory=lambda: str(uuid4()))
    payload: dict[str, Any] = field(default_factory=dict)
    coalesced_from: list[str] = field(default_factory=list)
    attempt: int = 0
    max_attempts: int = 3
    not_before: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    wake_log: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reason"] = self.reason.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunnableWork:
        payload = dict(data)
        payload["reason"] = WakeReason(payload["reason"])
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


class Scheduler:
    """Owns wake/event/retry policy; does not imply execution capability."""

    def __init__(self, store: JsonStore | None = None) -> None:
        self._queue: list[RunnableWork] = []
        self._schedules: dict[str, ScheduleSpec] = {}
        self._wake_history: list[dict[str, Any]] = []
        self._store = store
        self._load()

    def _load(self) -> None:
        if self._store is None:
            return
        for raw in self._store.list_items("scheduler_queue"):
            work = RunnableWork.from_dict(raw)
            self._queue.append(work)
        for raw in self._store.list_items("schedules"):
            fields = ScheduleSpec.__dataclass_fields__
            spec = ScheduleSpec(**{k: v for k, v in raw.items() if k in fields})
            self._schedules[spec.id] = spec
        self._wake_history = self._store.list_items("wake_history")

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save("scheduler_queue", {w.id: w.to_dict() for w in self._queue})
        self._store.save(
            "schedules",
            {s.id: asdict(s) for s in self._schedules.values()},
        )
        self._store.save(
            "wake_history",
            {str(i): entry for i, entry in enumerate(self._wake_history[-500:])},
        )

    def add_schedule(self, spec: ScheduleSpec) -> ScheduleSpec:
        self._schedules[spec.id] = spec
        self._persist()
        return spec

    def enqueue(
        self,
        *,
        reason: WakeReason,
        goal_id: str | None = None,
        issue_id: str | None = None,
        payload: dict[str, Any] | None = None,
        attempt: int = 0,
        max_attempts: int = 3,
        not_before: str | None = None,
        coalesce: bool = True,
    ) -> RunnableWork:
        work = RunnableWork(
            goal_id=goal_id,
            issue_id=issue_id,
            reason=reason,
            payload=dict(payload or {}),
            attempt=attempt,
            max_attempts=max_attempts,
            not_before=not_before,
            wake_log={
                "why": reason.value,
                "goal_id": goal_id,
                "issue_id": issue_id,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if coalesce:
            for existing in self._queue:
                if (
                    existing.goal_id
                    and existing.goal_id == work.goal_id
                    and existing.reason is work.reason
                    and existing.issue_id == work.issue_id
                ):
                    existing.coalesced_from.append(work.id)
                    existing.payload.update(work.payload)
                    self._record_wake(existing, coalesced=True)
                    self._persist()
                    return existing
        self._queue.append(work)
        self._record_wake(work, coalesced=False)
        self._persist()
        return work

    def _record_wake(self, work: RunnableWork, *, coalesced: bool) -> None:
        self._wake_history.append(
            {
                **work.wake_log,
                "work_id": work.id,
                "coalesced": coalesced,
            }
        )

    def tick(self, *, now: datetime | None = None) -> list[RunnableWork]:
        """Materialize due clock schedules into runnable work."""
        current = now or datetime.now(timezone.utc)
        woken: list[RunnableWork] = []
        for spec in list(self._schedules.values()):
            if not spec.enabled:
                continue
            due = datetime.fromisoformat(spec.next_run_at)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due > current:
                continue
            work = self.enqueue(
                reason=WakeReason.SCHEDULE,
                goal_id=spec.goal_id,
                issue_id=spec.issue_id,
                payload={**spec.payload, "schedule_id": spec.id},
            )
            woken.append(work)
            spec.next_run_at = (current + timedelta(seconds=spec.interval_seconds)).isoformat()
        self._persist()
        return woken

    def retry(
        self,
        work: RunnableWork,
        *,
        backoff_seconds: int = 30,
        reason: WakeReason = WakeReason.RETRY,
    ) -> RunnableWork | None:
        if work.attempt + 1 >= work.max_attempts:
            return None
        not_before = (datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)).isoformat()
        return self.enqueue(
            reason=reason,
            goal_id=work.goal_id,
            issue_id=work.issue_id,
            payload=work.payload,
            attempt=work.attempt + 1,
            max_attempts=work.max_attempts,
            not_before=not_before,
            coalesce=False,
        )

    def next(self, *, now: datetime | None = None) -> RunnableWork | None:
        current = now or datetime.now(timezone.utc)
        for idx, work in enumerate(self._queue):
            if work.not_before:
                ready_at = datetime.fromisoformat(work.not_before)
                if ready_at.tzinfo is None:
                    ready_at = ready_at.replace(tzinfo=timezone.utc)
                if ready_at > current:
                    continue
            selected = self._queue.pop(idx)
            self._persist()
            return selected
        self._persist()
        return None

    def pending(self) -> list[RunnableWork]:
        return list(self._queue)

    def wake_history(self) -> list[dict[str, Any]]:
        return list(self._wake_history)
