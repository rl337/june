"""Console cron graph: 10s / 60s buckets with event-log subgraph nodes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

CONSOLE_CRON_RUN_ID = "june.console.cron"

# Four sequential steps × 3s each ≈ 12s, longer than the 10s cron interval so
# overlapping bucket instances are expected under load.
BUCKET_10S_STEPS = (
    "acquire window",
    "sample signals",
    "emit heartbeat",
    "flush buffers",
)
BUCKET_10S_STEP_SECONDS = 3.0


def build_console_cron_graph(run_id: str | None = None) -> Any:
    """Build the MechaHarness graph shown in the console (structure + subgraphs)."""
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode

    rid = run_id or CONSOLE_CRON_RUN_ID
    graph = ExecutionGraph(id=rid, goal="June console cron scheduler")

    def _timed_pipeline(bucket_key: str, title: str, steps: tuple[str, ...]) -> dict[str, Any]:
        sub = ExecutionGraph(id=f"{rid}:bucket:{bucket_key}:pipeline", goal=title)
        prev: str | None = None
        for idx, message in enumerate(steps):
            node_id = f"{rid}:bucket:{bucket_key}:step:{idx}"
            node = GraphNode(
                id=node_id,
                kind="june.timed_log",
                goal=message,
                payload={
                    "message": message,
                    "firmness": "hard",
                    "bucket": bucket_key,
                    "duration_seconds": BUCKET_10S_STEP_SECONDS,
                    "step_index": idx,
                },
            )
            sub.add_node(node)
            if prev is not None:
                sub.add_dependency(
                    DependencyEdge(
                        from_node=prev,
                        to_node=node_id,
                        types=["control"],
                        reason=f"{bucket_key} pipeline step",
                    )
                )
            prev = node_id
        return sub.checkpoint()

    def _quick_logs(bucket_key: str, title: str, messages: list[str]) -> dict[str, Any]:
        sub = ExecutionGraph(id=f"{rid}:bucket:{bucket_key}:pipeline", goal=title)
        prev: str | None = None
        for idx, message in enumerate(messages):
            node_id = f"{rid}:bucket:{bucket_key}:log:{idx}"
            node = GraphNode(
                id=node_id,
                kind="june.event_log",
                goal=message,
                payload={"message": message, "firmness": "hard", "bucket": bucket_key},
            )
            sub.add_node(node)
            if prev is not None:
                sub.add_dependency(
                    DependencyEdge(
                        from_node=prev,
                        to_node=node_id,
                        types=["control"],
                        reason=f"{bucket_key} bucket sequence",
                    )
                )
            prev = node_id
        return sub.checkpoint()

    bucket_10s = GraphNode(
        id=f"{rid}:bucket:10s",
        kind="subgraph",
        goal="10s bucket",
        payload={
            "firmness": "soft",
            "interval_seconds": 10,
            "bucket": "10s",
            "overlap_expected": True,
            "pipeline_seconds": BUCKET_10S_STEP_SECONDS * len(BUCKET_10S_STEPS),
        },
        subgraph=_timed_pipeline("10s", "10s timed pipeline", BUCKET_10S_STEPS),
    )
    bucket_60s = GraphNode(
        id=f"{rid}:bucket:60s",
        kind="subgraph",
        goal="60s bucket",
        payload={"firmness": "soft", "interval_seconds": 60, "bucket": "60s"},
        subgraph=_quick_logs(
            "60s",
            "60s rollup",
            ["rollup minute metrics", "snapshot graph scene"],
        ),
    )
    cron_hub = GraphNode(
        id=f"{rid}:cron",
        kind="june.cron",
        goal="cron",
        payload={"firmness": "soft"},
    )

    # Left-to-right: cron → 10s → 60s for a cleaner zoom path.
    graph.add_node(cron_hub)
    graph.add_node(bucket_10s)
    graph.add_node(bucket_60s)
    graph.add_dependency(
        DependencyEdge(
            from_node=cron_hub.id,
            to_node=bucket_10s.id,
            types=["control"],
            reason="dispatch 10s bucket",
        )
    )
    graph.add_dependency(
        DependencyEdge(
            from_node=bucket_10s.id,
            to_node=bucket_60s.id,
            types=["control"],
            reason="minute rollup after short ticks",
        )
    )
    return graph


def new_bucket_run_id(bucket: str) -> str:
    return f"{CONSOLE_CRON_RUN_ID}:{bucket}:{uuid4().hex[:8]}"


def clone_pipeline_for_instance(
    template_subgraph: dict[str, Any], instance_id: str
) -> dict[str, Any]:
    """Clone a bucket pipeline checkpoint with instance-scoped node ids."""
    from mechaharness.graph import ExecutionGraph

    template = ExecutionGraph.resume(template_subgraph)
    cloned = ExecutionGraph(id=instance_id, goal=template.goal)
    id_map: dict[str, str] = {}
    for old_id, node in template.nodes.items():
        new_id = f"{instance_id}:{old_id.split(':')[-2]}:{old_id.split(':')[-1]}"
        # Prefer stable step suffix: ...:step:N or ...:log:N
        parts = old_id.rsplit(":", 2)
        if len(parts) >= 3:
            new_id = f"{instance_id}:{parts[-2]}:{parts[-1]}"
        else:
            new_id = f"{instance_id}:{old_id}"
        id_map[old_id] = new_id
        payload = dict(node.payload or {})
        payload["instance_id"] = instance_id
        cloned.add_node(
            node.model_copy(update={"id": new_id, "payload": payload, "status": node.status})
        )
    for edge in template.edges:
        cloned.add_dependency(
            edge.model_copy(
                update={
                    "from_node": id_map[edge.from_node],
                    "to_node": id_map[edge.to_node],
                }
            )
        )
    return cloned.checkpoint()
