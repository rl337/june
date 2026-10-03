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


def test_console_api_instance_world() -> None:
    pytest = __import__("pytest")
    fastapi = pytest.importorskip("fastapi")
    del fastapi
    from fastapi.testclient import TestClient

    from june.console.hub import ConsoleHub
    from june.console.server import create_app
    from june.harness.cron_graph import build_console_cron_graph

    hub = ConsoleHub()
    checkpoint = build_console_cron_graph().checkpoint()
    pipeline = checkpoint["nodes"]["june.console.cron:bucket:10s"]["subgraph"]
    run_id = "june.console.cron:10s:watchapi1"
    hub.begin_instance(
        run_id=run_id,
        bucket="10s",
        parent_node_id="june.console.cron:bucket:10s",
        pipeline=pipeline,
    )
    client = TestClient(create_app(hub))
    missing = client.get("/api/instance/does-not-exist/world")
    assert missing.status_code == 404
    ok = client.get(f"/api/instance/{run_id}/world")
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["run_id"] == run_id
    assert payload["world"]["nodes"][0]["id"] == run_id
    assert len(payload["world"]["nodes"][0]["children"]) == 4


def test_console_api_instance_node_detail() -> None:
    pytest = __import__("pytest")
    fastapi = pytest.importorskip("fastapi")
    del fastapi
    from fastapi.testclient import TestClient

    from june.console.hub import ConsoleHub
    from june.console.server import create_app
    from june.harness.cron_graph import build_console_cron_graph, clone_pipeline_for_instance

    hub = ConsoleHub()
    checkpoint = build_console_cron_graph().checkpoint()
    template = checkpoint["nodes"]["june.console.cron:bucket:10s"]["subgraph"]
    run_id = "june.console.cron:10s:nodedet01"
    pipeline = clone_pipeline_for_instance(template, run_id)
    hub.begin_instance(
        run_id=run_id,
        bucket="10s",
        parent_node_id="june.console.cron:bucket:10s",
        pipeline=pipeline,
    )
    client = TestClient(create_app(hub))

    root = client.get(f"/api/instance/{run_id}/node/{run_id}")
    assert root.status_code == 200
    root_body = root.json()
    assert root_body["kind"] == "instance"
    assert root_body["node_count"] == 4

    step_id = f"{run_id}:step:0"
    step = client.get(f"/api/instance/{run_id}/node/{step_id}")
    assert step.status_code == 200
    step_body = step.json()
    assert step_body["node_id"] == step_id
    assert step_body["node"]["goal"] == "acquire window"
    assert step_body["node"]["kind"] == "june.timed_log"

    missing = client.get(f"/api/instance/{run_id}/node/does-not-exist")
    assert missing.status_code == 404
