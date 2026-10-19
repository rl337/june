"""Sugiyama layered DAG layout for Bubble Trouble world baking."""

from __future__ import annotations

from dataclasses import dataclass

from june.console.layered_dag import (
    boxes_overlap,
    count_crossings,
    layout_layered_dag,
    longest_path_ranks,
    reduce_crossings,
    total_crossings,
)


@dataclass
class Box:
    id: str
    w: float = 100.0
    h: float = 40.0
    x: float = 0.0
    y: float = 0.0


def test_longest_path_ranks_fanout() -> None:
    ids = ["cron", "minute", "hourly", "chat"]
    edges = [
        ("cron", "minute"),
        ("cron", "hourly"),
        ("cron", "chat"),
    ]
    ranks = longest_path_ranks(ids, edges)
    assert ranks["cron"] == 0
    assert ranks["minute"] == ranks["hourly"] == ranks["chat"] == 1


def test_crossing_reduction_improves_swapped_peers() -> None:
    # Left A,B → right X,Y with crossing edges A→Y, B→X if ordered poorly.
    order = {0: ["A", "B"], 1: ["Y", "X"]}
    edges = [("A", "X"), ("B", "Y")]
    before = total_crossings(order, edges)
    assert before == 1
    reduced = reduce_crossings(order, edges, sweeps=4)
    after = total_crossings(reduced, edges)
    assert after == 0
    assert reduced[1] == ["X", "Y"]


def test_layout_layered_no_peer_overlap_and_channel() -> None:
    nodes = [
        Box("cron", w=80, h=60),
        Box("minute", w=200, h=120),
        Box("hourly", w=200, h=120),
        Box("chat", w=220, h=180),
    ]
    edges = [
        {"from": "cron", "to": "minute"},
        {"from": "cron", "to": "hourly"},
        {"from": "cron", "to": "chat"},
    ]
    w, h = layout_layered_dag(
        nodes, edges, origin_x=10, origin_y=10, rank_gap=72, node_gap=28
    )
    assert w > 0 and h > 0
    by = {n.id: n for n in nodes}
    assert by["cron"].x + by["cron"].w < by["minute"].x
    gap = by["minute"].x - (by["cron"].x + by["cron"].w)
    assert gap >= 40
    # Same-rank peers must not overlap.
    peers = [by["minute"], by["hourly"], by["chat"]]
    for i, a in enumerate(peers):
        for b in peers[i + 1 :]:
            assert not boxes_overlap(a, b, pad=1.0)


def test_layout_pipeline_top_to_bottom() -> None:
    nodes = [Box("a"), Box("b"), Box("c")]
    edges = [("a", "b"), ("b", "c")]
    layout_layered_dag(
        nodes, edges, origin_x=0, origin_y=0, direction="tb", rank_gap=48, node_gap=16
    )
    by = {n.id: n for n in nodes}
    assert by["a"].y + by["a"].h < by["b"].y
    assert by["b"].y + by["b"].h < by["c"].y


def test_count_crossings_unit() -> None:
    assert count_crossings(["A", "B"], ["X", "Y"], [("A", "Y"), ("B", "X")]) == 1
    assert count_crossings(["A", "B"], ["X", "Y"], [("A", "X"), ("B", "Y")]) == 0


def test_world_cron_uses_layered_without_peer_overlap() -> None:
    import pytest

    pytest.importorskip("mechaharness")
    from june.console.layered_dag import boxes_overlap
    from june.console.world import build_world_graph
    from june.harness.cron_graph import build_console_cron_graph

    world = build_world_graph(
        build_console_cron_graph().checkpoint(),
        [],
        run_id="june.console.cron",
    )
    tops = world.nodes
    for i, a in enumerate(tops):
        for b in tops[i + 1 :]:
            assert not boxes_overlap(a, b, pad=1.0), f"{a.id} overlaps {b.id}"
    by = {n.id: n for n in tops}
    cron = by["june.console.cron:cron"]
    minute = by["june.console.cron:bucket:minute"]
    assert cron.x + cron.w + 40 <= minute.x
