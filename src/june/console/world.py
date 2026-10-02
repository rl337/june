"""Hierarchical world model for continuous zoom graph rendering.

Builds nested nodes with natural size estimates from a MechaHarness checkpoint
so the client can pan/zoom and reveal interiors when a node is large enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from june.console.scene import node_shape, recent_node_ids
from june.harness.visualization import active_node_from_events

# Base leaf dimensions (world units ≈ CSS px at zoom=1).
LEAF_W = 148.0
LEAF_H = 52.0
PAD_X = 28.0
PAD_Y = 36.0
GAP = 18.0
HEADER_H = 28.0
BG_CHIP_W = 110.0
BG_CHIP_H = 36.0


@dataclass
class WorldNode:
    id: str
    label: str
    kind: str
    shape: str
    status: str
    execution: str
    detail: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = LEAF_W
    h: float = LEAF_H
    children: list[WorldNode] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "shape": self.shape,
            "status": self.status,
            "execution": self.execution,
            "detail": self.detail,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "children": [c.to_dict() for c in self.children],
            "edges": self.edges,
        }


@dataclass
class WorldGraph:
    root_id: str
    goal: str
    width: float
    height: float
    nodes: list[WorldNode]
    edges: list[dict[str, str]]
    active_node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_id": self.root_id,
            "goal": self.goal,
            "width": self.width,
            "height": self.height,
            "active_node_id": self.active_node_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": self.edges,
        }


def _payload_of(raw: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("payload")
    return dict(payload) if isinstance(payload, dict) else {}


def _execution(
    node_id: str,
    status: str,
    *,
    active_node_id: str | None,
    recent_ids: set[str],
) -> str:
    if active_node_id == node_id or status == "running":
        return "running"
    if node_id in recent_ids:
        return "recent"
    if status in {"succeeded", "failed", "cancelled"}:
        return "dim"
    return "pending"


def _background_children(raw: dict[str, Any], *, prefix: str) -> list[WorldNode]:
    payload = _payload_of(raw)
    items: list[WorldNode] = []
    refs = payload.get("context_refs")
    if isinstance(refs, list):
        for idx, ref in enumerate(refs):
            if not isinstance(ref, dict):
                continue
            title = str(ref.get("title") or ref.get("id") or f"context-{idx}")
            items.append(
                WorldNode(
                    id=f"{prefix}:ctx:{idx}",
                    label=title,
                    kind="context",
                    shape="round_rect",
                    status="materialized",
                    execution="pending",
                    detail=str(ref.get("summary") or ""),
                    w=BG_CHIP_W,
                    h=BG_CHIP_H,
                )
            )
    bindings = payload.get("bindings")
    if isinstance(bindings, dict):
        for key in sorted(bindings):
            items.append(
                WorldNode(
                    id=f"{prefix}:bind:{key}",
                    label=str(key),
                    kind="soft_point",
                    shape="round_rect",
                    status="bound",
                    execution="pending",
                    detail=str(bindings[key])[:80],
                    w=BG_CHIP_W,
                    h=BG_CHIP_H,
                )
            )
    return items


def _layout_row(children: list[WorldNode], *, origin_x: float, origin_y: float) -> tuple[float, float]:
    """Place children in a row; return (total_w, total_h)."""
    if not children:
        return 0.0, 0.0
    x = origin_x
    max_h = 0.0
    for child in children:
        child.x = x
        child.y = origin_y
        x += child.w + GAP
        max_h = max(max_h, child.h)
    total_w = sum(c.w for c in children) + GAP * (len(children) - 1)
    return total_w, max_h


def _build_from_subgraph(
    subgraph: dict[str, Any],
    *,
    active_node_id: str | None,
    recent_ids: set[str],
) -> tuple[list[WorldNode], list[dict[str, str]], float, float]:
    raw_nodes = subgraph.get("nodes") or {}
    if not isinstance(raw_nodes, dict):
        return [], [], LEAF_W, LEAF_H
    children: list[WorldNode] = []
    for node_id, raw in raw_nodes.items():
        if not isinstance(raw, dict):
            continue
        children.append(
            _build_node(
                str(node_id),
                raw,
                active_node_id=active_node_id,
                recent_ids=recent_ids,
            )
        )
    children.sort(key=lambda n: n.id)
    edges = []
    for edge in subgraph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        src, dst = edge.get("from_node"), edge.get("to_node")
        if isinstance(src, str) and isinstance(dst, str):
            edges.append({"from": src, "to": dst})

    # Prefer dependency order when edges exist.
    if edges:
        order = _topo_order([c.id for c in children], edges)
        by_id = {c.id: c for c in children}
        children = [by_id[i] for i in order if i in by_id]

    content_w, content_h = _layout_row(children, origin_x=PAD_X, origin_y=HEADER_H + PAD_Y / 2)
    width = max(LEAF_W, content_w + PAD_X * 2)
    height = max(LEAF_H, content_h + HEADER_H + PAD_Y)
    return children, edges, width, height


def _topo_order(ids: list[str], edges: list[dict[str, str]]) -> list[str]:
    indeg = {i: 0 for i in ids}
    outs: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        a, b = e["from"], e["to"]
        if a in indeg and b in indeg:
            outs[a].append(b)
            indeg[b] += 1
    queue = [i for i in ids if indeg[i] == 0]
    ordered: list[str] = []
    while queue:
        n = queue.pop(0)
        ordered.append(n)
        for nxt in outs[n]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    for i in ids:
        if i not in ordered:
            ordered.append(i)
    return ordered


def _build_node(
    node_id: str,
    raw: dict[str, Any],
    *,
    active_node_id: str | None,
    recent_ids: set[str],
) -> WorldNode:
    kind = str(raw.get("kind", "node"))
    status = str(raw.get("status", "pending"))
    goal = str(raw.get("goal", ""))
    payload = _payload_of(raw)
    short = node_id.split(":")[-1] if ":" in node_id else node_id
    label = f"{kind} ({short})" if not goal else goal
    shape = node_shape(kind, payload)
    execution = _execution(node_id, status, active_node_id=active_node_id, recent_ids=recent_ids)

    children: list[WorldNode] = []
    edges: list[dict[str, str]] = []
    width, height = LEAF_W, LEAF_H

    subgraph = raw.get("subgraph") or payload.get("subgraph")
    if isinstance(subgraph, dict) and subgraph.get("nodes"):
        children, edges, width, height = _build_from_subgraph(
            subgraph,
            active_node_id=active_node_id,
            recent_ids=recent_ids,
        )
    else:
        bg = _background_children(raw, prefix=node_id)
        if bg:
            children = bg
            content_w, content_h = _layout_row(bg, origin_x=PAD_X, origin_y=HEADER_H + PAD_Y / 2)
            width = max(LEAF_W, content_w + PAD_X * 2)
            height = max(LEAF_H * 1.4, content_h + HEADER_H + PAD_Y)

    return WorldNode(
        id=node_id,
        label=label,
        kind=kind,
        shape=shape,
        status=status,
        execution=execution,
        detail=goal,
        w=width,
        h=height,
        children=children,
        edges=edges,
    )


def build_world_graph(
    checkpoint: dict[str, Any],
    events: list[Any],
    *,
    run_id: str,
) -> WorldGraph:
    """Layout the full checkpoint hierarchy for continuous zoom rendering."""
    active = active_node_from_events(events, run_id=run_id)
    recent = recent_node_ids(events)
    raw_nodes = checkpoint.get("nodes") or {}
    if not isinstance(raw_nodes, dict) or not raw_nodes:
        return WorldGraph(
            root_id=run_id,
            goal=str(checkpoint.get("goal") or "empty"),
            width=400,
            height=240,
            nodes=[],
            edges=[],
            active_node_id=active,
        )

    tops: list[WorldNode] = []
    for node_id, raw in raw_nodes.items():
        if not isinstance(raw, dict):
            continue
        tops.append(
            _build_node(
                str(node_id),
                raw,
                active_node_id=active,
                recent_ids=recent,
            )
        )
    tops.sort(key=lambda n: n.id)

    edges: list[dict[str, str]] = []
    for edge in checkpoint.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        src, dst = edge.get("from_node"), edge.get("to_node")
        if isinstance(src, str) and isinstance(dst, str):
            edges.append({"from": src, "to": dst})

    if edges:
        order = _topo_order([n.id for n in tops], edges)
        by_id = {n.id: n for n in tops}
        tops = [by_id[i] for i in order if i in by_id]

    # Fan from left-to-right with vertical centering.
    total_w = sum(n.w for n in tops) + GAP * max(0, len(tops) - 1)
    max_h = max((n.h for n in tops), default=LEAF_H)
    world_w = total_w + PAD_X * 2
    world_h = max_h + PAD_Y * 2
    x = PAD_X
    for node in tops:
        node.x = x
        node.y = (world_h - node.h) / 2
        x += node.w + GAP

    return WorldGraph(
        root_id=run_id,
        goal=str(checkpoint.get("goal") or "graph"),
        width=world_w,
        height=world_h,
        nodes=tops,
        edges=edges,
        active_node_id=active,
    )
