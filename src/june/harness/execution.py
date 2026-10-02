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


def _june_runner_registry() -> Any:
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

    registry = GraphNodeRunnerRegistry()
    registry.register(CallableGraphNodeRunner(["june.task"], _june_task))
    return registry


def build_graph_executor(
    *,
    grants: list[str] | None = None,
    on_event: Callable[[Any], None] | None = None,
) -> tuple[Any, Any]:
    """Return ``(executor, event_log)`` wired for June child-graph runs."""
    from mechaharness.core.access import (
        AccessPolicy,
        GraphEscalate,
        GraphExecute,
        InMemoryAccessControl,
    )
    from mechaharness.core.environment import NoOpInferenceEnvironment
    from mechaharness.core.events import InMemoryEventLog
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
    access = InMemoryAccessControl(event_log, AccessPolicy(grants=sorted(grant_keys)))
    runners = _june_runner_registry()
    linkage = DefaultLinkageResolver(
        runners,
        access,
        NoOpInferenceEnvironment(),
        require_execute_grant=True,
    )
    executor = GraphExecutor(
        event_log,
        access,
        runners,
        DefaultGraphFailurePolicy(),
        RejectGraphEscalation(),
        linkage,
        agent_id="june",
    )
    return executor, event_log


def run_graph(
    graph: Any,
    run: Any,
    *,
    on_event: Callable[[Any], None] | None = None,
) -> Any:
    """Execute ``graph`` with June's default runners and budget policy."""
    executor, _event_log = build_graph_executor(grants=run.grants, on_event=on_event)
    budget_policy = run.budget.to_mechaharness()

    async def _run() -> Any:
        return await executor.run(
            graph,
            budget_policy=budget_policy,
            run_id=run.run_id,
        )

    return asyncio.run(_run())
