"""P0 Bubble Trouble graph viz: multi-locus frontier, roles, interiors, inspect."""

from __future__ import annotations

import pytest

from june.console.world import (
    build_world_graph,
    node_role,
    node_shape_for_role,
)

pytest.importorskip("mechaharness")


def _cron_checkpoint():
    from june.harness.cron_graph import build_console_cron_graph

    return build_console_cron_graph().checkpoint()


def test_node_role_vocabulary() -> None:
    assert node_role("inference") == "bead"
    assert node_role("tool_call", {"tool_name": "generate_image"}) == "bead"
    assert (
        node_role(
            "tool_call",
            {"recipe_as_tool": True},
            has_children=True,
            child_run_id="parent:tool",
        )
        == "dive"
    )
    assert node_role("conversational_tool_loop", repeating=True) == "chamber"
    assert node_role("june.event_log") == "door"
    assert node_role("soft_point") == "plaque"
    assert node_shape_for_role("chamber") == "round_rect"
    assert node_shape_for_role("door") == "rect"


def test_multi_locus_running_set_from_checkpoint() -> None:
    checkpoint = {
        "id": "run",
        "goal": "parallel",
        "nodes": {
            "a": {
                "id": "a",
                "kind": "branch",
                "status": "running",
                "goal": "branch a",
                "payload": {},
            },
            "b": {
                "id": "b",
                "kind": "branch",
                "status": "running",
                "goal": "branch b",
                "payload": {},
            },
            "c": {
                "id": "c",
                "kind": "reduce",
                "status": "pending",
                "goal": "join",
                "payload": {},
            },
        },
        "edges": [
            {
                "from_node": "a",
                "to_node": "c",
                "reason": "fan_in",
                "types": ["control"],
            },
            {
                "from_node": "b",
                "to_node": "c",
                "reason": "fan_in",
                "types": ["control"],
            },
        ],
    }
    world = build_world_graph(checkpoint, [], run_id="run")
    assert set(world.running_node_ids) >= {"a", "b"}
    by_id = {n.id: n for n in world.nodes}
    assert by_id["a"].execution == "running"
    assert by_id["b"].execution == "running"
    assert by_id["c"].execution == "pending"
    assert any(e.get("label") == "fan_in" for e in world.edges)


def test_failed_frontier_distinct_from_dim() -> None:
    checkpoint = {
        "id": "run",
        "goal": "fail",
        "nodes": {
            "ok": {
                "id": "ok",
                "kind": "step",
                "status": "succeeded",
                "goal": "ok",
                "payload": {},
            },
            "bad": {
                "id": "bad",
                "kind": "step",
                "status": "failed",
                "goal": "boom",
                "payload": {},
            },
        },
        "edges": [],
    }
    world = build_world_graph(checkpoint, [], run_id="run")
    by_id = {n.id: n for n in world.nodes}
    assert by_id["ok"].execution == "dim"
    assert by_id["bad"].execution == "failed"
    assert "bad" in world.failed_node_ids


def test_ancestor_occupied_when_nested_child_runs() -> None:
    checkpoint = {
        "id": "run",
        "goal": "nest",
        "nodes": {
            "tools": {
                "id": "tools",
                "kind": "conversational_tool_loop",
                "status": "succeeded",
                "goal": "tools",
                "repeating": True,
                "payload": {},
                "subgraph": {
                    "nodes": {
                        "tools/inference": {
                            "id": "tools/inference",
                            "kind": "inference",
                            "status": "succeeded",
                            "goal": "infer",
                            "payload": {},
                        },
                        "tools/tool_call:generate_image": {
                            "id": "tools/tool_call:generate_image",
                            "kind": "tool_call",
                            "status": "running",
                            "goal": "generate_image",
                            "payload": {
                                "tool_name": "generate_image",
                                "recipe_as_tool": True,
                                "child_run_id": "run:tools/tool_call:generate_image",
                                "subgraph": {
                                    "nodes": {
                                        "prompt": {
                                            "id": "prompt",
                                            "kind": "prompt",
                                            "status": "running",
                                            "goal": "prompt",
                                            "payload": {},
                                        }
                                    },
                                    "edges": [],
                                },
                            },
                        },
                    },
                    "edges": [
                        {
                            "from_node": "tools/inference",
                            "to_node": "tools/tool_call:generate_image",
                            "reason": "then",
                            "types": ["control"],
                        }
                    ],
                },
            }
        },
        "edges": [],
    }
    world = build_world_graph(checkpoint, [], run_id="run")
    tools = world.nodes[0]
    assert tools.role == "chamber"
    assert tools.execution in {"occupied", "running"}
    assert "tools/tool_call:generate_image" in world.running_node_ids
    assert "prompt" in world.running_node_ids
    dive = next(c for c in tools.children if c.id.endswith("generate_image"))
    assert dive.role == "dive"
    assert dive.tool_name == "generate_image"
    assert dive.child_run_id
    assert dive.execution == "running"
    beads = [c for c in tools.children if c.role == "bead"]
    assert any(c.kind == "inference" for c in beads)
    # Interior then-edge preserved with label.
    assert any(e.get("label") == "then" for e in tools.edges)


def test_serpentine_interior_for_wide_chamber() -> None:
    nodes = {
        f"step{i}": {
            "id": f"step{i}",
            "kind": "inference" if i % 2 == 0 else "tool_call",
            "status": "pending",
            "goal": f"step {i}",
            "payload": {"tool_name": "t"} if i % 2 else {},
        }
        for i in range(5)
    }
    checkpoint = {
        "id": "run",
        "goal": "loop",
        "nodes": {
            "tools": {
                "id": "tools",
                "kind": "conversational_tool_loop",
                "status": "pending",
                "goal": "tools",
                "repeating": True,
                "payload": {},
                "subgraph": {"nodes": nodes, "edges": []},
            }
        },
        "edges": [],
    }
    world = build_world_graph(checkpoint, [], run_id="run")
    tools = world.nodes[0]
    assert tools.role == "chamber"
    ys = sorted({round(c.y, 1) for c in tools.children})
    # Serpentine packs 5 beads into more than one row.
    assert len(ys) >= 2


def test_inspect_fields_on_world_nodes() -> None:
    checkpoint = _cron_checkpoint()
    world = build_world_graph(checkpoint, [], run_id="june.console.cron")
    payload = world.to_dict()
    assert "running_node_ids" in payload
    assert "failed_node_ids" in payload
    sample = payload["nodes"][0]
    assert "role" in sample
    assert "tool_name" in sample
    assert "child_run_id" in sample
    assert "bindings" in sample
    # Cron tops with subgraph content are chambers.
    assert any(n["role"] == "chamber" for n in payload["nodes"])


def test_cron_edge_reasons_surface_as_labels() -> None:
    checkpoint = _cron_checkpoint()
    world = build_world_graph(checkpoint, [], run_id="june.console.cron")
    labels = {e.get("label") for e in world.edges if e.get("label")}
    assert labels
    assert any("minute" in (lab or "") or "chat" in (lab or "") for lab in labels)


def test_layered_layout_keeps_fanout_in_separate_column() -> None:
    """Cron left, buckets stacked right — edge channel between ranks."""
    checkpoint = _cron_checkpoint()
    world = build_world_graph(checkpoint, [], run_id="june.console.cron")
    by_id = {n.id: n for n in world.nodes}
    cron = by_id["june.console.cron:cron"]
    minute = by_id["june.console.cron:bucket:minute"]
    hourly = by_id["june.console.cron:bucket:hourly"]
    chat = by_id["june.console.cron:chat"]
    # Source rank left of dependents.
    assert cron.x + cron.w < minute.x
    assert cron.x + cron.w < hourly.x
    assert cron.x + cron.w < chat.x
    # Dependents share a column (similar x), stacked vertically.
    assert abs(minute.x - hourly.x) < 80
    assert minute.y != hourly.y
    # Clear horizontal gap for orthogonal elbows.
    gap = minute.x - (cron.x + cron.w)
    assert gap >= 40
