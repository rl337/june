"""Console cron graph: minute / hourly empty-event buckets + soft lanes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

CONSOLE_CRON_RUN_ID = "june.console.cron"

# Empty tick buckets only — no overlapping timed pipelines.
CRON_BUCKETS = (
    ("minute", 60, "minute tick"),
    ("hourly", 3600, "hourly tick"),
)


def build_console_cron_graph(run_id: str | None = None) -> Any:
    """Build the MechaHarness graph shown in the console (structure + subgraphs)."""
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode

    rid = run_id or CONSOLE_CRON_RUN_ID
    graph = ExecutionGraph(id=rid, goal="June console cron scheduler")

    def _empty_tick(bucket_key: str, message: str) -> dict[str, Any]:
        sub = ExecutionGraph(
            id=f"{rid}:bucket:{bucket_key}:pipeline",
            goal=f"{bucket_key} tick",
        )
        sub.add_node(
            GraphNode(
                id=f"{rid}:bucket:{bucket_key}:log:0",
                kind="june.event_log",
                goal=message,
                payload={
                    "message": message,
                    "firmness": "hard",
                    "bucket": bucket_key,
                },
            )
        )
        return sub.checkpoint()

    cron_hub = GraphNode(
        id=f"{rid}:cron",
        kind="june.cron",
        goal="cron",
        payload={"firmness": "soft"},
    )
    graph.add_node(cron_hub)

    for bucket_key, interval_seconds, message in CRON_BUCKETS:
        node = GraphNode(
            id=f"{rid}:bucket:{bucket_key}",
            kind="subgraph",
            goal=f"{bucket_key} bucket",
            payload={
                "firmness": "soft",
                "interval_seconds": interval_seconds,
                "bucket": bucket_key,
            },
            subgraph=_empty_tick(bucket_key, message),
        )
        graph.add_node(node)
        graph.add_dependency(
            DependencyEdge(
                from_node=cron_hub.id,
                to_node=node.id,
                types=["control"],
                reason=f"dispatch {bucket_key} bucket",
            )
        )

    chat = GraphNode(
        id=f"{rid}:chat",
        kind="subgraph",
        goal="chat",
        payload={"firmness": "soft", "channel": "webapp", "template": "june.chat"},
        subgraph=_chat_pipeline_template(rid),
    )
    # Imagegen nests under chat tools → tool_call (HF-08); no parallel soft lane.
    graph.add_node(chat)
    graph.add_dependency(
        DependencyEdge(
            from_node=cron_hub.id,
            to_node=chat.id,
            types=["control"],
            reason="interactive chat lane",
        )
    )
    return graph


CHAT_PARENT_NODE_ID = f"{CONSOLE_CRON_RUN_ID}:chat"


def _linear_soft_pipeline(
    rid: str,
    *,
    lane: str,
    goal: str,
    steps: tuple[tuple[str, str, str], ...],
) -> dict[str, Any]:
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode

    sub = ExecutionGraph(id=f"{rid}:{lane}:pipeline", goal=goal)
    prev: str | None = None
    for key, kind, title in steps:
        node_id = f"{rid}:{lane}:step:{key}"
        sub.add_node(
            GraphNode(
                id=node_id,
                kind=kind,
                goal=title,
                payload={"firmness": "soft", "phase": key},
            )
        )
        if prev is not None:
            sub.add_dependency(
                DependencyEdge(
                    from_node=prev,
                    to_node=node_id,
                    types=["control"],
                    reason=f"{lane} phase",
                )
            )
        prev = node_id
    return sub.checkpoint()


def _chat_pipeline_template(rid: str) -> dict[str, Any]:
    """Structure template for the incubating june.chat phases."""
    return _linear_soft_pipeline(
        rid,
        lane="chat",
        goal="june.chat",
        steps=(
            ("refine", "june.chat.refine_input", "refine input"),
            ("context", "june.chat.context_optimize", "context optimize"),
            ("tools", "conversational_tool_loop", "tool loop"),
            ("render", "june.chat.render_reply", "render reply"),
        ),
    )


def new_chat_run_id() -> str:
    return f"{CONSOLE_CRON_RUN_ID}:chat:{uuid4().hex[:8]}"


def chat_pipeline_for_instance(instance_id: str) -> dict[str, Any]:
    """Clone the chat phase template with instance-scoped node ids."""
    template = _chat_pipeline_template(CONSOLE_CRON_RUN_ID)
    return clone_pipeline_for_instance(template, instance_id)


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
