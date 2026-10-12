"""Execution-backend protocol and deterministic fake for remote tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4


class BackendRunState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass
class BackendSubmitSpec:
    task_id: str
    instruction: str
    acceptance_criteria: list[str] = field(default_factory=list)
    workspace: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendHandle:
    external_run_id: str
    backend_id: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendStatus:
    state: BackendRunState
    summary: str | None = None
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendLogPage:
    records: list[dict[str, Any]]
    next_cursor: str | None = None


@dataclass
class BackendArtifact:
    artifact_id: str
    artifact_type: str
    reference: str
    size: int | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionBackend(Protocol):
    """June-owned interface for long-running external implementation backends."""

    @property
    def backend_id(self) -> str: ...

    def submit(self, spec: BackendSubmitSpec) -> BackendHandle: ...

    def status(self, handle: str) -> BackendStatus: ...

    def logs(
        self, handle: str, *, cursor: str | None = None, limit: int = 50
    ) -> BackendLogPage: ...

    def artifacts(self, handle: str) -> list[BackendArtifact]: ...

    def cancel(self, handle: str) -> BackendStatus: ...

    def reconcile(self, handle: str) -> BackendStatus: ...


@dataclass
class _FakeRun:
    handle: str
    task_id: str
    instruction: str
    polls_required: int
    polls_seen: int = 0
    cancelled: bool = False
    fail: bool = False
    logs: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[BackendArtifact] = field(default_factory=list)


class FakeExecutionBackend:
    """Deterministic multi-step backend driven by status/reconcile polls."""

    def __init__(self, *, polls_to_complete: int = 3, backend_id: str = "fake") -> None:
        self._backend_id = backend_id
        self.polls_to_complete = max(1, polls_to_complete)
        self._runs: dict[str, _FakeRun] = {}
        self.dispatch_count = 0

    @property
    def backend_id(self) -> str:
        return self._backend_id

    def submit(self, spec: BackendSubmitSpec) -> BackendHandle:
        self.dispatch_count += 1
        handle = f"fake-{uuid4()}"
        run = _FakeRun(
            handle=handle,
            task_id=spec.task_id,
            instruction=spec.instruction,
            polls_required=self.polls_to_complete,
        )
        run.logs.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": "info",
                "message": f"accepted task {spec.task_id}",
            }
        )
        self._runs[handle] = run
        return BackendHandle(external_run_id=handle, backend_id=self.backend_id)

    def status(self, handle: str) -> BackendStatus:
        run = self._runs.get(handle)
        if run is None:
            return BackendStatus(state=BackendRunState.UNKNOWN, error="unknown_handle")
        if run.cancelled:
            return BackendStatus(state=BackendRunState.CANCELLED, summary="cancelled")
        run.polls_seen += 1
        run.logs.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": "info",
                "message": f"poll {run.polls_seen}/{run.polls_required}",
            }
        )
        if run.polls_seen < run.polls_required:
            return BackendStatus(
                state=BackendRunState.RUNNING,
                summary=f"step {run.polls_seen}/{run.polls_required}",
                detail={"polls_seen": run.polls_seen},
            )
        if run.fail:
            return BackendStatus(state=BackendRunState.FAILED, error="fake_failure")
        if not run.artifacts:
            run.artifacts.append(
                BackendArtifact(
                    artifact_id=f"art-{handle}",
                    artifact_type="diff",
                    reference=f"memory://{handle}/result.diff",
                    metadata={"task_id": run.task_id},
                )
            )
        return BackendStatus(
            state=BackendRunState.SUCCEEDED,
            summary=f"completed: {run.instruction[:80]}",
            detail={"polls_seen": run.polls_seen},
        )

    def logs(self, handle: str, *, cursor: str | None = None, limit: int = 50) -> BackendLogPage:
        run = self._runs.get(handle)
        if run is None:
            return BackendLogPage(records=[])
        start = int(cursor or 0)
        end = start + max(1, limit)
        page = run.logs[start:end]
        next_cursor = str(end) if end < len(run.logs) else None
        return BackendLogPage(records=page, next_cursor=next_cursor)

    def artifacts(self, handle: str) -> list[BackendArtifact]:
        run = self._runs.get(handle)
        return list(run.artifacts) if run is not None else []

    def cancel(self, handle: str) -> BackendStatus:
        run = self._runs.get(handle)
        if run is None:
            return BackendStatus(state=BackendRunState.UNKNOWN, error="unknown_handle")
        run.cancelled = True
        run.logs.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": "info",
                "message": "cancel requested",
            }
        )
        return BackendStatus(state=BackendRunState.CANCELLED, summary="cancelled")

    def reconcile(self, handle: str) -> BackendStatus:
        """Reconcile without advancing the fake progress counter."""
        run = self._runs.get(handle)
        if run is None:
            return BackendStatus(state=BackendRunState.UNKNOWN, error="unknown_handle")
        if run.cancelled:
            return BackendStatus(state=BackendRunState.CANCELLED, summary="cancelled")
        if run.polls_seen >= run.polls_required:
            if run.fail:
                return BackendStatus(state=BackendRunState.FAILED, error="fake_failure")
            return BackendStatus(state=BackendRunState.SUCCEEDED, summary="completed")
        if run.polls_seen == 0:
            return BackendStatus(state=BackendRunState.QUEUED, summary="queued")
        return BackendStatus(
            state=BackendRunState.RUNNING,
            summary=f"step {run.polls_seen}/{run.polls_required}",
        )
