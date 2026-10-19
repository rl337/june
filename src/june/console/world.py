"""Hierarchical world model for continuous zoom graph rendering.

Builds nested nodes with natural size estimates from a MechaHarness checkpoint
so the client can pan/zoom and reveal interiors when a node is large enough.

Bubble Trouble graph viz: multi-locus frontier, role vocabulary, pre-baked
Sugiyama layered DAG layout (see ``layered_dag``), inspect fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from june.console.layered_dag import (
    DEFAULT_NODE_GAP,
    DEFAULT_RANK_GAP,
    layout_layered_dag,
    topo_order,
)
from june.console.scene import recent_node_ids
from june.harness.visualization import active_node_from_events

# Base leaf dimensions (world units ≈ CSS px at zoom=1).
LEAF_W = 160.0
LEAF_H = 56.0
BEAD_W = 132.0
BEAD_H = 44.0
PAD_X = 32.0
PAD_Y = 40.0
GAP = 22.0
CELL_GAP_X = 28.0
CELL_GAP_Y = 28.0
HEADER_H = 30.0
BG_CHIP_W = 120.0
BG_CHIP_H = 38.0
INSTANCE_GAP = 28.0
STACK_VISIBLE = 2
STACK_OVERLAP = 1.0 / 3.0  # back card shows 1/3; front covers 2/3
STACK_BADGE_W = 72.0
STACK_BADGE_H = 72.0
# Main-graph stack cards stay compact; full pipeline layout belongs in the
# instance watch dialog (build_instance_world). Deep chat/tool nests must not
# inflate the structure overview / camera fit.
STACK_CARD_W = 200.0
STACK_CARD_H = 112.0
MAX_PER_ROW = 3
RANK_GAP = DEFAULT_RANK_GAP
RANK_NODE_GAP = DEFAULT_NODE_GAP

WorldRole = Literal["chamber", "door", "bead", "dive", "plaque", "badge"]
ExecutionVisual = Literal[
    "running", "occupied", "recent", "dim", "pending", "failed"
]

_CHAMBER_KINDS = frozenset(
    {
        "conversational_tool_loop",
        "harness_loop",
        "subgraph",
        "tools",
        "june.cron.bucket",
        "june.cron",
        "june.chat",
    }
)
_BEAD_KINDS = frozenset(
    {
        "turn_start",
        "inference",
        "tool_call",
        "tool_result",
        "stop_contract",
        "max_turns",
        "cost",
        "access_check",
        "extension_applied",
        "effect_state",
        "budget_level",
    }
)
_PLAQUE_KINDS = frozenset({"soft_point", "context", "june.soft"})
_SOFT_KIND_PREFIXES = ("soft.", "june.soft.")


@dataclass
class WorldNode:
    id: str
    label: str
    kind: str
    shape: str
    status: str
    execution: str
    role: str = "door"
    detail: str = ""
    tool_name: str | None = None
    child_run_id: str | None = None
    bindings: dict[str, Any] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0
    w: float = LEAF_W
    h: float = LEAF_H
    children: list[WorldNode] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)
    stack_role: str | None = None  # front | back | badge | None
    stack_depth: int = 0
    stack_hidden: list[str] = field(default_factory=list)
    stack_parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "shape": self.shape,
            "status": self.status,
            "execution": self.execution,
            "role": self.role,
            "detail": self.detail,
            "tool_name": self.tool_name,
            "child_run_id": self.child_run_id,
            "bindings": dict(self.bindings),
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "children": [c.to_dict() for c in self.children],
            "edges": self.edges,
            "stack_role": self.stack_role,
            "stack_depth": self.stack_depth,
            "stack_hidden": list(self.stack_hidden),
            "stack_parent_id": self.stack_parent_id,
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
    running_node_ids: list[str] = field(default_factory=list)
    failed_node_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_id": self.root_id,
            "goal": self.goal,
            "width": self.width,
            "height": self.height,
            "active_node_id": self.active_node_id,
            "running_node_ids": list(self.running_node_ids),
            "failed_node_ids": list(self.failed_node_ids),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": self.edges,
        }


def _payload_of(raw: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("payload")
    return dict(payload) if isinstance(payload, dict) else {}


def _tool_name_of(kind: str, payload: dict[str, Any], node_id: str) -> str | None:
    for key in ("tool_name", "name", "tool"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    if kind.startswith("tool_call:") or kind.startswith("tool_result:"):
        return kind.split(":", 1)[1] or None
    if ":tool_call:" in node_id:
        return node_id.rsplit(":", 1)[-1] or None
    return None


def _child_run_id_of(raw: dict[str, Any], payload: dict[str, Any]) -> str | None:
    for source in (raw, payload):
        val = source.get("child_run_id")
        if isinstance(val, str) and val:
            return val
    return None


def _bindings_of(payload: dict[str, Any]) -> dict[str, Any]:
    bindings = payload.get("bindings")
    if isinstance(bindings, dict):
        return {str(k): bindings[k] for k in list(bindings)[:24]}
    return {}


def node_role(
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    has_children: bool = False,
    repeating: bool = False,
    child_run_id: str | None = None,
) -> WorldRole:
    """Map MH kind/payload to Bubble Trouble glyph role."""
    payload = payload or {}
    if kind == "stack_badge":
        return "badge"
    if (
        payload.get("recipe_as_tool")
        or child_run_id
        or (kind == "tool_call" and has_children)
        or kind == "child_graph"
    ):
        return "dive"
    if (
        has_children
        or repeating
        or kind in _CHAMBER_KINDS
        or kind.endswith("_loop")
        or "bucket" in kind
    ):
        return "chamber"
    if kind in _BEAD_KINDS or kind.startswith("tool_call") or kind.startswith("tool_result"):
        return "bead"
    if kind in _PLAQUE_KINDS or any(kind.startswith(p) for p in _SOFT_KIND_PREFIXES):
        return "plaque"
    if payload.get("soft_point") or payload.get("firmness") == "soft":
        return "plaque"
    return "door"


def node_shape_for_role(role: str) -> str:
    if role in {"chamber", "dive", "bead", "plaque", "badge"}:
        return "round_rect"
    return "rect"


def _execution(
    node_id: str,
    status: str,
    *,
    running_ids: set[str],
    recent_ids: set[str],
    failed_ids: set[str],
) -> ExecutionVisual:
    if status == "running" or node_id in running_ids:
        return "running"
    if status in {"failed", "cancelled"} or node_id in failed_ids:
        return "failed"
    if node_id in recent_ids:
        return "recent"
    if status in {"succeeded", "ok"}:
        return "dim"
    return "pending"


def _collect_status_ids(checkpoint: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Walk checkpoint tree for running and failed node ids (multi-locus)."""
    running: set[str] = set()
    failed: set[str] = set()

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, dict):
            return
        for node_id, raw in nodes.items():
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status", "pending"))
            nid = str(node_id)
            if status == "running":
                running.add(nid)
            elif status in {"failed", "cancelled"}:
                failed.add(nid)
            subgraph = raw.get("subgraph")
            if isinstance(subgraph, dict):
                walk(subgraph.get("nodes"))
            payload = raw.get("payload")
            if isinstance(payload, dict):
                nested = payload.get("subgraph")
                if isinstance(nested, dict):
                    walk(nested.get("nodes"))

    walk(checkpoint.get("nodes"))
    return running, failed


def _layout_column(
    children: list[WorldNode], *, origin_x: float, origin_y: float
) -> tuple[float, float]:
    """Stack children top-to-bottom (cleaner for sequential pipelines)."""
    if not children:
        return 0.0, 0.0
    y = origin_y
    max_w = 0.0
    for child in children:
        child.x = origin_x
        child.y = y
        y += child.h + GAP
        max_w = max(max_w, child.w)
    for child in children:
        child.x = origin_x + (max_w - child.w) / 2
    total_h = sum(c.h for c in children) + GAP * (len(children) - 1)
    return max_w, total_h


def _layout_row(
    children: list[WorldNode], *, origin_x: float, origin_y: float
) -> tuple[float, float]:
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


def _layout_serpentine(
    children: list[WorldNode],
    *,
    origin_x: float,
    origin_y: float,
    per_row: int = MAX_PER_ROW,
) -> tuple[float, float]:
    """Pack chamber interiors ~3/row; even rows L→R, odd rows R→L (MH-inspired)."""
    if not children:
        return 0.0, 0.0
    if len(children) <= 2:
        return _layout_column(children, origin_x=origin_x, origin_y=origin_y)

    rows: list[list[WorldNode]] = [
        children[i : i + per_row] for i in range(0, len(children), per_row)
    ]
    row_widths: list[float] = []
    row_heights: list[float] = []
    for row in rows:
        row_widths.append(sum(c.w for c in row) + CELL_GAP_X * max(0, len(row) - 1))
        row_heights.append(max(c.h for c in row))
    content_w = max(row_widths) if row_widths else 0.0
    y = origin_y
    for ri, row in enumerate(rows):
        rtl = ri % 2 == 1
        rw = row_widths[ri]
        rh = row_heights[ri]
        if rtl:
            x = origin_x + content_w
            for child in row:
                x -= child.w
                child.x = x
                child.y = y + (rh - child.h) / 2
                x -= CELL_GAP_X
        else:
            # First row right-aligns when multiple rows (room for C-wrap feel).
            x = origin_x + (content_w - rw if ri == 0 and len(rows) > 1 else 0.0)
            for child in row:
                child.x = x
                child.y = y + (rh - child.h) / 2
                x += child.w + CELL_GAP_X
        y += rh + CELL_GAP_Y
    total_h = sum(row_heights) + CELL_GAP_Y * max(0, len(row_heights) - 1)
    return content_w, total_h


def _topo_order(ids: list[str], edges: list[dict[str, str]]) -> list[str]:
    pairs = [(e["from"], e["to"]) for e in edges if "from" in e and "to" in e]
    return topo_order(ids, pairs)


def _layout_layered(
    nodes: list[WorldNode],
    edges: list[dict[str, str]],
    *,
    origin_x: float,
    origin_y: float,
    rank_gap: float = RANK_GAP,
    node_gap: float = RANK_NODE_GAP,
    direction: Literal["lr", "tb"] = "lr",
) -> tuple[float, float]:
    """Pre-bake Sugiyama layered DAG coordinates onto ``nodes``."""
    return layout_layered_dag(
        nodes,
        edges,
        origin_x=origin_x,
        origin_y=origin_y,
        rank_gap=rank_gap,
        node_gap=node_gap,
        direction=direction,
    )


def _extract_edges(raw_edges: Any) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    if not isinstance(raw_edges, list):
        return edges
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        src, dst = edge.get("from_node"), edge.get("to_node")
        if isinstance(src, str) and isinstance(dst, str):
            label = edge.get("reason") or ""
            if not label and isinstance(edge.get("types"), list):
                label = ",".join(str(t) for t in edge["types"])
            item: dict[str, str] = {"from": src, "to": dst}
            if isinstance(label, str) and label:
                item["label"] = label
            edges.append(item)
    return edges


def _build_from_subgraph(
    subgraph: dict[str, Any],
    *,
    running_ids: set[str],
    recent_ids: set[str],
    failed_ids: set[str],
    layout: Literal["auto", "column", "row", "serpentine", "layered"] = "auto",
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
                running_ids=running_ids,
                recent_ids=recent_ids,
                failed_ids=failed_ids,
            )
        )
    edges = _extract_edges(subgraph.get("edges"))
    if edges:
        order = _topo_order([c.id for c in children], edges)
        by_id = {c.id: c for c in children}
        children = [by_id[i] for i in order if i in by_id]
    else:
        children.sort(key=lambda n: n.id)

    origin_x = PAD_X
    origin_y = HEADER_H + PAD_Y / 2
    # Prefer layered DAG whenever dependency edges exist (pre-baked Sugiyama).
    use = layout
    if use == "auto":
        use = "layered" if edges else "column"

    if use == "layered" and edges:
        content_w, content_h = _layout_layered(
            children,
            edges,
            origin_x=origin_x,
            origin_y=origin_y,
            direction="tb",  # interiors read top→bottom like a recipe column
        )
    elif use == "serpentine":
        content_w, content_h = _layout_serpentine(
            children, origin_x=origin_x, origin_y=origin_y
        )
    elif use == "row":
        content_w, content_h = _layout_row(
            children, origin_x=origin_x, origin_y=origin_y
        )
    elif use == "layered":
        content_w, content_h = _layout_layered(
            children, edges, origin_x=origin_x, origin_y=origin_y, direction="lr"
        )
    else:
        content_w, content_h = _layout_column(
            children, origin_x=origin_x, origin_y=origin_y
        )
    width = max(LEAF_W, content_w + PAD_X * 2)
    height = max(LEAF_H, content_h + HEADER_H + PAD_Y)
    return children, edges, width, height


def _interior_layout(
    kind: str, child_count: int, *, has_edges: bool
) -> Literal["auto", "column", "serpentine", "layered"]:
    if has_edges:
        return "layered"
    if child_count >= 3 and (
        kind in _CHAMBER_KINDS
        or kind.endswith("_loop")
        or kind in {"tool_call", "subgraph"}
    ):
        return "serpentine"
    return "column"


def _build_node(
    node_id: str,
    raw: dict[str, Any],
    *,
    running_ids: set[str],
    recent_ids: set[str],
    failed_ids: set[str],
) -> WorldNode:
    kind = str(raw.get("kind", "node"))
    status = str(raw.get("status", "pending"))
    goal = str(raw.get("goal", ""))
    payload = _payload_of(raw)
    repeating = bool(raw.get("repeating") or raw.get("stop_contract"))
    tool_name = _tool_name_of(kind, payload, node_id)
    child_run_id = _child_run_id_of(raw, payload)
    bindings = _bindings_of(payload)

    children: list[WorldNode] = []
    edges: list[dict[str, str]] = []
    width, height = LEAF_W, LEAF_H

    subgraph = raw.get("subgraph") or payload.get("subgraph")
    has_subgraph = isinstance(subgraph, dict) and bool(subgraph.get("nodes"))
    if has_subgraph:
        sub_edges = _extract_edges(subgraph.get("edges"))
        layout = _interior_layout(
            kind,
            len(subgraph.get("nodes") or {}),
            has_edges=bool(sub_edges),
        )
        children, edges, width, height = _build_from_subgraph(
            subgraph,
            running_ids=running_ids,
            recent_ids=recent_ids,
            failed_ids=failed_ids,
            layout=layout,
        )

    role = node_role(
        kind,
        payload,
        has_children=bool(children),
        repeating=repeating,
        child_run_id=child_run_id,
    )
    shape = node_shape_for_role(role)
    if role == "bead" and not children:
        width, height = BEAD_W, BEAD_H

    if tool_name and kind in {"tool_call", "tool_result"}:
        label = f"{kind.split(':', 1)[0]}:{tool_name}"
    else:
        label = goal or kind

    execution = _execution(
        node_id,
        status,
        running_ids=running_ids,
        recent_ids=recent_ids,
        failed_ids=failed_ids,
    )
    return WorldNode(
        id=node_id,
        label=label,
        kind=kind,
        shape=shape,
        status=status,
        execution=execution,
        role=role,
        detail=goal,
        tool_name=tool_name,
        child_run_id=child_run_id,
        bindings=bindings,
        w=width,
        h=height,
        children=children,
        edges=edges,
    )


def build_instance_world(inst: dict[str, Any]) -> WorldGraph:
    """Layout a single stacked instance as its own zoomable world (watch dialog)."""
    run_id = str(inst.get("run_id") or "instance")
    pipeline = inst.get("pipeline") if isinstance(inst.get("pipeline"), dict) else {}
    running_ids, failed_ids = _collect_status_ids(pipeline)
    active = inst.get("active_node_id") if isinstance(inst.get("active_node_id"), str) else None
    if active:
        running_ids.add(active)
    if str(inst.get("status")) == "running":
        running_ids.add(run_id)
    node = _instance_node(
        inst,
        running_ids=running_ids,
        recent_ids=set(),
        failed_ids=failed_ids,
    )
    _propagate_frontier(node)
    node.x = PAD_X
    node.y = PAD_Y
    return WorldGraph(
        root_id=run_id,
        goal=node.label,
        width=node.w + PAD_X * 2,
        height=node.h + PAD_Y * 2,
        nodes=[node],
        edges=[],
        active_node_id=active,
        running_node_ids=sorted(running_ids),
        failed_node_ids=sorted(failed_ids),
    )


def _instance_execution(
    inst: dict[str, Any], *, running_ids: set[str]
) -> ExecutionVisual:
    run_id = str(inst.get("run_id") or "")
    status = str(inst.get("status", "running"))
    if status == "running" or run_id in running_ids:
        return "running"
    if status in {"failed", "cancelled"}:
        return "failed"
    return "dim"


def _instance_node(
    inst: dict[str, Any],
    *,
    running_ids: set[str],
    recent_ids: set[str],
    failed_ids: set[str],
) -> WorldNode:
    """Full recursive pipeline layout — used by the instance watch dialog."""
    run_id = str(inst.get("run_id"))
    status = str(inst.get("status", "running"))
    pipeline = inst.get("pipeline") if isinstance(inst.get("pipeline"), dict) else {}
    short = run_id[-8:]
    label = f"run {short}"
    child_count = len(pipeline.get("nodes") or {})
    layout = _interior_layout(
        "subgraph",
        child_count,
        has_edges=bool(_extract_edges(pipeline.get("edges"))),
    )
    children, edges, width, height = _build_from_subgraph(
        pipeline,
        running_ids=running_ids,
        recent_ids=recent_ids,
        failed_ids=failed_ids,
        layout=layout,
    )
    return WorldNode(
        id=run_id,
        label=label,
        kind="subgraph",
        shape="round_rect",
        status=status,
        execution=_instance_execution(inst, running_ids=running_ids),
        role="chamber",
        detail=str(inst.get("bucket", "")),
        w=width,
        h=height,
        children=children,
        edges=edges,
    )


def _instance_stack_card(
    inst: dict[str, Any],
    *,
    running_ids: set[str],
) -> WorldNode:
    """Compact stack face for the structure overview (no nested pipeline size)."""
    run_id = str(inst.get("run_id"))
    status = str(inst.get("status", "running"))
    short = run_id[-8:]
    pipeline = inst.get("pipeline") if isinstance(inst.get("pipeline"), dict) else {}
    step_count = len(pipeline.get("nodes") or {})
    active = inst.get("active_node_id")
    detail_bits = [str(inst.get("bucket", "") or "run")]
    if step_count:
        detail_bits.append(f"{step_count} steps")
    if isinstance(active, str) and active:
        detail_bits.append(active.split(":")[-1][:24])
    return WorldNode(
        id=run_id,
        label=f"run {short}",
        kind="subgraph",
        shape="round_rect",
        status=status,
        execution=_instance_execution(inst, running_ids=running_ids),
        role="chamber",
        detail=" · ".join(detail_bits),
        w=STACK_CARD_W,
        h=STACK_CARD_H,
        children=[],
        edges=[],
    )


def _attach_instances(
    tops: list[WorldNode],
    instances: list[dict[str, Any]],
    *,
    running_ids: set[str],
    recent_ids: set[str],
    failed_ids: set[str],
) -> None:
    """Place live instances as an overlapping stack under each parent bucket."""
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for inst in instances:
        parent = str(inst.get("parent_node_id") or "")
        if not parent:
            continue
        by_parent.setdefault(parent, []).append(inst)

    for top in tops:
        group = by_parent.get(top.id)
        if not group:
            continue
        running = [i for i in group if i.get("status") == "running"]
        finished = [i for i in group if i.get("status") != "running"]
        running.sort(key=lambda i: str(i.get("started_at", "")), reverse=True)
        finished.sort(
            key=lambda i: str(i.get("finished_at") or i.get("started_at", "")),
            reverse=True,
        )
        ordered = running + finished

        visible = ordered[:STACK_VISIBLE]
        hidden = ordered[STACK_VISIBLE:]
        # Compact cards only — expanding full pipelines here made chat/tool
        # nests dominate the overview and zoom the camera into emptiness.
        visible_nodes = [
            _instance_stack_card(i, running_ids=running_ids) for i in visible
        ]
        for depth, node in enumerate(reversed(visible_nodes)):
            node.stack_depth = depth
            node.stack_role = "back" if depth == 0 and len(visible_nodes) > 1 else "front"
            node.stack_parent_id = top.id

        template = list(top.children)
        template_edges = list(top.edges)
        if template:
            content_w, content_h = _layout_column(
                template, origin_x=PAD_X, origin_y=HEADER_H + PAD_Y / 2
            )
        else:
            content_w, content_h = 0.0, 0.0

        stack_origin_x = PAD_X + (content_w + INSTANCE_GAP if template else 0.0)
        stack_origin_y = HEADER_H + PAD_Y / 2
        card_w = max((n.w for n in visible_nodes), default=LEAF_W)
        card_h = max((n.h for n in visible_nodes), default=LEAF_H)
        peek = card_w * STACK_OVERLAP
        for i, node in enumerate(reversed(visible_nodes)):
            node.w = card_w
            node.h = card_h
            node.x = stack_origin_x + i * peek
            node.y = stack_origin_y + i * 10
            node.stack_depth = i

        stack_w = card_w + peek * max(0, len(visible_nodes) - 1)
        stack_h = card_h + 10 * max(0, len(visible_nodes) - 1)

        extras: list[WorldNode] = []
        if hidden:
            hidden_running = any(i.get("status") == "running" for i in hidden)
            badge = WorldNode(
                id=f"{top.id}:stack-badge",
                label=f"+{len(hidden)}",
                kind="stack_badge",
                shape="round_rect",
                status="running" if hidden_running else "pending",
                execution="running" if hidden_running else "pending",
                role="badge",
                detail="click for instance list",
                x=stack_origin_x + stack_w + 12,
                y=stack_origin_y + (stack_h - STACK_BADGE_H) / 2,
                w=STACK_BADGE_W,
                h=STACK_BADGE_H,
                stack_role="badge",
                stack_depth=10_000,
                stack_hidden=[str(i.get("run_id")) for i in ordered],
                stack_parent_id=top.id,
            )
            extras.append(badge)
            stack_w += 12 + STACK_BADGE_W

        stacked = list(reversed(visible_nodes))
        top.children = template + stacked + extras
        top.edges = template_edges
        top.w = max(
            LEAF_W,
            PAD_X * 2
            + content_w
            + (INSTANCE_GAP if template and (visible_nodes or extras) else 0)
            + stack_w,
        )
        top.h = max(LEAF_H, HEADER_H + PAD_Y + max(content_h, stack_h))
        if any(i.get("status") == "running" for i in ordered):
            top.status = "running"
            top.execution = "running"
        elif ordered:
            top.execution = "recent"
            if top.status in {"pending", "succeeded", "dim", ""}:
                top.status = str(ordered[0].get("status") or top.status or "succeeded")


def _propagate_frontier(node: WorldNode) -> bool:
    """Mark ancestors occupied when any descendant is running (multi-locus).

    Finished stack instance cards are not re-lit from stale nested statuses.
    True runners keep ``running``; containers get ``occupied`` so zoomed-out
    views still show where work lives without pretending the parent itself runs.
    """
    self_running = node.execution == "running" or node.status == "running"
    if node.stack_role in {"front", "back"}:
        return self_running

    child_running = False
    for child in node.children:
        if _propagate_frontier(child):
            child_running = True
    if child_running and not self_running:
        if node.execution not in {"running", "failed"}:
            node.execution = "occupied"
        if node.status in {"pending", "succeeded", "dim", ""}:
            node.status = "running"
    return self_running or child_running


def build_world_graph(
    checkpoint: dict[str, Any],
    events: list[Any],
    *,
    run_id: str,
    instances: list[dict[str, Any]] | None = None,
) -> WorldGraph:
    """Layout the full checkpoint hierarchy for continuous zoom rendering."""
    running_ids, failed_ids = _collect_status_ids(checkpoint)
    active = active_node_from_events(events, run_id=run_id)
    if active:
        running_ids.add(active)
    for inst in instances or []:
        if inst.get("status") == "running":
            rid = inst.get("run_id")
            if isinstance(rid, str):
                running_ids.add(rid)
            nested_active = inst.get("active_node_id")
            if isinstance(nested_active, str):
                running_ids.add(nested_active)
            pipeline = inst.get("pipeline")
            if isinstance(pipeline, dict):
                nest_run, nest_fail = _collect_status_ids(pipeline)
                running_ids |= nest_run
                failed_ids |= nest_fail
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
            running_node_ids=sorted(running_ids),
            failed_node_ids=sorted(failed_ids),
        )

    tops: list[WorldNode] = []
    for node_id, raw in raw_nodes.items():
        if not isinstance(raw, dict):
            continue
        tops.append(
            _build_node(
                str(node_id),
                raw,
                running_ids=running_ids,
                recent_ids=recent,
                failed_ids=failed_ids,
            )
        )

    edges = _extract_edges(checkpoint.get("edges"))
    if edges:
        order = _topo_order([n.id for n in tops], edges)
        by_id = {n.id: n for n in tops}
        tops = [by_id[i] for i in order if i in by_id]
    else:
        tops.sort(key=lambda n: n.id)

    _attach_instances(
        tops,
        instances or [],
        running_ids=running_ids,
        recent_ids=recent,
        failed_ids=failed_ids,
    )
    for top in tops:
        _propagate_frontier(top)

    # Layered left→right ranks keep fan-out edges in a clear channel instead of
    # drawing diagonals across sibling chambers.
    content_w, content_h = _layout_layered(
        tops, edges, origin_x=PAD_X, origin_y=PAD_Y
    )
    world_w = content_w + PAD_X * 2
    world_h = content_h + PAD_Y * 2

    return WorldGraph(
        root_id=run_id,
        goal=str(checkpoint.get("goal") or "graph"),
        width=world_w,
        height=world_h,
        nodes=tops,
        edges=edges,
        active_node_id=active,
        running_node_ids=sorted(running_ids),
        failed_node_ids=sorted(failed_ids),
    )
