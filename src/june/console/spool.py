"""Rolling-file persistence for console events and instance checkpoints.

June incubates this observability store. The contract is intentionally small
so a mature version can later be promoted into MechaHarness as a reusable
event/checkpoint spool without dragging June-specific UI policy along.

Layout under ``root``::

    events/events-000001.jsonl   # append-only, rotated by size
    events/events-000002.jsonl
    instances/<safe_run_id>.json # latest snapshot per instance run

Lookups are memory-first at the hub; this module is the disk fallback.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_SAFE_RUN_ID = re.compile(r"[^A-Za-z0-9._-]+")


def safe_run_id(run_id: str) -> str:
    """Filesystem-safe encoding of a run id (keeps uniqueness for cron ids)."""
    text = str(run_id or "").strip()
    if not text:
        return "unknown"
    return _SAFE_RUN_ID.sub("__", text)


class ConsoleSpool:
    """Append-only JSONL event spool + per-instance JSON snapshots."""

    def __init__(
        self,
        root: Path | str,
        *,
        max_segment_bytes: int = 1_000_000,
        max_segments: int = 48,
    ) -> None:
        self.root = Path(root)
        self.events_dir = self.root / "events"
        self.instances_dir = self.root / "instances"
        self.max_segment_bytes = max(256, int(max_segment_bytes))
        self.max_segments = max(2, int(max_segments))
        self._lock = threading.Lock()
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.instances_dir.mkdir(parents=True, exist_ok=True)
        self._current_path = self._resolve_current_segment()

    def append_event(self, record: dict[str, Any]) -> None:
        self._append({"stream": "event", **record})

    def append_journal(self, record: dict[str, Any]) -> None:
        self._append({"stream": "journal", **record})

    def put_instance(self, run_id: str, instance: dict[str, Any]) -> None:
        path = self.instances_dir / f"{safe_run_id(run_id)}.json"
        payload = dict(instance)
        payload["run_id"] = run_id
        tmp = path.with_suffix(".json.tmp")
        text = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)

    def get_instance(self, run_id: str) -> dict[str, Any] | None:
        path = self.instances_dir / f"{safe_run_id(run_id)}.json"
        if not path.is_file():
            # Fallback: scan (handles legacy/odd encodings).
            with self._lock:
                for candidate in self.instances_dir.glob("*.json"):
                    try:
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(data, dict) and data.get("run_id") == run_id:
                        return data
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def list_instances(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._lock:
            paths = sorted(self.instances_dir.glob("*.json"))
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                rows.append(data)
        rows.sort(key=lambda r: str(r.get("finished_at") or r.get("started_at") or ""))
        return rows

    def iter_records(
        self,
        *,
        run_id: str | None = None,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Yield spooled records, optionally filtered by run_id."""
        segments = self._segment_paths()
        if newest_first:
            segments = list(reversed(segments))
        yielded = 0
        for path in segments:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            if newest_first:
                lines = list(reversed(lines))
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                if run_id is not None and str(row.get("run_id") or "") != run_id:
                    continue
                yield row
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

    def _append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        data = line.encode("utf-8")
        with self._lock:
            path = self._current_path
            if path.exists() and path.stat().st_size + len(data) > self.max_segment_bytes:
                path = self._rotate_locked()
            with path.open("ab") as fh:
                fh.write(data)
            self._trim_segments_locked()

    def _segment_paths(self) -> list[Path]:
        return sorted(self.events_dir.glob("events-*.jsonl"))

    def _resolve_current_segment(self) -> Path:
        segments = self._segment_paths()
        if not segments:
            path = self.events_dir / "events-000001.jsonl"
            path.touch(exist_ok=True)
            return path
        return segments[-1]

    def _rotate_locked(self) -> Path:
        segments = self._segment_paths()
        if segments:
            last = segments[-1].stem  # events-000001
            try:
                n = int(last.split("-")[-1]) + 1
            except ValueError:
                n = len(segments) + 1
        else:
            n = 1
        path = self.events_dir / f"events-{n:06d}.jsonl"
        path.touch(exist_ok=True)
        self._current_path = path
        return path

    def _trim_segments_locked(self) -> None:
        segments = self._segment_paths()
        while len(segments) > self.max_segments:
            old = segments.pop(0)
            try:
                old.unlink(missing_ok=True)
            except OSError:
                break
