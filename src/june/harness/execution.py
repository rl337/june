"""Run June-bound graphs through MechaHarness GraphExecutor."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class TappingEventLog:
    """Forward events to a store and an optional June callback."""

    def __init__(
        self,
        store: Any,
        on_event: Callable[[Any], None] | None = None,
    ) -> None:
        self._store = store
        self._on_event = on_event

    def emit(self, event: Any) -> None:
        self._store.emit(event)
        if self._on_event is not None:
            self._on_event(event)

    def query(self, **kwargs: Any) -> list[Any]:
        return self._store.query(**kwargs)

    def agents(self, **kwargs: Any) -> list[Any]:
        return self._store.agents(**kwargs)


def _june_runner_registry(
    on_console_log: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
    from datetime import datetime, timezone

    from mechaharness.graph import NodeStatus
    from mechaharness.graph_executor import (
        CallableGraphNodeRunner,
        GraphNodeRunnerRegistry,
        NodeOutcome,
    )

    async def _june_task(node: Any, context: Any) -> Any:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"june_task": True, "node_id": node.id},
            cost_units=1.0,
        )

    async def _event_log(node: Any, context: Any) -> Any:
        message = str(node.payload.get("message") or node.goal or "event")
        if on_console_log is not None:
            on_console_log(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "june.console.log",
                    "run_id": context.run_id,
                    "node_id": node.id,
                    "kind": node.kind,
                    "message": message,
                    "summary": message,
                    "bucket": node.payload.get("bucket"),
                    "instance_id": node.payload.get("instance_id"),
                }
            )
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"console_message": message, "node_id": node.id},
            cost_units=0.25,
        )

    async def _timed_log(node: Any, context: Any) -> Any:
        import asyncio as _asyncio

        message = str(node.payload.get("message") or node.goal or "timed")
        try:
            delay = float(node.payload.get("duration_seconds", 3.0))
        except (TypeError, ValueError):
            delay = 3.0
        delay = max(0.0, min(delay, 30.0))
        if on_console_log is not None:
            on_console_log(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "june.console.log",
                    "run_id": context.run_id,
                    "node_id": node.id,
                    "kind": node.kind,
                    "message": f"{message} (wait {delay:.0f}s)",
                    "summary": f"⏳ {message}",
                    "bucket": node.payload.get("bucket"),
                    "instance_id": node.payload.get("instance_id"),
                }
            )
        if delay:
            await _asyncio.sleep(delay)
        if on_console_log is not None:
            on_console_log(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "june.console.log",
                    "run_id": context.run_id,
                    "node_id": node.id,
                    "kind": node.kind,
                    "message": message,
                    "summary": f"✓ {message}",
                    "bucket": node.payload.get("bucket"),
                    "instance_id": node.payload.get("instance_id"),
                }
            )
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "console_message": message,
                "node_id": node.id,
                "duration_seconds": delay,
            },
            cost_units=0.5,
        )

    async def _cron_hub(node: Any, context: Any) -> Any:
        del node
        if on_console_log is not None:
            on_console_log(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "june.console.log",
                    "run_id": context.run_id,
                    "kind": "june.cron",
                    "message": "cron hub tick",
                    "summary": "cron hub tick",
                }
            )
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"cron": True}, cost_units=0.1)

    registry = GraphNodeRunnerRegistry()
    registry.register(CallableGraphNodeRunner(["june.task"], _june_task))
    registry.register(CallableGraphNodeRunner(["june.event_log"], _event_log))
    registry.register(CallableGraphNodeRunner(["june.timed_log"], _timed_log))
    registry.register(CallableGraphNodeRunner(["june.cron"], _cron_hub))
    return registry


def build_graph_executor(
    *,
    grants: list[str] | None = None,
    on_event: Callable[[Any], None] | None = None,
    on_console_log: Callable[[dict[str, Any]], None] | None = None,
    checkpoint_path: str | None = None,
    runners: Any | None = None,
) -> tuple[Any, Any]:
    """Return ``(executor, event_log)`` wired for June child-graph runs.

    When ``checkpoint_path`` is set, use durable SQLite checkpoints; otherwise
    an ephemeral EventLog-backed store (fine for tests / short demos).

    Prefer ``mechaharness.host_kit.host_graph_executor`` for new paths that do
    not need event tapping (remote-task dispatch already does). This hand-wired
    helper remains for ``MechaHarnessClient`` / console event taps — see
    ``docs/requirements/mechaharness-host-friction.md`` HF-01 / HF-05.
    """
    from mechaharness.checkpoint_store import EventLogCheckpointStore
    from mechaharness.core.access import (
        AccessPolicy,
        GraphEscalate,
        GraphExecute,
        InMemoryAccessControl,
    )
    from mechaharness.core.environment import NoOpInferenceEnvironment
    from mechaharness.core.events import InMemoryEventLog
    from mechaharness.external_effect import NoopCrashProbe
    from mechaharness.graph import GraphStore
    from mechaharness.graph_executor import (
        DefaultGraphFailurePolicy,
        GraphExecutor,
        RejectGraphEscalation,
    )
    from mechaharness.linkage_resolver import DefaultLinkageResolver

    store = InMemoryEventLog()
    event_log = TappingEventLog(store, on_event=on_event)
    grant_keys = {
        GraphExecute.key(),
        GraphEscalate.key(),
        *(grants or []),
    }
    access = InMemoryAccessControl(
        event_log,  # type: ignore[arg-type]
        AccessPolicy(grants=sorted(grant_keys)),
    )
    runner_registry = runners if runners is not None else _june_runner_registry(
        on_console_log=on_console_log
    )
    linkage = DefaultLinkageResolver(
        runner_registry,
        access,
        NoOpInferenceEnvironment(),
        require_execute_grant=True,
    )
    if checkpoint_path:
        from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore

        checkpoint_store: Any = SqliteCheckpointStore(checkpoint_path)
    else:
        checkpoint_store = EventLogCheckpointStore(
            GraphStore(store, agent_id="june"),
            event_log=store,
            agent_id="june",
        )
    # TappingEventLog mirrors EventLog; MH types expect the Protocol.
    executor = GraphExecutor(
        event_log,  # type: ignore[arg-type]
        access,
        runner_registry,
        DefaultGraphFailurePolicy(),
        RejectGraphEscalation(),
        linkage,
        checkpoint_store,
        NoopCrashProbe(),
        agent_id="june",
    )
    return executor, event_log


def run_graph(
    graph: Any,
    run: Any,
    *,
    on_event: Callable[[Any], None] | None = None,
    on_console_log: Callable[[dict[str, Any]], None] | None = None,
    checkpoint_path: str | None = None,
    runners: Any | None = None,
    resume: bool = False,
) -> Any:
    """Execute ``graph`` with June's default runners and budget policy."""
    executor, _event_log = build_graph_executor(
        grants=run.grants,
        on_event=on_event,
        on_console_log=on_console_log,
        checkpoint_path=checkpoint_path,
        runners=runners,
    )
    budget_policy = run.budget.to_mechaharness()

    async def _run() -> Any:
        return await executor.run(
            graph,
            budget_policy=budget_policy,
            run_id=run.run_id,
            resume=resume,
        )

    return asyncio.run(_run())
