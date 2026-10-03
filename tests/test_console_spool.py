"""Rolling console spool + memory/disk instance lookup."""

from __future__ import annotations

from pathlib import Path

from june.console.hub import ConsoleHub
from june.console.spool import ConsoleSpool, safe_run_id


def test_safe_run_id_encodes_colons() -> None:
    assert ":" not in safe_run_id("june.console.cron:60s:abcd1234")
    assert safe_run_id("june.console.cron:60s:abcd1234").startswith("june.console.cron")


def test_rolling_jsonl_rotates_and_retains_segments(tmp_path: Path) -> None:
    spool = ConsoleSpool(tmp_path, max_segment_bytes=200, max_segments=3)
    for i in range(40):
        spool.append_event(
            {
                "ts": f"2026-01-01T00:00:{i:02d}Z",
                "type": "core:graph_node_start",
                "run_id": f"run-{i // 10}",
                "summary": f"event {i} " + ("x" * 40),
            }
        )
    segments = sorted((tmp_path / "events").glob("events-*.jsonl"))
    assert len(segments) == 3
    # Oldest segments are trimmed; newest-first still yields retained rows.
    rows = list(spool.iter_records(limit=10, newest_first=True))
    assert 1 <= len(rows) <= 10
    assert rows[0]["stream"] == "event"
    assert rows[0]["ts"] >= rows[-1]["ts"]


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
