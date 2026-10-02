"""Layered scene model for the June web console (scene / foreground / background)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from june.harness.visualization import (
    GRAPH_NODE_END,
    GRAPH_NODE_START,
    active_node_from_events,
    execution_focus_from_events,
    view_from_checkpoint,
)

Layer = Literal["foreground", "background"]
Shape = Literal["rect", "round_rect"]
ExecutionVisual = Literal["running", "recent", "dim", "pending"]
ROOT_SCENE_ID = "__root__"

_SOFT_KINDS = frozenset({"subgraph", "soft_point", "context", "june.soft"})
_SOFT_KIND_PREFIXES = ("soft.", "june.soft.")


@dataclass(frozen=True)
class SceneNode:
    id: str
    label: str
    kind: str
    shape: Shape
    layer: Layer
    execution: ExecutionVisual
    status: str = "pending"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "shape": self.shape,
            "layer": self.layer,
            "execution": self.execution,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class SceneFrame:
    """One console frame: selected scene plus foreground/background layers."""

    run_id: str
    scene_node_id: str
    scene_title: str
    scene_kind: str
    active_node_id: str | None
    nodes: list[SceneNode] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scene_node_id": self.scene_node_id,
            "scene_title": self.scene_title,
            "scene_kind": self.scene_kind,
            "active_node_id": self.active_node_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": self.edges,
        }


def node_shape(kind: str, payload: dict[str, Any] | None = None) -> Shape:
    payload = payload or {}
    firmness = payload.get("firmness")
    if firmness == "soft" or payload.get("soft_point"):
        return "round_rect"
    if firmness == "hard":
        return "rect"
    if kind in _SOFT_KINDS:
        return "round_rect"
    if any(kind.startswith(prefix) for prefix in _SOFT_KIND_PREFIXES):
        return "round_rect"
    if kind == "subgraph":
        return "round_rect"
    return "rect"


def _execution_visual(
    node_id: str,
    status: str,
    *,
    active_node_id: str | None,
    recent_ids: set[str],
) -> ExecutionVisual:
    if active_node_id == node_id or status == "running":
        return "running"
    if node_id in recent_ids:
        return "recent"
    if status in {"succeeded", "failed", "cancelled"}:
        return "dim"
    return "pending"


def recent_node_ids(events: list[Any], *, limit: int = 8) -> set[str]:
    """Nodes that finished recently (dim highlight trail)."""
    ended: list[str] = []
    for event in events:
        etype = str(getattr(event, "type", ""))
        if etype != GRAPH_NODE_END:
            continue
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict):
            continue
        node_id = payload.get("node_id")
        if isinstance(node_id, str):
            ended.append(node_id)
    return set(ended[-limit:])


def _raw_node(checkpoint: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    nodes = checkpoint.get("nodes")
    if not isinstance(nodes, dict):
        return None
    raw = nodes.get(node_id)
    return raw if isinstance(raw, dict) else None


def _payload_of(raw: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("payload")
    return dict(payload) if isinstance(payload, dict) else dict(raw)


def _background_nodes(
    raw: dict[str, Any],
    *,
    active_node_id: str | None,
    recent_ids: set[str],
    prefix: str,
) -> list[SceneNode]:
    payload = _payload_of(raw)
    items: list[SceneNode] = []
    refs = payload.get("context_refs")
    if isinstance(refs, list):
        for idx, ref in enumerate(refs):
            if not isinstance(ref, dict):
                continue
            title = str(ref.get("title") or ref.get("id") or f"context-{idx}")
            node_id = f"{prefix}:ctx:{idx}"
            items.append(
                SceneNode(
                    id=node_id,
                    label=title,
                    kind="context",
                    shape="round_rect",
                    layer="background",
                    execution=_execution_visual(
                        node_id,
                        "pending",
                        active_node_id=active_node_id,
                        recent_ids=recent_ids,
                    ),
                    status="materialized",
                    detail=str(ref.get("summary") or ref.get("kind") or ""),
                )
            )
    bindings = payload.get("bindings")
    if isinstance(bindings, dict):
        for key in sorted(bindings):
            node_id = f"{prefix}:bind:{key}"
            items.append(
                SceneNode(
                    id=node_id,
                    label=str(key),
                    kind="soft_point",
                    shape="round_rect",
                    layer="background",
                    execution="pending",
                    status="bound",
                    detail=str(bindings[key])[:120],
                )
            )
    guidance = payload.get("advisor_guidance")
    if guidance:
        node_id = f"{prefix}:advisor"
        items.append(
            SceneNode(
                id=node_id,
                label="advisor",
                kind="soft_point",
                shape="round_rect",
                layer="background",
                execution="pending",
                status="advisory",
                detail=str(guidance)[:160],
            )
        )
    return items


def _foreground_from_subgraph(
    subgraph: dict[str, Any],
    *,
    run_id: str,
    active_node_id: str | None,
    recent_ids: set[str],
) -> tuple[list[SceneNode], list[dict[str, str]]]:
    view = view_from_checkpoint(subgraph, run_id=run_id, active_node_id=active_node_id)
    nodes: list[SceneNode] = []
    for item in view.nodes:
        raw = (subgraph.get("nodes") or {}).get(item.id, {})
        payload = raw if isinstance(raw, dict) else {}
        nodes.append(
            SceneNode(
                id=item.id,
                label=item.label or item.kind,
                kind=item.kind,
                shape=node_shape(item.kind, _payload_of(payload) if payload else None),
                layer="foreground",
                execution=_execution_visual(
                    item.id,
                    item.status,
                    active_node_id=active_node_id,
                    recent_ids=recent_ids,
                ),
                status=item.status,
                detail=item.goal,
            )
        )
    edges = [{"from": a, "to": b} for a, b in view.edges]
    return nodes, edges


def build_scene_frame(
    checkpoint: dict[str, Any],
    events: list[Any],
    *,
    run_id: str,
    selected_node_id: str | None = None,
) -> SceneFrame:
    """Compose scene / foreground / background for the web console."""
    focus = execution_focus_from_events(events, root_run_id=run_id, root_checkpoint=checkpoint)
    active_node_id = focus.active_node_id
    if active_node_id is None:
        active_node_id = active_node_from_events(events, run_id=run_id)
    recent_ids = recent_node_ids(events)

    scene_node_id = selected_node_id or active_node_id or ROOT_SCENE_ID
    nodes: list[SceneNode] = []
    edges: list[dict[str, str]] = []

    if scene_node_id == ROOT_SCENE_ID:
        root_view = view_from_checkpoint(
            checkpoint,
            run_id=run_id,
            active_node_id=active_node_id,
        )
        scene_title = str(checkpoint.get("goal") or "execution graph")
        scene_kind = "graph"
        for item in root_view.nodes:
            raw = _raw_node(checkpoint, item.id) or {}
            nodes.append(
                SceneNode(
                    id=item.id,
                    label=item.label or item.kind,
                    kind=item.kind,
                    shape=node_shape(item.kind, _payload_of(raw)),
                    layer="foreground",
                    execution=_execution_visual(
                        item.id,
                        item.status,
                        active_node_id=active_node_id,
                        recent_ids=recent_ids,
                    ),
                    status=item.status,
                    detail=item.goal,
                )
            )
        edges = [{"from": a, "to": b} for a, b in root_view.edges]
        if active_node_id:
            active_raw = _raw_node(checkpoint, active_node_id)
            if active_raw is not None:
                nodes.extend(
                    _background_nodes(
                        active_raw,
                        active_node_id=active_node_id,
                        recent_ids=recent_ids,
                        prefix=active_node_id,
                    )
                )
        return SceneFrame(
            run_id=run_id,
            scene_node_id=ROOT_SCENE_ID,
            scene_title=scene_title,
            scene_kind=scene_kind,
            active_node_id=active_node_id,
            nodes=nodes,
            edges=edges,
        )

    raw = _raw_node(checkpoint, scene_node_id)
    if raw is None:
        return SceneFrame(
            run_id=run_id,
            scene_node_id=scene_node_id,
            scene_title="unknown node",
            scene_kind="unknown",
            active_node_id=active_node_id,
            nodes=[],
            edges=[],
        )

    scene_title = str(raw.get("goal") or raw.get("kind") or scene_node_id)
    scene_kind = str(raw.get("kind", "node"))
    payload = _payload_of(raw)

    subgraph = raw.get("subgraph") or payload.get("subgraph")
    if isinstance(subgraph, dict):
        fg, fg_edges = _foreground_from_subgraph(
            subgraph,
            run_id=run_id,
            active_node_id=active_node_id,
            recent_ids=recent_ids,
        )
        nodes.extend(fg)
        edges.extend(fg_edges)
    else:
        nodes.append(
            SceneNode(
                id=scene_node_id,
                label=scene_title,
                kind=scene_kind,
                shape=node_shape(scene_kind, payload),
                layer="foreground",
                execution=_execution_visual(
                    scene_node_id,
                    str(raw.get("status", "pending")),
                    active_node_id=active_node_id,
                    recent_ids=recent_ids,
                ),
                status=str(raw.get("status", "pending")),
                detail=scene_title,
            )
        )
        if focus.nested is not None and focus.root.active_node_id == scene_node_id:
            for item in focus.nested.nodes:
                nodes.append(
                    SceneNode(
                        id=item.id,
                        label=item.label or item.kind,
                        kind=item.kind,
                        shape=node_shape(item.kind, None),
                        layer="foreground",
                        execution=_execution_visual(
                            item.id,
                            item.status,
                            active_node_id=active_node_id,
                            recent_ids=recent_ids,
                        ),
                        status=item.status,
                        detail=item.goal,
                    )
                )
            edges.extend({"from": a, "to": b} for a, b in focus.nested.edges)

    nodes.extend(
        _background_nodes(
            raw,
            active_node_id=active_node_id,
            recent_ids=recent_ids,
            prefix=scene_node_id,
        )
    )

    return SceneFrame(
        run_id=run_id,
        scene_node_id=scene_node_id,
        scene_title=scene_title,
        scene_kind=scene_kind,
        active_node_id=active_node_id,
        nodes=nodes,
        edges=edges,
    )
