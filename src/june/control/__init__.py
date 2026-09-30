"""June control graph — single entrypoint loop for cron, polling, and due work.

This is a June-owned incubating concrete graph: it owns the timed work queue and
the ≤100ms tick. MechaHarness execution graphs are only invoked when a due job
asks the task runner to bind/run product work.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Protocol
from uuid import uuid4

from june.persist import JsonStore

MAX_TICK_SECONDS = 0.1


class ControlJobKind(str, Enum):
    CRON_TICK = "control.cron_tick"
    POLL_TELEGRAM = "control.poll_telegram"
    POLL_DISCORD = "control.poll_discord"
    POLL_WEBAPP = "control.poll_webapp"
    EXECUTE_WORK = "control.execute_work"


@dataclass(order=True)
class TimedJob:
    """Future work with an absolute trigger time."""

    run_at: datetime
    kind: str = field(compare=False)
    id: str = field(default_factory=lambda: str(uuid4()), compare=False)
    payload: dict[str, Any] = field(default_factory=dict, compare=False)
    recurring_every_seconds: float | None = field(default=None, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "run_at": self.run_at.isoformat(),
            "payload": self.payload,
            "recurring_every_seconds": self.recurring_every_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimedJob:
        run_at = datetime.fromisoformat(str(data["run_at"]))
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        return cls(
            id=str(data.get("id") or uuid4()),
            kind=str(data["kind"]),
            run_at=run_at,
            payload=dict(data.get("payload") or {}),
            recurring_every_seconds=data.get("recurring_every_seconds"),
        )


class WorkQueue:
    """Priority queue of future control-graph jobs."""

    def __init__(self, store: JsonStore | None = None) -> None:
        self._jobs: list[TimedJob] = []
        self._store = store
        self._load()

    def _load(self) -> None:
        if self._store is None:
            return
        for raw in self._store.list_items("control_queue"):
            self._jobs.append(TimedJob.from_dict(raw))
        self._jobs.sort()

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save("control_queue", {job.id: job.to_dict() for job in self._jobs})

    def schedule(
        self,
        kind: str | ControlJobKind,
        *,
        run_at: datetime | None = None,
        payload: dict[str, Any] | None = None,
        recurring_every_seconds: float | None = None,
        job_id: str | None = None,
    ) -> TimedJob:
        when = run_at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        kind_value = kind.value if isinstance(kind, ControlJobKind) else kind
        # Replace existing job with same id (used for singleton pollers).
        if job_id is not None:
            self._jobs = [j for j in self._jobs if j.id != job_id]
        job = TimedJob(
            id=job_id or str(uuid4()),
            kind=kind_value,
            run_at=when,
            payload=dict(payload or {}),
            recurring_every_seconds=recurring_every_seconds,
        )
        self._jobs.append(job)
        self._jobs.sort()
        self._persist()
        return job

    def due(self, now: datetime | None = None) -> list[TimedJob]:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        due: list[TimedJob] = []
        remaining: list[TimedJob] = []
        for job in self._jobs:
            if job.run_at <= current:
                due.append(job)
            else:
                remaining.append(job)
        self._jobs = remaining
        self._persist()
        return due

    def next_run_at(self) -> datetime | None:
        if not self._jobs:
            return None
        return self._jobs[0].run_at

    def pending(self) -> list[TimedJob]:
        return list(self._jobs)

    def sleep_seconds(
        self,
        now: datetime | None = None,
        *,
        max_tick_seconds: float = MAX_TICK_SECONDS,
    ) -> float:
        """How long the control loop should wait before the next step.

        - 0 if any job is already due
        - min(max_tick, time_until_next_job) otherwise
        - max_tick if the queue is empty
        """
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        nxt = self.next_run_at()
        if nxt is None:
            return max_tick_seconds
        delay = (nxt - current).total_seconds()
        if delay <= 0:
            return 0.0
        return min(max_tick_seconds, delay)


class ChannelPoller(Protocol):
    name: str

    def poll(self) -> list[dict[str, Any]]:
        """Return newly observed intake events (messages, wakes, etc.)."""


@dataclass
class NullPoller:
    name: str

    def poll(self) -> list[dict[str, Any]]:
        return []


@dataclass
class ControlStepResult:
    slept_seconds: float
    jobs_run: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    work_outcomes: list[dict[str, Any]] = field(default_factory=list)


class ControlGraph:
    """Concrete June graph: cron tick + channel polls + due execute_work jobs."""

    GRAPH_NAME = "june.control"
    NODE_KINDS = [
        ControlJobKind.CRON_TICK.value,
        ControlJobKind.POLL_TELEGRAM.value,
        ControlJobKind.POLL_DISCORD.value,
        ControlJobKind.POLL_WEBAPP.value,
        ControlJobKind.EXECUTE_WORK.value,
    ]

    def __init__(
        self,
        *,
        queue: WorkQueue | None = None,
        store: JsonStore | None = None,
        max_tick_seconds: float = MAX_TICK_SECONDS,
        poll_interval_seconds: float = MAX_TICK_SECONDS,
        on_cron_tick: Callable[[], list[dict[str, Any]]] | None = None,
        on_execute_work: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        pollers: dict[str, ChannelPoller] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.queue = queue or WorkQueue(store)
        self.max_tick_seconds = max_tick_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.on_cron_tick = on_cron_tick
        self.on_execute_work = on_execute_work
        self.pollers = pollers or {
            ControlJobKind.POLL_TELEGRAM.value: NullPoller("telegram"),
            ControlJobKind.POLL_DISCORD.value: NullPoller("discord"),
            ControlJobKind.POLL_WEBAPP.value: NullPoller("webapp"),
        }
        self.sleeper = sleeper
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._started = False

    def bootstrap(self) -> None:
        """Ensure the recurring control nodes are on the queue."""
        now = self.clock()
        self.queue.schedule(
            ControlJobKind.CRON_TICK,
            run_at=now,
            recurring_every_seconds=self.poll_interval_seconds,
            job_id="control:cron_tick",
        )
        for kind in (
            ControlJobKind.POLL_TELEGRAM,
            ControlJobKind.POLL_DISCORD,
            ControlJobKind.POLL_WEBAPP,
        ):
            self.queue.schedule(
                kind,
                run_at=now,
                recurring_every_seconds=self.poll_interval_seconds,
                job_id=f"control:{kind.value}",
            )
        self._started = True

    def schedule_work(
        self,
        payload: dict[str, Any],
        *,
        run_at: datetime | None = None,
    ) -> TimedJob:
        return self.queue.schedule(
            ControlJobKind.EXECUTE_WORK,
            run_at=run_at or self.clock(),
            payload=payload,
        )

    def _reschedule_if_recurring(self, job: TimedJob) -> None:
        if job.recurring_every_seconds is None:
            return
        self.queue.schedule(
            job.kind,
            run_at=self.clock() + timedelta(seconds=job.recurring_every_seconds),
            payload=job.payload,
            recurring_every_seconds=job.recurring_every_seconds,
            job_id=job.id,
        )

    def _handle(self, job: TimedJob) -> dict[str, Any]:
        if job.kind == ControlJobKind.CRON_TICK.value:
            events = self.on_cron_tick() if self.on_cron_tick else []
            return {"kind": job.kind, "events": events}
        if job.kind in self.pollers:
            events = self.pollers[job.kind].poll()
            return {"kind": job.kind, "events": events}
        if job.kind == ControlJobKind.EXECUTE_WORK.value:
            if self.on_execute_work is None:
                return {"kind": job.kind, "status": "no_handler", "payload": job.payload}
            return {"kind": job.kind, "outcome": self.on_execute_work(job.payload)}
        return {"kind": job.kind, "status": "unknown_kind"}

    def step(self) -> ControlStepResult:
        if not self._started:
            self.bootstrap()
        now = self.clock()
        sleep_for = self.queue.sleep_seconds(now, max_tick_seconds=self.max_tick_seconds)
        if sleep_for > 0:
            self.sleeper(sleep_for)
        now = self.clock()
        due = self.queue.due(now)
        events: list[dict[str, Any]] = []
        work_outcomes: list[dict[str, Any]] = []
        jobs_run: list[str] = []
        for job in due:
            result = self._handle(job)
            jobs_run.append(job.kind)
            if "events" in result:
                events.extend(result["events"])
            if "outcome" in result:
                work_outcomes.append(result["outcome"])
            self._reschedule_if_recurring(job)
        return ControlStepResult(
            slept_seconds=sleep_for,
            jobs_run=jobs_run,
            events=events,
            work_outcomes=work_outcomes,
        )

    def run(
        self,
        *,
        max_steps: int | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[ControlStepResult]:
        if not self._started:
            self.bootstrap()
        results: list[ControlStepResult] = []
        steps = 0
        while True:
            if should_stop is not None and should_stop():
                break
            if max_steps is not None and steps >= max_steps:
                break
            results.append(self.step())
            steps += 1
        return results

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.GRAPH_NAME,
            "max_tick_seconds": self.max_tick_seconds,
            "poll_interval_seconds": self.poll_interval_seconds,
            "node_kinds": list(self.NODE_KINDS),
            "pending": [asdict_job(j) for j in self.queue.pending()],
        }


def asdict_job(job: TimedJob) -> dict[str, Any]:
    return job.to_dict()
