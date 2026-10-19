"""Sugiyama-style layered DAG layout (pre-baked coordinates).

Ranks from longest-path, barycenter crossing reduction, then left→right
(or top→bottom) coordinate assignment with dedicated edge channels between
ranks so orthogonal conduits need not cross peer boxes.

Pure Python — no Graphviz/ELK. Mutates ``x``/``y`` on duck-typed nodes that
expose ``id``, ``w``, ``h``, ``x``, ``y``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Literal, Protocol, runtime_checkable


@runtime_checkable
class LayoutNode(Protocol):
    id: str
    w: float
    h: float
    x: float
    y: float


Direction = Literal["lr", "tb"]

DEFAULT_RANK_GAP = 72.0
DEFAULT_NODE_GAP = 28.0
CROSSING_SWEEPS = 4


def topo_order(ids: list[str], edges: list[tuple[str, str]]) -> list[str]:
    indeg = {i: 0 for i in ids}
    outs: dict[str, list[str]] = {i: [] for i in ids}
    id_set = set(ids)
    for a, b in edges:
        if a not in id_set or b not in id_set:
            continue
        outs[a].append(b)
        indeg[b] += 1
    queue = [i for i in ids if indeg[i] == 0]
    ordered: list[str] = []
    seen = set(queue)
    while queue:
        cur = queue.pop(0)
        ordered.append(cur)
        for nxt in outs[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0 and nxt not in seen:
                queue.append(nxt)
                seen.add(nxt)
    for i in ids:
        if i not in seen:
            ordered.append(i)
    return ordered


def longest_path_ranks(ids: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """Layer index from roots (0) along the longest dependency path."""
    preds: dict[str, list[str]] = {i: [] for i in ids}
    id_set = set(ids)
    for a, b in edges:
        if a in id_set and b in id_set:
            preds[b].append(a)
    ranks = {i: 0 for i in ids}
    for nid in topo_order(ids, edges):
        if preds[nid]:
            ranks[nid] = max(ranks[p] for p in preds[nid]) + 1
    return ranks


def _normalize_edges(
    edges: Iterable[Any],
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        if isinstance(edge, tuple) and len(edge) >= 2:
            a, b = str(edge[0]), str(edge[1])
        elif isinstance(edge, dict):
            a = edge.get("from") or edge.get("from_node")
            b = edge.get("to") or edge.get("to_node")
            if not isinstance(a, str) or not isinstance(b, str):
                continue
        else:
            continue
        key = (a, b)
        if key in seen or a == b:
            continue
        seen.add(key)
        out.append(key)
    return out


def count_crossings(
    left: list[str],
    right: list[str],
    edges: list[tuple[str, str]],
) -> int:
    """Two-layer crossing count between ordered ``left`` and ``right`` ranks."""
    li = {n: i for i, n in enumerate(left)}
    ri = {n: i for i, n in enumerate(right)}
    pairs = [
        (li[a], ri[b])
        for a, b in edges
        if a in li and b in ri
    ]
    crossings = 0
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            a1, b1 = pairs[i]
            a2, b2 = pairs[j]
            if (a1 - a2) * (b1 - b2) < 0:
                crossings += 1
    return crossings


def _barycenters(
    targets: list[str],
    anchors: list[str],
    edges: list[tuple[str, str]],
    *,
    forward: bool,
) -> dict[str, float]:
    """Average neighbor index in the adjacent rank (barycenter heuristic)."""
    anchor_pos = {n: float(i) for i, n in enumerate(anchors)}
    buckets: dict[str, list[float]] = {t: [] for t in targets}
    for a, b in edges:
        if forward:
            src, dst = a, b
        else:
            src, dst = b, a
        if dst in buckets and src in anchor_pos:
            buckets[dst].append(anchor_pos[src])
    return {
        t: (sum(vals) / len(vals) if vals else float(targets.index(t)))
        for t, vals in buckets.items()
    }


def reduce_crossings(
    order_by_rank: dict[int, list[str]],
    edges: list[tuple[str, str]],
    *,
    sweeps: int = CROSSING_SWEEPS,
) -> dict[int, list[str]]:
    """Barycenter sweeps to cut two-layer crossings; mutates a copy of orders."""
    ranks = sorted(order_by_rank)
    if len(ranks) < 2:
        return {r: list(order_by_rank[r]) for r in ranks}

    order = {r: list(order_by_rank[r]) for r in ranks}
    for sweep in range(max(1, sweeps)):
        forward = sweep % 2 == 0
        seq = ranks if forward else list(reversed(ranks))
        for r in seq:
            neighbor = r - 1 if forward else r + 1
            if neighbor not in order:
                continue
            bary = _barycenters(
                order[r],
                order[neighbor],
                edges,
                forward=forward,
            )
            # Stable sort: barycenter, then prior index.
            prior = {n: i for i, n in enumerate(order[r])}
            order[r] = sorted(order[r], key=lambda n: (bary.get(n, 0.0), prior[n]))
    return order


def total_crossings(
    order_by_rank: dict[int, list[str]],
    edges: list[tuple[str, str]],
) -> int:
    ranks = sorted(order_by_rank)
    total = 0
    for i in range(len(ranks) - 1):
        total += count_crossings(
            order_by_rank[ranks[i]],
            order_by_rank[ranks[i + 1]],
            edges,
        )
    return total


def boxes_overlap(a: LayoutNode, b: LayoutNode, *, pad: float = 0.0) -> bool:
    return not (
        a.x + a.w + pad <= b.x
        or b.x + b.w + pad <= a.x
        or a.y + a.h + pad <= b.y
        or b.y + b.h + pad <= a.y
    )


def layout_layered_dag(
    nodes: list[Any],
    edges: Iterable[Any],
    *,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    rank_gap: float = DEFAULT_RANK_GAP,
    node_gap: float = DEFAULT_NODE_GAP,
    direction: Direction = "lr",
    crossing_sweeps: int = CROSSING_SWEEPS,
) -> tuple[float, float]:
    """Assign ``x``/``y`` on ``nodes`` via layered DAG placement.

    Returns ``(content_width, content_height)`` of the placed bounding box
    relative to the origin (not including outer pad outside origin).
    """
    if not nodes:
        return 0.0, 0.0

    by_id = {str(n.id): n for n in nodes}
    ids = list(by_id)
    pairs = _normalize_edges(edges)
    pairs = [(a, b) for a, b in pairs if a in by_id and b in by_id]

    if not pairs:
        # Disconnected / no edges: pack as a single flow line.
        return _pack_line(
            [by_id[i] for i in ids],
            origin_x=origin_x,
            origin_y=origin_y,
            gap=node_gap,
            direction=direction,
        )

    ranks = longest_path_ranks(ids, pairs)
    seed_order = {nid: i for i, nid in enumerate(topo_order(ids, pairs))}
    order_by_rank: dict[int, list[str]] = defaultdict(list)
    for nid in sorted(ids, key=lambda n: (ranks[n], seed_order.get(n, 0))):
        order_by_rank[ranks[nid]].append(nid)

    before = total_crossings(order_by_rank, pairs)
    order_by_rank = reduce_crossings(
        order_by_rank, pairs, sweeps=crossing_sweeps
    )
    after = total_crossings(order_by_rank, pairs)
    # Keep the better of seed vs reduced (barycenter can regress on tiny graphs).
    if after > before:
        order_by_rank = defaultdict(list)
        for nid in sorted(ids, key=lambda n: (ranks[n], seed_order.get(n, 0))):
            order_by_rank[ranks[nid]].append(nid)

    return _assign_coordinates(
        by_id,
        order_by_rank,
        origin_x=origin_x,
        origin_y=origin_y,
        rank_gap=rank_gap,
        node_gap=node_gap,
        direction=direction,
    )


def _pack_line(
    nodes: list[Any],
    *,
    origin_x: float,
    origin_y: float,
    gap: float,
    direction: Direction,
) -> tuple[float, float]:
    if direction == "tb":
        y = origin_y
        max_w = 0.0
        for node in nodes:
            node.x = origin_x
            node.y = y
            y += node.h + gap
            max_w = max(max_w, node.w)
        for node in nodes:
            node.x = origin_x + (max_w - node.w) / 2
        h = y - gap - origin_y if nodes else 0.0
        return max_w, max(h, 0.0)

    x = origin_x
    max_h = 0.0
    for node in nodes:
        node.x = x
        node.y = origin_y
        x += node.w + gap
        max_h = max(max_h, node.h)
    for node in nodes:
        node.y = origin_y + (max_h - node.h) / 2
    w = x - gap - origin_x if nodes else 0.0
    return max(w, 0.0), max_h


def _assign_coordinates(
    by_id: dict[str, Any],
    order_by_rank: dict[int, list[str]],
    *,
    origin_x: float,
    origin_y: float,
    rank_gap: float,
    node_gap: float,
    direction: Direction,
) -> tuple[float, float]:
    ranks = sorted(order_by_rank)
    # Measure each rank band.
    band_sizes: list[tuple[float, float]] = []  # (primary span, secondary span)
    for r in ranks:
        members = [by_id[i] for i in order_by_rank[r]]
        if direction == "lr":
            primary = max(n.w for n in members)
            secondary = sum(n.h for n in members) + node_gap * max(0, len(members) - 1)
        else:
            primary = max(n.h for n in members)
            secondary = sum(n.w for n in members) + node_gap * max(0, len(members) - 1)
        band_sizes.append((primary, secondary))

    max_secondary = max((s for _, s in band_sizes), default=0.0)
    cursor = origin_x if direction == "lr" else origin_y
    for r, (primary, secondary) in zip(ranks, band_sizes):
        members = [by_id[i] for i in order_by_rank[r]]
        # Center shorter bands along the cross axis.
        cross0 = origin_y if direction == "lr" else origin_x
        cross = cross0 + (max_secondary - secondary) / 2

        for node in members:
            if direction == "lr":
                node.x = cursor + (primary - node.w) / 2
                node.y = cross
                cross += node.h + node_gap
            else:
                node.y = cursor + (primary - node.h) / 2
                node.x = cross
                cross += node.w + node_gap
        cursor += primary + rank_gap

    if direction == "lr":
        width = cursor - rank_gap - origin_x
        height = max_secondary
    else:
        width = max_secondary
        height = cursor - rank_gap - origin_y
    return max(width, 0.0), max(height, 0.0)


__all__ = [
    "DEFAULT_NODE_GAP",
    "DEFAULT_RANK_GAP",
    "boxes_overlap",
    "count_crossings",
    "layout_layered_dag",
    "longest_path_ranks",
    "reduce_crossings",
    "topo_order",
    "total_crossings",
]
