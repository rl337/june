"""Remote task orchestration: durable model, fake backend, effectful dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from june.orchestrator import Orchestrator
from june.persist import JsonStore
from june.tasks import RemoteTaskService, TaskState, TaskStore
from june.tasks.backend import FakeExecutionBackend


def _noop_sleep(_: float) -> None:
    return None


def _drive(
    orch: Orchestrator,
    task_id: str,
    *,
    until: TaskState,
    max_steps: int = 80,
) -> None:
    orch.control.sleeper = _noop_sleep
    for _ in range(max_steps):
        orch.tick()
        try:
            orch.remote_worker.wait(f"dispatch:{task_id}", timeout=2.0)
        except Exception:
            pass
        task = orch.tasks.get_task(task_id)
        assert task is not None
        if task.state is until:
            return
        if task.is_terminal and until is not task.state:
            raise AssertionError(f"terminal {task.state} error={task.error}")
    task = orch.tasks.get_task(task_id)
    raise AssertionError(f"did not reach {until}; last={task.state if task else None}")


def test_json_store_atomic_roundtrip(tmp_path: Path) -> None:
    store = JsonStore(tmp_path)
    store.put_item("remote_tasks", "t1", {"id": "t1", "state": "accepted"})
    assert store.get_item("remote_tasks", "t1")["state"] == "accepted"
    path = tmp_path / "remote_tasks.json"
    assert path.exists()
    assert not list(tmp_path.glob(".remote_tasks.*.tmp"))


def test_task_submit_survives_restart_without_backend(tmp_path: Path) -> None:
    store = JsonStore(tmp_path)
    service = RemoteTaskService(TaskStore(store), backend=None, on_queued=None)
    task = service.submit_task(
        instruction="noop durable",
        acceptance_criteria=["persisted"],
        workspace={"repository": "rl337/june"},
    )
    assert task.state is TaskState.QUEUED
    assert task.id

    reloaded = RemoteTaskService(TaskStore(JsonStore(tmp_path)), backend=None)
    got = reloaded.get_task(task.id)
    assert got is not None
    assert got.instruction == "noop durable"
    assert got.state is TaskState.QUEUED
    listed = reloaded.list_tasks()
    assert any(t.id == task.id for t in listed)

    cancelled = reloaded.cancel_task(task.id)
    assert cancelled is not None
    assert cancelled.state is TaskState.CANCELLED
    # Idempotent cancel
    again = reloaded.cancel_task(task.id)
    assert again is not None
    assert again.state is TaskState.CANCELLED


def test_fake_backend_progresses_across_ticks(tmp_path: Path) -> None:
    backend = FakeExecutionBackend(polls_to_complete=3)
    orch = Orchestrator(tmp_path, execution_backend=backend)
    orch.control.sleeper = _noop_sleep
    orch.tasks.observe_backoff_seconds = 0.0
    task = orch.submit_remote_task(
        instruction="ship remote slice",
        acceptance_criteria=["tests pass"],
        workspace={"repository": "rl337/june", "base_ref": "main"},
    )
    assert task.state is TaskState.QUEUED
    _drive(orch, task.id, until=TaskState.SUCCEEDED)
    done = orch.tasks.get_task(task.id)
    assert done is not None
    assert done.external_run_id
    assert done.mechaharness_run_ids
    assert done.artifacts
    status = orch.status()
    assert status["remote_tasks"]["terminal"] >= 1
    assert any(r["task_id"] == task.id for r in status["remote_task_recent"])


def test_restart_does_not_double_dispatch(tmp_path: Path) -> None:
    backend = FakeExecutionBackend(polls_to_complete=5)
    orch = Orchestrator(tmp_path, execution_backend=backend)
    orch.control.sleeper = _noop_sleep
    orch.tasks.observe_backoff_seconds = 0.0
    task = orch.submit_remote_task(instruction="long job")
    _drive(orch, task.id, until=TaskState.RUNNING)
    assert backend.dispatch_count == 1
    running = orch.tasks.get_task(task.id)
    assert running is not None
    assert running.external_run_id

    orch2 = Orchestrator(tmp_path, execution_backend=backend)
    orch2.control.sleeper = _noop_sleep
    orch2.tasks.observe_backoff_seconds = 0.0
    # Startup reconcile + a few observes; must not submit again.
    for _ in range(10):
        orch2.tick()
        try:
            orch2.remote_worker.wait(f"dispatch:{task.id}", timeout=0.2)
        except Exception:
            pass
    assert backend.dispatch_count == 1
    after = orch2.tasks.get_task(task.id)
    assert after is not None
    assert after.external_run_id == running.external_run_id


def test_cancel_before_dispatch(tmp_path: Path) -> None:
    backend = FakeExecutionBackend(polls_to_complete=3)
    orch = Orchestrator(tmp_path, execution_backend=backend)
    # Do not tick — cancel while queued.
    task = orch.submit_remote_task(instruction="cancel me")
    cancelled = orch.tasks.cancel_task(task.id)
    assert cancelled is not None
    assert cancelled.state is TaskState.CANCELLED
    orch.control.sleeper = _noop_sleep
    orch.tick()
    final = orch.tasks.get_task(task.id)
    assert final is not None
    assert final.state is TaskState.CANCELLED
    assert backend.dispatch_count == 0


def test_effectful_dispatch_uses_durable_checkpoint(tmp_path: Path) -> None:
    pytest.importorskip("mechaharness")
    backend = FakeExecutionBackend(polls_to_complete=2)
    orch = Orchestrator(tmp_path, execution_backend=backend)
    orch.control.sleeper = _noop_sleep
    orch.tasks.observe_backoff_seconds = 0.0
    task = orch.submit_remote_task(instruction="checkpointed dispatch")
    _drive(orch, task.id, until=TaskState.RUNNING)
    ckpt = tmp_path / "checkpoints.sqlite"
    assert ckpt.exists()
    done = orch.tasks.get_task(task.id)
    assert done is not None
    assert done.mechaharness_run_ids
