"""Rolling event-rate bins for the console activity chart."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DEFAULT_BIN_SECONDS = 2.0
DEFAULT_BIN_COUNT = 60  # ~2 minutes at 2s bins


def build_event_rate(
    events: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    bin_seconds: float = DEFAULT_BIN_SECONDS,
    bin_count: int = DEFAULT_BIN_COUNT,
) -> dict[str, Any]:
    """Bucket serialized events into a rolling histogram.

    Returns ``{bin_seconds, bins: [{start, end, count, event_ids}]}`` where
    ``event_ids`` are indices into the provided ``events`` list.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    width = max(0.25, float(bin_seconds))
    count = max(1, int(bin_count))
    # Align end to the current bin boundary.
    end_ts = current.timestamp()
    end_aligned = (int(end_ts // width) + 1) * width
    start_aligned = end_aligned - count * width

    bins: list[dict[str, Any]] = []
    for i in range(count):
        b0 = start_aligned + i * width
        b1 = b0 + width
        bins.append(
            {
                "index": i,
                "start": datetime.fromtimestamp(b0, tz=timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(b1, tz=timezone.utc).isoformat(),
                "start_ts": b0,
                "end_ts": b1,
                "count": 0,
                "event_indices": [],
            }
        )

    for idx, event in enumerate(events):
        ts_raw = event.get("ts")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        t = ts.timestamp()
        if t < start_aligned or t >= end_aligned:
            continue
        bin_i = int((t - start_aligned) // width)
        if 0 <= bin_i < count:
            bins[bin_i]["count"] += 1
            bins[bin_i]["event_indices"].append(idx)

    return {
        "bin_seconds": width,
        "bin_count": count,
        "updated_at": current.isoformat(),
        "bins": [
            {
                "index": b["index"],
                "start": b["start"],
                "end": b["end"],
                "count": b["count"],
                "event_indices": b["event_indices"],
            }
            for b in bins
        ],
    }
