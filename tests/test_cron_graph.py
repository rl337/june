"""Console cron graph structure."""

from __future__ import annotations

import pytest

pytest.importorskip("mechaharness")

from june.harness.cron_graph import (
    BUCKET_10S_STEPS,
    CONSOLE_CRON_RUN_ID,
    build_console_cron_graph,
    clone_pipeline_for_instance,
)


def test_cron_graph_has_timed_10s_pipeline() -> None:
    graph = build_console_cron_graph()
    assert graph.id == CONSOLE_CRON_RUN_ID
    assert f"{CONSOLE_CRON_RUN_ID}:bucket:10s" in graph.nodes
    assert f"{CONSOLE_CRON_RUN_ID}:bucket:60s" in graph.nodes
    bucket = graph.nodes[f"{CONSOLE_CRON_RUN_ID}:bucket:10s"]
    assert bucket.subgraph is not None
    sub_nodes = bucket.subgraph.get("nodes") or {}
    kinds = {raw.get("kind") for raw in sub_nodes.values() if isinstance(raw, dict)}
    assert kinds == {"june.timed_log"}
    assert len(sub_nodes) == len(BUCKET_10S_STEPS)


def test_clone_pipeline_scopes_instance_ids() -> None:
    graph = build_console_cron_graph()
    bucket = graph.nodes[f"{CONSOLE_CRON_RUN_ID}:bucket:10s"]
    cloned = clone_pipeline_for_instance(bucket.subgraph, "june.console.cron:10s:abcd1234")
    assert cloned["id"] == "june.console.cron:10s:abcd1234"
    nodes = cloned["nodes"]
    assert all(nid.startswith("june.console.cron:10s:abcd1234:") for nid in nodes)
    assert len(nodes) == len(BUCKET_10S_STEPS)
