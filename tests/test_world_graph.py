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
    assert "june.console.cron:chat" in by_id
    assert "june.console.cron:imagegen" not in by_id
    assert "june.console.cron:bucket:minute" in by_id
    assert "june.console.cron:bucket:hourly" in by_id
    assert "june.console.cron:bucket:10s" not in by_id
    bucket = by_id["june.console.cron:bucket:minute"]
    # Empty tick: one event_log child.
    assert len(bucket.children) == 1
    assert world.width >= bucket.w


def test_world_attaches_overlapping_instances() -> None:
    checkpoint = _cron_checkpoint()
    bucket = checkpoint["nodes"]["june.console.cron:bucket:minute"]
    pipeline = bucket["subgraph"]
    instances = [
        {
            "run_id": "june.console.cron:minute:instAAAA",
            "bucket": "minute",
            "parent_node_id": "june.console.cron:bucket:minute",
            "status": "running",
            "pipeline": pipeline,
            "started_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "run_id": "june.console.cron:minute:instBBBB",
            "bucket": "minute",
            "parent_node_id": "june.console.cron:bucket:minute",
            "status": "running",
            "pipeline": pipeline,
            "started_at": "2026-01-01T00:01:00+00:00",
        },
    ]
    world = build_world_graph(
        checkpoint, [], run_id="june.console.cron", instances=instances
    )
    bucket_node = next(n for n in world.nodes if n.id.endswith(":bucket:minute"))
    instance_ids = {
        c.id
        for c in bucket_node.children
        if c.id.startswith("june.console.cron:minute:")
    }
    assert "june.console.cron:minute:instAAAA" in instance_ids
    assert "june.console.cron:minute:instBBBB" in instance_ids
    assert bucket_node.status == "running"
    assert bucket_node.execution == "running"


def test_world_stack_hides_older_instances_behind_badge() -> None:
    checkpoint = _cron_checkpoint()
    bucket = checkpoint["nodes"]["june.console.cron:bucket:minute"]
    pipeline = bucket["subgraph"]
    parent = "june.console.cron:bucket:minute"
    instances = [
        {
            "run_id": f"june.console.cron:minute:inst{i:04d}",
            "bucket": "minute",
            "parent_node_id": parent,
            "status": "ok" if i < 2 else "running",
            "pipeline": pipeline,
            "started_at": f"2026-01-01T00:0{i}:00+00:00",
            "finished_at": f"2026-01-01T00:0{i}:05+00:00" if i < 2 else None,
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
    checkpoint["nodes"]["june.console.cron:bucket:minute"]["status"] = "succeeded"
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:minute"]["subgraph"]
    instances = [
        {
            "run_id": "june.console.cron:minute:live0001",
            "bucket": "minute",
            "parent_node_id": "june.console.cron:bucket:minute",
            "status": "running",
            "pipeline": pipeline,
            "started_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    world = build_world_graph(
        checkpoint, [], run_id="june.console.cron", instances=instances
    )
    bucket_node = next(n for n in world.nodes if n.id.endswith(":bucket:minute"))
    assert bucket_node.execution == "running"
    assert bucket_node.status == "running"


def test_main_graph_stack_cards_stay_compact_with_deep_pipeline() -> None:
    """Chat-like nests must not blow up overview chambers / camera fit."""
    from june.console.world import STACK_CARD_H, STACK_CARD_W

    checkpoint = {
        "id": "ui-demo",
        "goal": "overview",
        "nodes": {
            "chat": {
                "id": "chat",
                "kind": "conversational_tool_loop",
                "goal": "chat",
                "status": "pending",
                "payload": {},
                "subgraph": {
                    "id": "chat-steps",
                    "nodes": {
                        "refine": {"id": "refine", "kind": "soft_point", "status": "pending"},
                        "tools": {"id": "tools", "kind": "tool_loop", "status": "pending"},
                    },
                    "edges": [
                        {
                            "from_node": "refine",
                            "to_node": "tools",
                            "types": ["control"],
                            "reason": "seq",
                        }
                    ],
                },
            }
        },
        "edges": [],
    }
    # Deep finished run (nested dives) — watch dialog still expands this;
    # overview stack cards must stay compact.
    deep_pipeline = {
        "id": "chat-run",
        "nodes": {
            "tools": {
                "id": "tools",
                "kind": "conversational_tool_loop",
                "status": "succeeded",
                "subgraph": {
                    "id": "tools-inner",
                    "nodes": {
                        f"dive:{i}": {
                            "id": f"dive:{i}",
                            "kind": "tool_call",
                            "status": "succeeded",
                            "payload": {"tool_name": "generate_image", "recipe_as_tool": True},
                            "subgraph": {
                                "id": f"inner:{i}",
                                "nodes": {
                                    f"s:{i}:{j}": {
                                        "id": f"s:{i}:{j}",
                                        "kind": "june.task",
                                        "status": "succeeded",
                                        "goal": f"step {j}",
                                    }
                                    for j in range(4)
                                },
                                "edges": [],
                            },
                        }
                        for i in range(4)
                    },
                    "edges": [],
                },
            }
        },
        "edges": [],
    }
    instances = [
        {
            "run_id": "chat:deep0001",
            "bucket": "chat",
            "parent_node_id": "chat",
            "status": "ok",
            "pipeline": deep_pipeline,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00",
        }
    ]
    world = build_world_graph(checkpoint, [], run_id="ui-demo", instances=instances)
    chat = next(n for n in world.nodes if n.id == "chat")
    card = next(c for c in chat.children if c.stack_role == "front")
    assert card.w == STACK_CARD_W
    assert card.h == STACK_CARD_H
    assert card.children == []
    # Parent should stay near template + compact card, not thousands of px tall.
    assert chat.h < 500
    assert world.height < 700


def test_build_instance_world_exposes_pipeline_children() -> None:
    from june.console.world import build_instance_world

    checkpoint = _cron_checkpoint()
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:minute"]["subgraph"]
    inst = {
        "run_id": "june.console.cron:minute:watch0001",
        "bucket": "minute",
        "parent_node_id": "june.console.cron:bucket:minute",
        "status": "running",
        "pipeline": pipeline,
        "started_at": "2026-01-01T00:00:00+00:00",
        "active_node_id": None,
    }
    world = build_instance_world(inst)
    assert world.root_id.endswith("watch0001")
    assert len(world.nodes) == 1
    assert len(world.nodes[0].children) == 1
    assert world.nodes[0].execution == "running"


def test_hub_instance_world_endpoint_payload() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    checkpoint = _cron_checkpoint()
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:minute"]["subgraph"]
    hub.begin_instance(
        run_id="june.console.cron:minute:api0001",
        bucket="minute",
        parent_node_id="june.console.cron:bucket:minute",
        pipeline=pipeline,
    )
    world = hub.instance_world("june.console.cron:minute:api0001")
    assert world is not None
    assert world["nodes"][0]["id"].endswith("api0001")
    assert hub.instance_world("missing") is None


def test_finished_bucket_stays_recent_when_instances_remain() -> None:
    checkpoint = _cron_checkpoint()
    checkpoint["nodes"]["june.console.cron:bucket:hourly"]["status"] = "succeeded"
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:hourly"]["subgraph"]
    instances = [
        {
            "run_id": "june.console.cron:hourly:done0001",
            "bucket": "hourly",
            "parent_node_id": "june.console.cron:bucket:hourly",
            "status": "ok",
            "pipeline": pipeline,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:02+00:00",
        }
    ]
    world = build_world_graph(
        checkpoint, [], run_id="june.console.cron", instances=instances
    )
    bucket = next(n for n in world.nodes if n.id.endswith(":bucket:hourly"))
    assert bucket.execution == "recent"
    assert any(c.id.endswith("done0001") for c in bucket.children)


def test_hub_keeps_finished_instances_per_bucket() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    pipeline = {"id": "p", "goal": "t", "nodes": {}, "edges": []}
    # Flood minute finished runs past the old global cap of 6.
    for i in range(8):
        rid = f"june.console.cron:minute:keep{i:04d}"
        hub.begin_instance(
            run_id=rid,
            bucket="minute",
            parent_node_id="june.console.cron:bucket:minute",
            pipeline=pipeline,
        )
        hub.complete_instance(run_id=rid, status="ok", pipeline=pipeline)
    hub.begin_instance(
        run_id="june.console.cron:hourly:keepme01",
        bucket="hourly",
        parent_node_id="june.console.cron:bucket:hourly",
        pipeline=pipeline,
    )
    hub.complete_instance(
        run_id="june.console.cron:hourly:keepme01", status="ok", pipeline=pipeline
    )
    snap = hub.snapshot().to_dict()
    ids = {i["run_id"] for i in snap["instances"]}
    assert "june.console.cron:hourly:keepme01" in ids
    minute = [i for i in snap["instances"] if i["bucket"] == "minute"]
    assert len(minute) == 4  # per-bucket finished cap


def test_hub_instance_node_detail() -> None:
    from june.console.hub import ConsoleHub

    hub = ConsoleHub()
    run_id = "june.console.cron:minute:detail01"
    pipeline = {
        "id": run_id,
        "goal": "minute tick",
        "nodes": {
            f"{run_id}:log:0": {
                "id": f"{run_id}:log:0",
                "kind": "june.event_log",
                "goal": "minute tick",
                "status": "succeeded",
            },
        },
        "edges": [],
    }
    hub.begin_instance(
        run_id=run_id,
        bucket="minute",
        parent_node_id="june.console.cron:bucket:minute",
        pipeline=pipeline,
    )
    root = hub.instance_node_detail(run_id, run_id)
    assert root is not None
    assert root["kind"] == "instance"
    step = hub.instance_node_detail(run_id, f"{run_id}:log:0")
    assert step is not None
    assert step["node"]["goal"] == "minute tick"
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
    assert "june.console.cron:bucket:minute" in ids
    assert "june.console.cron:bucket:hourly" in ids
    assert "june.console.cron:chat" in ids
    assert "demo-run:0" not in ids
    assert snap["status"] == "succeeded"
    assert "event_rate" in snap
    assert "bins" in snap["event_rate"]
    assert "instances" in snap
    assert isinstance(snap["instances"], list)
