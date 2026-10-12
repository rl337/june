"""MechaHarness effectful coding-job runner and remote-task graph builders.

``june.remote_task`` is a June-incubated recipe candidate (not an MH catalog
id). See ``docs/requirements/mechaharness-host-friction.md`` HF-03.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from june.budget import SubgraphBudget
from june.harness import BoundRun
from june.tasks.backend import BackendSubmitSpec, ExecutionBackend


def build_remote_task_graph(task_payload: dict[str, Any], *, run_id: str | None = None) -> Any:
    """Build validate → resolve → coding_job → collect → verify → persist.

    Hand-built linear graph until HF-03 promotion into an MH Agentic Recipe.
    """
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode

    rid = run_id or f"remote-task-{uuid4().hex[:8]}"
    graph = ExecutionGraph(
        id=rid,
        goal=str(task_payload.get("instruction") or "remote task"),
    )
    nodes = [
        GraphNode(
            id="validate_task",
            kind="june.task",
            goal="validate remote task",
            payload={"phase": "validate", **task_payload},
        ),
        GraphNode(
            id="resolve_workspace",
            kind="june.task",
            goal="resolve workspace",
            payload={"phase": "resolve_workspace", **task_payload},
        ),
        GraphNode(
            id="coding_job",
            kind="june.coding_job",
            goal="dispatch external coding job",
            payload=dict(task_payload),
        ),
        GraphNode(
            id="collect_result",
            kind="june.task",
            goal="collect dispatch evidence",
            payload={"phase": "collect"},
        ),
        GraphNode(
            id="verify_acceptance",
            kind="june.task",
            goal="verify acceptance criteria evidence present",
            payload={
                "phase": "verify",
                "acceptance_criteria": list(task_payload.get("acceptance_criteria") or []),
            },
        ),
        GraphNode(
            id="persist_outcome",
            kind="june.task",
            goal="persist outcome markers",
            payload={"phase": "persist"},
        ),
    ]
    for node in nodes:
        graph.add_node(node)
    order = [n.id for n in nodes]
    for left, right in zip(order, order[1:]):
        graph.add_dependency(
            DependencyEdge(
                from_node=left,
                to_node=right,
                types=["control"],
                reason="june remote task sequence",
            )
        )
    return graph


def bound_run_for_task(task_id: str, *, grants: list[str] | None = None) -> BoundRun:
    return BoundRun(
        run_id=f"remote-task-{task_id}-{uuid4().hex[:8]}",
        template_name="june.remote_task",
        bindings={"task_id": task_id},
        budget=SubgraphBudget(),
        grants=list(grants or []),
        node_kinds=[
            "june.task",
            "june.task",
            "june.coding_job",
            "june.task",
            "june.task",
            "june.task",
        ],
    )


def make_coding_job_runner(backend: ExecutionBackend) -> Any:
    """Return MH ``SubmitOnceEffectfulRunner`` bound to June's ExecutionBackend."""
    from mechaharness.external_effect import EffectDispatchResult
    from mechaharness.host_kit import SubmitOnceEffectfulRunner

    async def submit(node: Any, effect: Any, context: Any) -> EffectDispatchResult:
        del effect, context
        spec = BackendSubmitSpec(
            task_id=str(node.payload.get("task_id") or ""),
            instruction=str(node.payload.get("instruction") or node.goal or ""),
            acceptance_criteria=list(node.payload.get("acceptance_criteria") or []),
            workspace=dict(node.payload.get("workspace") or {}),
            metadata=dict(node.payload.get("metadata") or {}),
        )
        handle = backend.submit(spec)
        return EffectDispatchResult(
            external_handle=handle.external_run_id,
            detail={"backend_id": handle.backend_id, **handle.detail},
        )

    return SubmitOnceEffectfulRunner(
        kinds=["june.coding_job"],
        backend_id=backend.backend_id,
        submit=submit,
    )
