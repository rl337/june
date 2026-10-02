"""Graph execution visualization from MechaHarness checkpoints and events.

MechaHarness emits ``core:graph_node_start`` / ``core:graph_node_end`` and
persists graph checkpoints on ``core:graph_node`` events. June turns those into
a host-facing snapshot that highlights the active node within the larger graph,
including nested subgraph runs (child run ids ``{parent_run_id}:{node_id}``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GRAPH_NODE_EVENT = "core:graph_node"
GRAPH_NODE_START = "core:graph_node_start"
GRAPH_NODE_END = "core:graph_node_end"


@dataclass(frozen=True)
class GraphNodeView:
    id: str
    kind: str
    status: str
    goal: str = ""
    label: str = ""


@dataclass
class GraphExecutionView:
    """One renderable graph with optional active-node highlight."""

    run_id: str
    goal: str
    nodes: list[GraphNodeView] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    active_node_id: str | None = None
    scope: Literal["root", "nested"] = "root"
    parent_node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "scope": self.scope,
            "parent_node_id": self.parent_node_id,
            "active_node_id": self.active_node_id,
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind,
                    "status": n.status,
                    "goal": n.goal,
                    "label": n.label,
                }
                for n in self.nodes
            ],
            "edges": [{"from": a, "to": b} for a, b in self.edges],
        }


@dataclass
class ExecutionFocus:
    """Active node in context: outer graph plus optional nested child graph."""

    root: GraphExecutionView
    nested: GraphExecutionView | None = None
    active_run_id: str = ""
    active_node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_run_id": self.active_run_id,
            "active_node_id": self.active_node_id,
            "root": self.root.to_dict(),
            "nested": None if self.nested is None else self.nested.to_dict(),
        }


def view_from_checkpoint(
    checkpoint: dict[str, Any],
    *,
    run_id: str,
    active_node_id: str | None = None,
    scope: Literal["root", "nested"] = "root",
    parent_node_id: str | None = None,
) -> GraphExecutionView:
    """Build a view from an :class:`~mechaharness.graph.ExecutionGraph` checkpoint."""
    raw_nodes = checkpoint.get("nodes") or {}
    nodes: list[GraphNodeView] = []
    if isinstance(raw_nodes, dict):
        for node_id, raw in raw_nodes.items():
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind", "node"))
            status = str(raw.get("status", "pending"))
            goal = str(raw.get("goal", ""))
            short = node_id.split(":")[-1] if ":" in node_id else node_id
            nodes.append(
                GraphNodeView(
                    id=str(node_id),
                    kind=kind,
                    status=status,
                    goal=goal,
                    label=f"{kind} ({short})",
                )
            )
    nodes.sort(key=lambda n: n.id)

    edges: list[tuple[str, str]] = []
    for edge in checkpoint.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        src = edge.get("from_node")
        dst = edge.get("to_node")
        if isinstance(src, str) and isinstance(dst, str):
            edges.append((src, dst))

    return GraphExecutionView(
        run_id=run_id,
        goal=str(checkpoint.get("goal", "")),
        nodes=nodes,
        edges=edges,
        active_node_id=active_node_id,
        scope=scope,
        parent_node_id=parent_node_id,
    )


def _event_payload(event: Any) -> dict[str, Any]:
    payload = getattr(event, "payload", None)
    return dict(payload) if isinstance(payload, dict) else {}


def _event_type(event: Any) -> str:
    return str(getattr(event, "type", ""))


def _event_run_id(event: Any) -> str:
    return str(getattr(event, "run_id", ""))


def active_node_from_events(events: list[Any], *, run_id: str) -> str | None:
    """Return the node id currently running on ``run_id`` (open start, no end)."""
    open_by_node: dict[str, int] = {}
    for event in events:
        if _event_run_id(event) != run_id:
            continue
        etype = _event_type(event)
        payload = _event_payload(event)
        node_id = payload.get("node_id")
        if not isinstance(node_id, str):
            continue
        if etype == GRAPH_NODE_START:
            open_by_node[node_id] = open_by_node.get(node_id, 0) + 1
        elif etype == GRAPH_NODE_END:
            if node_id in open_by_node:
                open_by_node[node_id] -= 1
                if open_by_node[node_id] <= 0:
                    del open_by_node[node_id]
    if not open_by_node:
        return None
    # Prefer a node explicitly marked running in the latest start payload.
    last_running: str | None = None
    for event in reversed(events):
        if _event_run_id(event) != run_id or _event_type(event) != GRAPH_NODE_START:
            continue
        payload = _event_payload(event)
        node_id = payload.get("node_id")
        if isinstance(node_id, str) and node_id in open_by_node:
            last_running = node_id
            break
    return last_running or next(iter(open_by_node))


def latest_graph_checkpoint(events: list[Any], *, run_id: str) -> dict[str, Any] | None:
    for event in reversed(events):
        if _event_run_id(event) != run_id:
            continue
        if _event_type(event) != GRAPH_NODE_EVENT:
            continue
        payload = _event_payload(event)
        graph = payload.get("graph")
        if isinstance(graph, dict):
            return graph
    return None


def _child_run_parent_prefix(parent_run_id: str, child_run_id: str) -> str | None:
    """Return the parent node id embedded in a MechaHarness child run id.

    Child runs are named ``{parent_run_id}:{node_id}`` where ``node_id`` may
    itself contain ``:`` (for example ``{uuid}:0``).
    """
    prefix = f"{parent_run_id}:"
    if not child_run_id.startswith(prefix):
        return None
    return child_run_id[len(prefix) :]


def execution_focus_from_events(
    events: list[Any],
    *,
    root_run_id: str,
    root_checkpoint: dict[str, Any] | None = None,
) -> ExecutionFocus:
    """Derive root + nested views and the active node from MechaHarness events."""
    active_run = root_run_id
    active_node: str | None = None
    for event in reversed(events):
        etype = _event_type(event)
        if etype != GRAPH_NODE_START:
            continue
        rid = _event_run_id(event)
        payload = _event_payload(event)
        node_id = payload.get("node_id")
        if not isinstance(node_id, str):
            continue
        if active_node_from_events(events, run_id=rid) == node_id:
            active_run = rid
            active_node = node_id
            break

    root_cp = root_checkpoint or latest_graph_checkpoint(events, run_id=root_run_id) or {}
    root_active = active_node if active_run == root_run_id else None
    if root_active is None and active_run != root_run_id:
        parent_node = _child_run_parent_prefix(root_run_id, active_run)
        if parent_node:
            root_active = parent_node

    root_view = view_from_checkpoint(
        root_cp,
        run_id=root_run_id,
        active_node_id=root_active,
        scope="root",
    )

    nested_view: GraphExecutionView | None = None
    if active_run != root_run_id:
        child_cp = latest_graph_checkpoint(events, run_id=active_run) or {}
        nested_view = view_from_checkpoint(
            child_cp,
            run_id=active_run,
            active_node_id=active_node,
            scope="nested",
            parent_node_id=_child_run_parent_prefix(root_run_id, active_run),
        )

    return ExecutionFocus(
        root=root_view,
        nested=nested_view,
        active_run_id=active_run,
        active_node_id=active_node,
    )


def _mermaid_node_id(node_id: str) -> str:
    safe = node_id.replace(":", "_").replace("-", "_").replace(".", "_")
    return f"n_{safe}"


def render_mermaid(view: GraphExecutionView) -> str:
    """Mermaid flowchart for docs / dashboards."""
    lines = ["flowchart TD"]
    for node in view.nodes:
        mid = _mermaid_node_id(node.id)
        title = node.label or node.kind
        status = node.status
        if view.active_node_id == node.id:
            lines.append(f'  {mid}["{title}\\n{status}"]:::active')
        else:
            lines.append(f'  {mid}["{title}\\n{status}"]')
    for src, dst in view.edges:
        lines.append(f"  {_mermaid_node_id(src)} --> {_mermaid_node_id(dst)}")
    if view.active_node_id:
        lines.append("  classDef active fill:#ffe6a7,stroke:#b45309,stroke-width:3px")
    return "\n".join(lines)


def render_ascii(view: GraphExecutionView) -> str:
    """Compact terminal view of the graph and active node."""
    if not view.nodes:
        return f"(empty graph run_id={view.run_id})"
    width = max(len(n.label or n.kind) for n in view.nodes) + 4
    lines = [f"run {view.run_id}  goal={view.goal or '-'}  scope={view.scope}"]
    for node in view.nodes:
        marker = ">>" if view.active_node_id == node.id else "  "
        label = (node.label or node.kind).ljust(width)
        lines.append(f"{marker} [{label}] {node.status}")
    if view.edges:
        lines.append("edges:")
        for src, dst in view.edges:
            lines.append(f"  {src} -> {dst}")
    if view.scope == "nested" and view.parent_node_id:
        lines.append(f"(nested under parent node {view.parent_node_id})")
    return "\n".join(lines)


def render_focus_ascii(focus: ExecutionFocus) -> str:
    parts = [render_ascii(focus.root)]
    if focus.nested is not None:
        parts.append("")
        parts.append("--- nested execution ---")
        parts.append(render_ascii(focus.nested))
    if focus.active_node_id:
        parts.append("")
        parts.append(
            f"active: node={focus.active_node_id} run={focus.active_run_id}",
        )
    return "\n".join(parts)
