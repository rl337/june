"""MechaHarness graph execution visualization."""

from __future__ import annotations

from june.harness import MechaHarnessClient
from june.harness.visualization import (
    GRAPH_NODE_END,
    GRAPH_NODE_START,
    active_node_from_events,
    execution_focus_from_events,
    render_ascii,
    view_from_checkpoint,
)


class _FakeEvent:
    def __init__(self, *, type: str, run_id: str, payload: dict) -> None:
        self.type = type
        self.run_id = run_id
        self.payload = payload


def test_active_node_from_open_start_end() -> None:
    events = [
        _FakeEvent(
            type=GRAPH_NODE_START,
            run_id="r1",
            payload={"node_id": "a"},
        ),
        _FakeEvent(
            type=GRAPH_NODE_START,
            run_id="r1",
            payload={"node_id": "b"},
        ),
        _FakeEvent(
            type=GRAPH_NODE_END,
            run_id="r1",
            payload={"node_id": "a", "status": "succeeded"},
        ),
    ]
    assert active_node_from_events(events, run_id="r1") == "b"


def test_render_ascii_marks_active_node() -> None:
    view = view_from_checkpoint(
        {
            "goal": "demo",
            "nodes": {
                "n0": {"kind": "june.task", "status": "succeeded"},
                "n1": {"kind": "june.task", "status": "running"},
            },
            "edges": [{"from_node": "n0", "to_node": "n1", "types": ["control"], "reason": "x"}],
        },
        run_id="r1",
        active_node_id="n1",
    )
    text = render_ascii(view)
    assert ">>" in text
    assert "n1" in text or "june.task" in text


def test_execution_focus_nested_run_id() -> None:
    root_cp = {
        "goal": "parent",
        "nodes": {
            "parent:0": {"kind": "subgraph", "status": "running"},
        },
        "edges": [],
    }
    child_cp = {
        "goal": "child",
        "nodes": {
            "child:0": {"kind": "june.task", "status": "running"},
        },
        "edges": [],
    }
    events = [
        _FakeEvent(
            type="core:graph_node",
            run_id="parent-run",
            payload={"graph": root_cp},
        ),
        _FakeEvent(
            type=GRAPH_NODE_START,
            run_id="parent-run",
            payload={"node_id": "parent:0", "subgraph": True},
        ),
        _FakeEvent(
            type="core:graph_node",
            run_id="parent-run:parent:0",
            payload={"graph": child_cp},
        ),
        _FakeEvent(
            type=GRAPH_NODE_START,
            run_id="parent-run:parent:0",
            payload={"node_id": "child:0"},
        ),
    ]
    focus = execution_focus_from_events(events, root_run_id="parent-run", root_checkpoint=root_cp)
    assert focus.active_run_id == "parent-run:parent:0"
    assert focus.nested is not None
    assert focus.root.active_node_id == "parent:0"


def test_client_execute_run_populates_focus() -> None:
    client = MechaHarnessClient()
    if not client.connect():
        return
    run = client.bind_template("viz", node_kinds=["june.task", "june.task"])
    result = client.execute(run, driver="run")
    assert result.status == "ok"
    focus = client.execution_focus(run, checkpoint=result.graph_checkpoint)
    assert focus is not None
    assert len(focus.root.nodes) == 2
    assert result.raw.get("execution_focus")
