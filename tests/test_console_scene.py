"""Web console scene composition."""

from __future__ import annotations

from june.console.hub import ConsoleHub
from june.console.scene import ROOT_SCENE_ID, build_scene_frame, node_shape
from june.harness.visualization import GRAPH_NODE_END, GRAPH_NODE_START


class _Event:
    def __init__(self, *, type: str, run_id: str, payload: dict) -> None:
        self.type = type
        self.run_id = run_id
        self.payload = payload


def test_node_shape_hard_vs_soft() -> None:
    assert node_shape("june.task", {}) == "rect"
    assert node_shape("subgraph", {}) == "round_rect"
    assert node_shape("compute", {"firmness": "soft"}) == "round_rect"


def test_root_scene_lists_foreground_pipeline() -> None:
    run_id = "run-1"
    checkpoint = {
        "goal": "demo",
        "nodes": {
            "run-1:0": {
                "kind": "june.task",
                "status": "succeeded",
                "goal": "a",
                "payload": {"context_refs": [{"title": "doc"}]},
            },
            "run-1:1": {
                "kind": "june.task",
                "status": "running",
                "goal": "b",
                "payload": {"context_refs": [{"title": "live-doc", "summary": "ctx"}]},
            },
        },
        "edges": [
            {
                "from_node": "run-1:0",
                "to_node": "run-1:1",
                "types": ["control"],
                "reason": "seq",
            }
        ],
    }
    events = [
        _Event(type=GRAPH_NODE_START, run_id=run_id, payload={"node_id": "run-1:1"}),
    ]
    frame = build_scene_frame(
        checkpoint,
        events,
        run_id=run_id,
        selected_node_id=ROOT_SCENE_ID,
    )
    fg = [n for n in frame.nodes if n.layer == "foreground"]
    bg = [n for n in frame.nodes if n.layer == "background"]
    assert len(fg) == 2
    assert any(n.execution == "running" for n in fg)
    assert bg and bg[0].shape == "round_rect"
    assert frame.active_node_id == "run-1:1"


def test_recent_nodes_dim_after_end() -> None:
    run_id = "r1"
    checkpoint = {
        "goal": "g",
        "nodes": {
            "n0": {"kind": "june.task", "status": "succeeded"},
            "n1": {"kind": "june.task", "status": "running"},
        },
        "edges": [],
    }
    events = [
        _Event(type=GRAPH_NODE_START, run_id=run_id, payload={"node_id": "n0"}),
        _Event(type=GRAPH_NODE_END, run_id=run_id, payload={"node_id": "n0", "status": "succeeded"}),
        _Event(type=GRAPH_NODE_START, run_id=run_id, payload={"node_id": "n1"}),
    ]
    frame = build_scene_frame(checkpoint, events, run_id=run_id, selected_node_id=ROOT_SCENE_ID)
    by_id = {n.id: n for n in frame.nodes if n.layer == "foreground"}
    assert by_id["n0"].execution in {"recent", "dim"}
    assert by_id["n1"].execution == "running"


def test_hub_snapshot_after_run() -> None:
    hub = ConsoleHub()
    hub.begin_run("abc")
    hub.ingest_event(
        _Event(
            type="core:graph_node",
            run_id="abc",
            payload={
                "graph": {
                    "goal": "hub",
                    "nodes": {"x": {"kind": "june.task", "status": "pending"}},
                    "edges": [],
                }
            },
        )
    )
    snap = hub.snapshot()
    assert snap.run_id == "abc"
    assert snap.scene["scene_title"] == "hub"


def test_console_api_snapshot() -> None:
    pytest = __import__("pytest")
    fastapi = pytest.importorskip("fastapi")
    del fastapi
    from fastapi.testclient import TestClient

    from june.console.hub import ConsoleHub
    from june.console.server import create_app

    hub = ConsoleHub()
    client = TestClient(create_app(hub))
    response = client.get("/api/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert "scene" in body
    assert "event_log" in body
