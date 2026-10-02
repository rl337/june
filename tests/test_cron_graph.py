"""Console cron graph structure."""

from __future__ import annotations

from june.harness.cron_graph import CONSOLE_CRON_RUN_ID, build_console_cron_graph


def test_cron_graph_has_buckets_and_event_log_nodes() -> None:
    graph = build_console_cron_graph()
    assert graph.id == CONSOLE_CRON_RUN_ID
    assert f"{CONSOLE_CRON_RUN_ID}:bucket:10s" in graph.nodes
    assert f"{CONSOLE_CRON_RUN_ID}:bucket:60s" in graph.nodes
    bucket = graph.nodes[f"{CONSOLE_CRON_RUN_ID}:bucket:10s"]
    assert bucket.subgraph is not None
    sub_nodes = bucket.subgraph.get("nodes") or {}
    kinds = {raw.get("kind") for raw in sub_nodes.values() if isinstance(raw, dict)}
    assert "june.event_log" in kinds
