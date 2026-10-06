"""Hierarchical world graph sizing for continuous zoom."""

from __future__ import annotations

import pytest

from june.console.world import build_world_graph


def _cron_checkpoint():
    pytest.importorskip("mechaharness")
    from june.harness.cron_graph import build_console_cron_graph

    return build_console_cron_graph().checkpoint()


def test_world_graph_sizes_buckets_by_subgraph_content() -> None:
    checkpoint = _cron_checkpoint()
    world = build_world_graph(checkpoint, [], run_id="june.console.cron")
    assert len(world.nodes) == 4
    by_id = {n.id: n for n in world.nodes}
    bucket = by_id["june.console.cron:bucket:10s"]
    leaf = by_id["june.console.cron:cron"]
    # Vertical pipeline: taller than a leaf, four timed steps.
    assert bucket.h > leaf.h
    assert len(bucket.children) == 4
    assert world.width >= bucket.w


def test_world_attaches_overlapping_instances() -> None:
    checkpoint = _cron_checkpoint()
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
    instance_ids = {
        c.id for c in bucket_node.children if c.id.startswith("june.console.cron:10s:")
    }
    assert "june.console.cron:10s:instAAAA" in instance_ids
    assert "june.console.cron:10s:instBBBB" in instance_ids
    # Parent bucket stays running while stacked instances are live.
    assert bucket_node.status == "running"
    assert bucket_node.execution == "running"


def test_world_stack_hides_older_instances_behind_badge() -> None:
    checkpoint = _cron_checkpoint()
    bucket = checkpoint["nodes"]["june.console.cron:bucket:10s"]
    pipeline = bucket["subgraph"]
    parent = "june.console.cron:bucket:10s"
    instances = [
        {
            "run_id": f"june.console.cron:10s:inst{i:04d}",
            "bucket": "10s",
            "parent_node_id": parent,
            "status": "ok" if i < 2 else "running",
            "pipeline": pipeline,
            "started_at": f"2026-01-01T00:00:{i:02d}+00:00",
            "finished_at": f"2026-01-01T00:00:{i + 5:02d}+00:00" if i < 2 else None,
        }
        for i in range(4)
    ]
    world = build_world_graph(
        checkpoint, [], run_id="june.console.cron", instances=instances
    )
    bucket_node = next(n for n in world.nodes if n.id == parent)
    roles = {c.stack_role for c in bucket_node.children if c.stack_role}
    assert "front" in roles
    assert "back" in roles
    assert "badge" in roles
    badge = next(c for c in bucket_node.children if c.stack_role == "badge")
    assert badge.label.startswith("+")
    assert bucket_node.execution == "running"


def test_propagate_running_marks_idle_parent_when_child_runs() -> None:
    checkpoint = _cron_checkpoint()
    # Force the structure bucket idle; a live instance should re-light it.
    checkpoint["nodes"]["june.console.cron:bucket:10s"]["status"] = "succeeded"
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:10s"]["subgraph"]
    instances = [
        {
            "run_id": "june.console.cron:10s:live0001",
            "bucket": "10s",
            "parent_node_id": "june.console.cron:bucket:10s",
            "status": "running",
            "pipeline": pipeline,
            "started_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    world = build_world_graph(
        checkpoint, [], run_id="june.console.cron", instances=instances
    )
    bucket_node = next(n for n in world.nodes if n.id.endswith(":bucket:10s"))
    assert bucket_node.execution == "running"
    assert bucket_node.status == "running"


def test_build_instance_world_exposes_pipeline_children() -> None:
    from june.console.world import build_instance_world

    checkpoint = _cron_checkpoint()
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:10s"]["subgraph"]
    inst = {
        "run_id": "june.console.cron:10s:watch0001",
        "bucket": "10s",
        "parent_node_id": "june.console.cron:bucket:10s",
        "status": "running",
        "pipeline": pipeline,
        "started_at": "2026-01-01T00:00:00+00:00",
        "active_node_id": None,
    }
    world = build_instance_world(inst)
    assert world.root_id.endswith("watch0001")
    assert len(world.nodes) == 1
    assert len(world.nodes[0].children) == 4
    assert world.nodes[0].execution == "running"


def test_hub_instance_world_endpoint_payload() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    checkpoint = _cron_checkpoint()
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:10s"]["subgraph"]
    hub.begin_instance(
        run_id="june.console.cron:10s:api0001",
        bucket="10s",
        parent_node_id="june.console.cron:bucket:10s",
        pipeline=pipeline,
    )
    world = hub.instance_world("june.console.cron:10s:api0001")
    assert world is not None
    assert world["nodes"][0]["id"].endswith("api0001")
    assert hub.instance_world("missing") is None


def test_finished_bucket_stays_recent_when_instances_remain() -> None:
    checkpoint = _cron_checkpoint()
    checkpoint["nodes"]["june.console.cron:bucket:60s"]["status"] = "succeeded"
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:60s"]["subgraph"]
    instances = [
        {
            "run_id": "june.console.cron:60s:done0001",
            "bucket": "60s",
            "parent_node_id": "june.console.cron:bucket:60s",
            "status": "ok",
            "pipeline": pipeline,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:02+00:00",
        }
    ]
    world = build_world_graph(
        checkpoint, [], run_id="june.console.cron", instances=instances
    )
    bucket = next(n for n in world.nodes if n.id.endswith(":bucket:60s"))
    assert bucket.execution == "recent"
    assert any(c.id.endswith("done0001") for c in bucket.children)


def test_hub_keeps_finished_instances_per_bucket() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    pipeline = {"id": "p", "goal": "t", "nodes": {}, "edges": []}
    # Flood 10s finished runs past the old global cap of 6.
    for i in range(8):
        rid = f"june.console.cron:10s:keep{i:04d}"
        hub.begin_instance(
            run_id=rid,
            bucket="10s",
            parent_node_id="june.console.cron:bucket:10s",
            pipeline=pipeline,
        )
        hub.complete_instance(run_id=rid, status="ok", pipeline=pipeline)
    hub.begin_instance(
        run_id="june.console.cron:60s:keepme01",
        bucket="60s",
        parent_node_id="june.console.cron:bucket:60s",
        pipeline=pipeline,
    )
    hub.complete_instance(
        run_id="june.console.cron:60s:keepme01", status="ok", pipeline=pipeline
    )
    snap = hub.snapshot().to_dict()
    ids = {i["run_id"] for i in snap["instances"]}
    assert "june.console.cron:60s:keepme01" in ids
    ten = [i for i in snap["instances"] if i["bucket"] == "10s"]
    assert len(ten) == 4  # per-bucket finished cap


def test_hub_instance_node_detail() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    run_id = "june.console.cron:10s:detail01"
    pipeline = {
        "id": run_id,
        "goal": "10s timed pipeline",
        "nodes": {
            f"{run_id}:step:0": {
                "id": f"{run_id}:step:0",
                "kind": "june.timed_log",
                "goal": "acquire window",
                "status": "succeeded",
            },
            f"{run_id}:step:2": {
                "id": f"{run_id}:step:2",
                "kind": "june.timed_log",
                "goal": "emit heartbeat",
                "status": "succeeded",
            },
        },
        "edges": [],
    }
    hub.begin_instance(
        run_id=run_id,
        bucket="10s",
        parent_node_id="june.console.cron:bucket:10s",
        pipeline=pipeline,
    )
    root = hub.instance_node_detail(run_id, run_id)
    assert root is not None
    assert root["kind"] == "instance"
    step = hub.instance_node_detail(run_id, f"{run_id}:step:2")
    assert step is not None
    assert step["node"]["goal"] == "emit heartbeat"
    assert hub.instance_node_detail(run_id, "missing") is None
    assert hub.instance_node_detail("missing", "x") is None


def test_world_included_in_hub_snapshot() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    hub.set_structure_checkpoint(_cron_checkpoint())
    snap = hub.snapshot().to_dict()
    assert "world" in snap
    assert len(snap["world"]["nodes"]) == 4


def test_complete_run_preserves_structure_checkpoint() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    hub.set_structure_checkpoint(_cron_checkpoint())
    hub.complete_run(
        run_id="demo-run",
        status="succeeded",
        checkpoint={
            "id": "demo-run",
            "goal": "console demo",
            "nodes": {
                "demo-run:0": {
                    "id": "demo-run:0",
                    "kind": "june.task",
                    "goal": "console demo",
                    "status": "succeeded",
                    "payload": {},
                }
            },
            "edges": [],
        },
    )
    snap = hub.snapshot().to_dict()
    ids = {n["id"] for n in snap["world"]["nodes"]}
    assert "june.console.cron:bucket:10s" in ids
    assert "june.console.cron:chat" in ids
    assert "demo-run:0" not in ids
    assert snap["status"] == "succeeded"
    assert "event_rate" in snap
    assert "bins" in snap["event_rate"]
    assert "instances" in snap
    assert isinstance(snap["instances"], list)
