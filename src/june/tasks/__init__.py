"""Durable remote-task identity, lifecycle, and transport-neutral service."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from june.persist import JsonStore
from june.tasks.backend import (
    BackendRunState,
    BackendSubmitSpec,
    ExecutionBackend,
)

COLLECTION = "remote_tasks"

TERMINAL_STATES = frozenset(
    {
        "succeeded",
        "failed",
        "cancelled",
        "needs_attention",
    }
)


class TaskState(str, Enum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_ATTENTION = "needs_attention"
    RECONCILING = "reconciling"


@dataclass
class TaskArtifactRef:
    artifact_id: str
    artifact_type: str
    reference: str
    size: int | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskArtifactRef:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RemoteTask:
    """Durable remote execution entity that survives restarts and client disconnects."""

    instruction: str
    id: str = field(default_factory=lambda: str(uuid4()))
    state: TaskState = TaskState.ACCEPTED
    acceptance_criteria: list[str] = field(default_factory=list)
    workspace: dict[str, Any] = field(default_factory=dict)
    backend: str = "fake"
    goal_id: str | None = None
    issue_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    attempt_count: int = 0
    external_run_id: str | None = None
    mechaharness_run_ids: list[str] = field(default_factory=list)
    result_summary: str | None = None
    error: str | None = None
    failure_class: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    log_buffer: list[dict[str, Any]] = field(default_factory=list)
    cancel_requested: bool = False
    transitions: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RemoteTask:
        payload = dict(data)
        payload["state"] = TaskState(payload.get("state", TaskState.ACCEPTED.value))
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})

    @property
    def is_terminal(self) -> bool:
        return self.state.value in TERMINAL_STATES


class TaskStore:
    """Persisted remote-task collection."""

    def __init__(self, store: JsonStore | None = None) -> None:
        self._memory: dict[str, RemoteTask] = {}
        self._store = store

    def put(self, task: RemoteTask) -> RemoteTask:
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self._memory[task.id] = task
        if self._store is not None:
            self._store.put_item(COLLECTION, task.id, task.to_dict())
        return task

    def get(self, task_id: str) -> RemoteTask | None:
        if task_id in self._memory:
            return self._memory[task_id]
        if self._store is None:
            return None
        raw = self._store.get_item(COLLECTION, task_id)
        if raw is None:
            return None
        task = RemoteTask.from_dict(raw)
        self._memory[task.id] = task
        return task

    def list_all(self, *, state: TaskState | None = None) -> list[RemoteTask]:
        if self._store is not None:
            for raw in self._store.list_items(COLLECTION):
                task = RemoteTask.from_dict(raw)
                self._memory.setdefault(task.id, task)
        tasks = list(self._memory.values())
        if state is not None:
            tasks = [t for t in tasks if t.state is state]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def non_terminal(self) -> list[RemoteTask]:
        return [t for t in self.list_all() if not t.is_terminal]


class RemoteTaskService:
    """Transport-neutral application service for remote task intake and observation."""

    def __init__(
        self,
        store: TaskStore,
        *,
        backend: ExecutionBackend | None = None,
        on_queued: Callable[[RemoteTask], None] | None = None,
        observe_backoff_seconds: float = 0.05,
    ) -> None:
        self.store = store
        self.backend = backend
        self.on_queued = on_queued
        self.observe_backoff_seconds = observe_backoff_seconds

    def submit_task(
        self,
        *,
        instruction: str,
        acceptance_criteria: list[str] | None = None,
        workspace: dict[str, Any] | None = None,
        backend: str | None = None,
        goal_id: str | None = None,
        issue_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RemoteTask:
        task = RemoteTask(
            instruction=instruction,
            acceptance_criteria=list(acceptance_criteria or []),
            workspace=dict(workspace or {}),
            backend=backend or (self.backend.backend_id if self.backend else "fake"),
            goal_id=goal_id,
            issue_id=issue_id,
            metadata=dict(metadata or {}),
        )
        self._transition(task, TaskState.ACCEPTED, reason="submitted")
        self.store.put(task)
        self._transition(task, TaskState.QUEUED, reason="queued")
        self.store.put(task)
        if self.on_queued is not None:
            self.on_queued(task)
        return task

    def get_task(self, task_id: str) -> RemoteTask | None:
        return self.store.get(task_id)

    def list_tasks(self, *, state: TaskState | None = None) -> list[RemoteTask]:
        return self.store.list_all(state=state)

    def cancel_task(self, task_id: str) -> RemoteTask | None:
        task = self.store.get(task_id)
        if task is None:
            return None
        if task.is_terminal:
            return task
        task.cancel_requested = True
        if task.external_run_id and self.backend is not None:
            try:
                self.backend.cancel(task.external_run_id)
            except Exception as exc:  # noqa: BLE001 - surface into task state
                task.error = f"cancel_backend_error:{exc}"
                self._transition(task, TaskState.NEEDS_ATTENTION, reason="cancel_failed")
                return self.store.put(task)
        self._transition(task, TaskState.CANCELLED, reason="cancel_requested")
        return self.store.put(task)

    def get_task_logs(
        self,
        task_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        task = self.store.get(task_id)
        if task is None:
            return {"records": [], "next_cursor": None, "error": "not_found"}
        if task.external_run_id and self.backend is not None:
            page = self.backend.logs(task.external_run_id, cursor=cursor, limit=limit)
            # Merge into durable buffer for restart-friendly reads.
            for record in page.records:
                if record not in task.log_buffer:
                    task.log_buffer.append(record)
            self.store.put(task)
            return {"records": page.records, "next_cursor": page.next_cursor}
        start = int(cursor or 0)
        end = start + max(1, limit)
        records = task.log_buffer[start:end]
        next_cursor = str(end) if end < len(task.log_buffer) else None
        return {"records": records, "next_cursor": next_cursor}

    def list_task_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        task = self.store.get(task_id)
        if task is None:
            return []
        if task.external_run_id and self.backend is not None:
            arts = [
                {
                    "artifact_id": a.artifact_id,
                    "artifact_type": a.artifact_type,
                    "reference": a.reference,
                    "size": a.size,
                    "content_type": a.content_type,
                    "metadata": a.metadata,
                    "task_id": task_id,
                    "backend_reference": task.external_run_id,
                }
                for a in self.backend.artifacts(task.external_run_id)
            ]
            if arts:
                task.artifacts = arts
                self.store.put(task)
            return arts
        return list(task.artifacts)

    def get_status(self) -> dict[str, Any]:
        tasks = self.store.list_all()
        counts: dict[str, int] = {}
        for task in tasks:
            counts[task.state.value] = counts.get(task.state.value, 0) + 1
        return {
            "task_counts": counts,
            "total": len(tasks),
            "non_terminal": len([t for t in tasks if not t.is_terminal]),
            "queued": counts.get(TaskState.QUEUED.value, 0),
            "running": counts.get(TaskState.RUNNING.value, 0)
            + counts.get(TaskState.DISPATCHING.value, 0),
            "terminal": len([t for t in tasks if t.is_terminal]),
        }

    def mark_dispatching(self, task_id: str) -> RemoteTask | None:
        task = self.store.get(task_id)
        if task is None or task.is_terminal:
            return task
        if task.state is TaskState.DISPATCHING:
            return task
        task.attempt_count += 1
        self._transition(task, TaskState.DISPATCHING, reason="dispatch_started")
        return self.store.put(task)

    def mark_running(
        self,
        task_id: str,
        *,
        external_run_id: str,
        mechaharness_run_id: str | None = None,
    ) -> RemoteTask | None:
        task = self.store.get(task_id)
        if task is None or task.is_terminal:
            return task
        task.external_run_id = external_run_id
        if mechaharness_run_id and mechaharness_run_id not in task.mechaharness_run_ids:
            task.mechaharness_run_ids.append(mechaharness_run_id)
        self._transition(task, TaskState.RUNNING, reason="external_accepted")
        return self.store.put(task)

    def record_mechaharness_run(self, task_id: str, run_id: str) -> RemoteTask | None:
        task = self.store.get(task_id)
        if task is None:
            return None
        if run_id not in task.mechaharness_run_ids:
            task.mechaharness_run_ids.append(run_id)
            self.store.put(task)
        return task

    def observe_task(self, task_id: str) -> RemoteTask | None:
        """One non-blocking observation poll against the execution backend."""
        task = self.store.get(task_id)
        if task is None or task.is_terminal:
            return task
        if task.cancel_requested:
            return self.cancel_task(task_id)
        if not task.external_run_id or self.backend is None:
            self._transition(task, TaskState.NEEDS_ATTENTION, reason="missing_backend_handle")
            task.error = "missing_backend_handle"
            return self.store.put(task)
        status = self.backend.status(task.external_run_id)
        page = self.backend.logs(task.external_run_id, limit=20)
        for record in page.records:
            if record not in task.log_buffer:
                task.log_buffer.append(record)
        if status.state is BackendRunState.RUNNING or status.state is BackendRunState.QUEUED:
            task.result_summary = status.summary
            self.store.put(task)
            return task
        if status.state is BackendRunState.SUCCEEDED:
            task.result_summary = status.summary
            task.artifacts = [
                {
                    "artifact_id": a.artifact_id,
                    "artifact_type": a.artifact_type,
                    "reference": a.reference,
                    "size": a.size,
                    "content_type": a.content_type,
                    "metadata": a.metadata,
                    "task_id": task_id,
                    "backend_reference": task.external_run_id,
                }
                for a in self.backend.artifacts(task.external_run_id)
            ]
            self._transition(task, TaskState.SUCCEEDED, reason="backend_succeeded")
            return self.store.put(task)
        if status.state is BackendRunState.CANCELLED:
            self._transition(task, TaskState.CANCELLED, reason="backend_cancelled")
            return self.store.put(task)
        if status.state is BackendRunState.FAILED:
            task.error = status.error or "backend_failed"
            task.failure_class = "backend_failed"
            self._transition(task, TaskState.FAILED, reason="backend_failed")
            return self.store.put(task)
        task.error = status.error or "backend_unknown"
        self._transition(task, TaskState.NEEDS_ATTENTION, reason="backend_unknown")
        return self.store.put(task)

    def reconcile_task(self, task_id: str) -> RemoteTask | None:
        task = self.store.get(task_id)
        if task is None or task.is_terminal:
            return task
        prior = task.state
        self._transition(task, TaskState.RECONCILING, reason="startup_reconcile")
        self.store.put(task)
        if not task.external_run_id:
            # Never auto-redispatch merely because state is unknown.
            if prior in {TaskState.QUEUED, TaskState.ACCEPTED}:
                self._transition(task, TaskState.QUEUED, reason="reconcile_requeue")
                self.store.put(task)
                if self.on_queued is not None:
                    self.on_queued(task)
                return task
            if prior is TaskState.DISPATCHING:
                # Background dispatch still in flight; leave alone.
                self._transition(task, TaskState.DISPATCHING, reason="reconcile_dispatch_inflight")
                return self.store.put(task)
            task.error = "missing_external_run_id"
            self._transition(task, TaskState.NEEDS_ATTENTION, reason="reconcile_no_handle")
            return self.store.put(task)
        if self.backend is None:
            task.error = "backend_unavailable"
            self._transition(task, TaskState.NEEDS_ATTENTION, reason="reconcile_no_backend")
            return self.store.put(task)
        status = self.backend.reconcile(task.external_run_id)
        if status.state in {BackendRunState.RUNNING, BackendRunState.QUEUED}:
            self._transition(task, TaskState.RUNNING, reason="reconcile_still_running")
            return self.store.put(task)
        if status.state is BackendRunState.SUCCEEDED:
            task.result_summary = status.summary
            self._transition(task, TaskState.SUCCEEDED, reason="reconcile_succeeded")
            return self.store.put(task)
        if status.state is BackendRunState.CANCELLED:
            self._transition(task, TaskState.CANCELLED, reason="reconcile_cancelled")
            return self.store.put(task)
        if status.state is BackendRunState.FAILED:
            task.error = status.error or "reconcile_failed"
            self._transition(task, TaskState.FAILED, reason="reconcile_failed")
            return self.store.put(task)
        task.error = status.error or "reconcile_unknown"
        self._transition(task, TaskState.NEEDS_ATTENTION, reason="reconcile_unknown")
        return self.store.put(task)

    def reconcile_all(self) -> list[RemoteTask]:
        results = (self.reconcile_task(task.id) for task in self.store.non_terminal())
        return [task for task in results if task is not None]

    def mark_needs_attention(
        self,
        task_id: str,
        *,
        error: str,
        reason: str = "needs_attention",
        failure_class: str | None = None,
    ) -> RemoteTask | None:
        task = self.store.get(task_id)
        if task is None or task.is_terminal:
            return task
        task.error = error
        if failure_class is not None:
            task.failure_class = failure_class
        self._transition(task, TaskState.NEEDS_ATTENTION, reason=reason)
        return self.store.put(task)

    def build_submit_spec(self, task: RemoteTask) -> BackendSubmitSpec:
        return BackendSubmitSpec(
            task_id=task.id,
            instruction=task.instruction,
            acceptance_criteria=list(task.acceptance_criteria),
            workspace=dict(task.workspace),
            metadata=dict(task.metadata),
        )

    def _transition(self, task: RemoteTask, state: TaskState, *, reason: str) -> None:
        if task.state is state and task.transitions:
            # Idempotent terminal / same-state writes still record once on first set.
            if state.value in TERMINAL_STATES:
                return
        transition = {
            "from_status": task.state.value,
            "to_status": state.value,
            "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        task.transitions.append(transition)
        task.state = state
        task.updated_at = transition["at"]
