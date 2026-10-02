"""Console cron graph: 10s / 60s buckets with event-log subgraph nodes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

CONSOLE_CRON_RUN_ID = "june.console.cron"


def build_console_cron_graph(run_id: str | None = None) -> Any:
    """Build the MechaHarness graph shown in the console (structure + subgraphs)."""
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode

    rid = run_id or CONSOLE_CRON_RUN_ID
    graph = ExecutionGraph(id=rid, goal="June console cron scheduler")

    def _bucket_subgraph(bucket_key: str, title: str, messages: list[str]) -> dict[str, Any]:
        sub = ExecutionGraph(id=f"{rid}:bucket:{bucket_key}", goal=title)
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
        goal="10 second bucket",
        payload={"firmness": "soft", "interval_seconds": 10, "bucket": "10s"},
        subgraph=_bucket_subgraph(
            "10s",
            "10 second bucket",
            ["align 10s window", "emit heartbeat", "flush event buffer"],
        ),
    )
    bucket_60s = GraphNode(
        id=f"{rid}:bucket:60s",
        kind="subgraph",
        goal="1 minute bucket",
        payload={"firmness": "soft", "interval_seconds": 60, "bucket": "60s"},
        subgraph=_bucket_subgraph(
            "60s",
            "1 minute bucket",
            ["rollup minute metrics", "snapshot graph scene"],
        ),
    )
    cron_hub = GraphNode(
        id=f"{rid}:cron",
        kind="june.cron",
        goal="cron tick dispatcher",
        payload={"firmness": "soft"},
    )

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
            from_node=cron_hub.id,
            to_node=bucket_60s.id,
            types=["control"],
            reason="dispatch 60s bucket",
        )
    )
    return graph


def new_bucket_run_id(bucket: str) -> str:
    return f"{CONSOLE_CRON_RUN_ID}:{bucket}:{uuid4().hex[:8]}"
