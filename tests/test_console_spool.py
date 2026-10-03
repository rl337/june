"""Rolling console spool + memory/disk instance lookup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from june.console.hub import ConsoleHub
from june.console.spool import ConsoleSpool, safe_run_id


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


def test_safe_run_id_encodes_colons() -> None:
    assert ":" not in safe_run_id("june.console.cron:60s:abcd1234")
    assert safe_run_id("june.console.cron:60s:abcd1234").startswith("june.console.cron")


def test_hourly_rollover_and_age_retention(tmp_path: Path) -> None:
    clock = _Clock(datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc))
    spool = ConsoleSpool(
        tmp_path,
        min_segments=3,
        max_age=timedelta(hours=4),
        now=clock,
    )
    # Write across 10 hours → 10 segment files initially.
    for hour in range(10):
        clock.now = datetime(2026, 1, 1, hour, 5, tzinfo=timezone.utc)
        spool.append_event(
            {
                "ts": clock.now.isoformat(),
                "type": "core:graph_node_start",
                "run_id": f"run-{hour}",
                "summary": f"hour {hour}",
            }
        )
    segments = sorted((tmp_path / "events").glob("events-*.jsonl"))
    # At ~09:05 with max_age=4h, cutoff is ~05:05. Hours 0..5 are older and
    # surplus (count > min_segments=3), so they are removed; hours 6..9 remain.
    names = [p.name for p in segments]
    assert "events-20260101-00.jsonl" not in names
    assert "events-20260101-05.jsonl" not in names
    assert "events-20260101-06.jsonl" in names
    assert "events-20260101-09.jsonl" in names
    assert len(segments) == 4

    rows = list(spool.iter_records(limit=3, newest_first=True))
    assert len(rows) == 3
    assert rows[0]["run_id"] == "run-9"


def test_retention_keeps_min_segments_even_when_old(tmp_path: Path) -> None:
    clock = _Clock(datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc))
    spool = ConsoleSpool(
        tmp_path,
        min_segments=4,
        max_age=timedelta(hours=1),
        now=clock,
    )
    for hour in range(4):
        clock.now = datetime(2026, 1, 1, hour, 0, tzinfo=timezone.utc)
        spool.append_event(
            {
                "ts": clock.now.isoformat(),
                "type": "core:graph_start",
                "run_id": f"run-{hour}",
                "summary": f"hour {hour}",
            }
        )
    # Jump far ahead; all 4 files are older than max_age, but min_segments=4.
    clock.now = datetime(2026, 1, 3, 0, 0, tzinfo=timezone.utc)
    spool.append_event(
        {
            "ts": clock.now.isoformat(),
            "type": "core:graph_start",
            "run_id": "run-new",
            "summary": "new hour",
        }
    )
    segments = sorted((tmp_path / "events").glob("events-*.jsonl"))
    # New hour file + keep at least 4 old ones that would otherwise expire.
    assert len(segments) >= 4
    assert any(p.name.startswith("events-20260103-00") for p in segments)


def test_instance_roundtrip_and_hub_disk_fallback(tmp_path: Path) -> None:
    spool = ConsoleSpool(tmp_path)
    hub = ConsoleHub(spool=spool)
    run_id = "june.console.cron:60s:spool0001"
    pipeline = {
        "id": run_id,
        "goal": "60s rollup",
        "nodes": {
            f"{run_id}:log:0": {
                "id": f"{run_id}:log:0",
                "kind": "june.event_log",
                "goal": "rollup minute metrics",
                "status": "succeeded",
            }
        },
        "edges": [],
    }
    hub.begin_instance(
        run_id=run_id,
        bucket="60s",
        parent_node_id="june.console.cron:bucket:60s",
        pipeline=pipeline,
    )
    hub.complete_instance(run_id=run_id, status="ok", pipeline=pipeline)

    # Evict from hot memory (simulate prune).
    with hub._lock:
        hub._instances.pop(run_id, None)

    assert run_id not in hub._instances
    world = hub.instance_world(run_id)
    assert world is not None
    assert world["nodes"][0]["id"] == run_id
    detail = hub.instance_node_detail(run_id, f"{run_id}:log:0")
    assert detail is not None
    assert detail["node"]["goal"] == "rollup minute metrics"


def test_hub_keeps_writing_events_to_spool(tmp_path: Path) -> None:
    class _Evt:
        def __init__(self) -> None:
            self.ts = "2026-01-01T00:00:00Z"
            self.type = "core:graph_start"
            self.run_id = "run-a"
            self.agent_id = "june"
            self.payload = {"node_count": 2}

    spool = ConsoleSpool(tmp_path)
    hub = ConsoleHub(spool=spool)
    hub.ingest_event(_Evt())
    hub.ingest_journal(
        {
            "ts": "2026-01-01T00:00:01Z",
            "type": "june.console.log",
            "run_id": "run-a",
            "message": "hello",
            "summary": "hello",
        }
    )
    rows = list(spool.iter_records(run_id="run-a", newest_first=False))
    streams = {r.get("stream") for r in rows}
    assert "event" in streams
    assert "journal" in streams
