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
    # Vertical pipeline: taller than a leaf, four timed steps.
    assert bucket.h > leaf.h
    assert len(bucket.children) == 4
    assert world.width >= bucket.w


def test_world_attaches_overlapping_instances() -> None:
    checkpoint = build_console_cron_graph().checkpoint()
    bucket = checkpoint["nodes"]["june.console.cron:bucket:10s"]
    pipeline = bucket["subgraph"]
    instances = [
        {
            "run_id": "june.console.cron:10s:instAAAA",
            "bucket": "10s",
            "parent_node_id": "june.console.cron:bucket:10s",
            "status": "running",
            "pipeline": pipeline,
            "started_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "run_id": "june.console.cron:10s:instBBBB",
            "bucket": "10s",
            "parent_node_id": "june.console.cron:bucket:10s",
            "status": "running",
            "pipeline": pipeline,
            "started_at": "2026-01-01T00:00:10+00:00",
        },
    ]
    world = build_world_graph(
        checkpoint, [], run_id="june.console.cron", instances=instances
    )
    bucket_node = next(n for n in world.nodes if n.id.endswith(":bucket:10s"))
    instance_ids = {c.id for c in bucket_node.children if c.id.startswith("june.console.cron:10s:")}
    assert "june.console.cron:10s:instAAAA" in instance_ids
    assert "june.console.cron:10s:instBBBB" in instance_ids



def test_world_included_in_hub_snapshot() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    hub.set_structure_checkpoint(build_console_cron_graph().checkpoint())
    snap = hub.snapshot().to_dict()
    assert "world" in snap
    assert len(snap["world"]["nodes"]) == 3
