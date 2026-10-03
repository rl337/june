"""Rolling event-rate bins for the console activity chart."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from june.console.event_rate import build_event_rate


def test_build_event_rate_bins_events_by_timestamp() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        {"ts": (now - timedelta(seconds=3)).isoformat(), "type": "a"},
        {"ts": (now - timedelta(seconds=2.5)).isoformat(), "type": "b"},
        {"ts": (now - timedelta(seconds=25)).isoformat(), "type": "c"},
        {"ts": (now - timedelta(seconds=200)).isoformat(), "type": "old"},
    ]
    rate = build_event_rate(events, now=now, bin_seconds=2.0, bin_count=60)
    assert rate["bin_seconds"] == 2.0
    assert len(rate["bins"]) == 60
    total = sum(b["count"] for b in rate["bins"])
    assert total == 3  # oldest event falls outside the window
    hot = [b for b in rate["bins"] if b["count"]]
    assert any(b["count"] >= 2 for b in hot)
    assert all(isinstance(i, int) for b in hot for i in b["event_indices"])
