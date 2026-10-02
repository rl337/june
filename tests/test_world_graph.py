"""Hierarchical world graph sizing for continuous zoom."""

from __future__ import annotations

from june.console.world import build_world_graph
from june.harness.cron_graph import build_console_cron_graph


def test_world_graph_sizes_buckets_by_subgraph_content() -> None:
    checkpoint = build_console_cron_graph().checkpoint()
    world = build_world_graph(checkpoint, [], run_id="june.console.cron")
    assert len(world.nodes) == 3
    by_id = {n.id: n for n in world.nodes}
    bucket = by_id["june.console.cron:bucket:10s"]
    leaf = by_id["june.console.cron:cron"]
    assert bucket.w > leaf.w
    assert bucket.h > leaf.h
    assert len(bucket.children) == 3
    assert world.width > bucket.w


def test_world_included_in_hub_snapshot() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    hub.set_structure_checkpoint(build_console_cron_graph().checkpoint())
    snap = hub.snapshot().to_dict()
    assert "world" in snap
    assert len(snap["world"]["nodes"]) == 3
