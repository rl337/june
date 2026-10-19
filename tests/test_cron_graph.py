"""Console cron graph structure."""

from __future__ import annotations

import pytest

pytest.importorskip("mechaharness")

from june.harness.cron_graph import (
    CONSOLE_CRON_RUN_ID,
    CRON_BUCKETS,
    build_console_cron_graph,
    clone_pipeline_for_instance,
)


def test_cron_graph_has_minute_and_hourly_empty_ticks() -> None:
    graph = build_console_cron_graph()
    assert graph.id == CONSOLE_CRON_RUN_ID
    assert f"{CONSOLE_CRON_RUN_ID}:bucket:10s" not in graph.nodes
    assert f"{CONSOLE_CRON_RUN_ID}:chat" in graph.nodes
    assert f"{CONSOLE_CRON_RUN_ID}:imagegen" not in graph.nodes
    for bucket_key, interval_seconds, message in CRON_BUCKETS:
        node_id = f"{CONSOLE_CRON_RUN_ID}:bucket:{bucket_key}"
        assert node_id in graph.nodes
        bucket = graph.nodes[node_id]
        assert bucket.payload.get("interval_seconds") == interval_seconds
        assert bucket.subgraph is not None
        sub_nodes = bucket.subgraph.get("nodes") or {}
        assert len(sub_nodes) == 1
        raw = next(iter(sub_nodes.values()))
        assert isinstance(raw, dict)
        assert raw.get("kind") == "june.event_log"
        assert raw.get("goal") == message
    chat = graph.nodes[f"{CONSOLE_CRON_RUN_ID}:chat"]
    assert chat.subgraph is not None
    assert len(chat.subgraph.get("nodes") or {}) == 4
    tools = next(
        n
        for n in (chat.subgraph.get("nodes") or {}).values()
        if isinstance(n, dict) and n.get("kind") == "conversational_tool_loop"
    )
    assert tools.get("goal") == "tool loop"


def test_clone_pipeline_scopes_instance_ids() -> None:
    graph = build_console_cron_graph()
    bucket = graph.nodes[f"{CONSOLE_CRON_RUN_ID}:bucket:minute"]
    cloned = clone_pipeline_for_instance(
        bucket.subgraph, "june.console.cron:minute:abcd1234"
    )
    assert cloned["id"] == "june.console.cron:minute:abcd1234"
    nodes = cloned["nodes"]
    assert all(nid.startswith("june.console.cron:minute:abcd1234:") for nid in nodes)
    assert len(nodes) == 1
