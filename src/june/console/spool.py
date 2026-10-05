"""Rolling-file persistence for console events and instance checkpoints.

June incubates this observability store. The contract is intentionally small
so a mature version can later be promoted into MechaHarness as a reusable
event/checkpoint spool without dragging June-specific UI policy along.

Layout under ``root``::

    events/events-YYYYMMDD-HH.jsonl  # append-only, hourly rollover
    instances/<safe_run_id>.json     # latest snapshot per instance run

Retention (applied at rollover):
  - Always keep at least ``min_segments`` files (default 24).
  - Among the surplus, delete segments older than ``max_age`` (default 1 day).

Lookups are memory-first at the hub; this module is the disk fallback.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SAFE_RUN_ID = re.compile(r"[^A-Za-z0-9._-]+")
_SEGMENT_NAME = re.compile(r"^events-(\d{8})-(\d{2})(?:-(\d+))?\.jsonl$")


def safe_run_id(run_id: str) -> str:
    """Filesystem-safe encoding of a run id (keeps uniqueness for cron ids)."""
    text = str(run_id or "").strip()
    if not text:
        return "unknown"
    return _SAFE_RUN_ID.sub("__", text)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConsoleSpool:
    """Append-only JSONL event spool + per-instance JSON snapshots."""

    def __init__(
        self,
        root: Path | str,
        *,
        min_segments: int = 24,
        max_age: timedelta | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = Path(root)
        self.events_dir = self.root / "events"
        self.instances_dir = self.root / "instances"
        self.min_segments = max(1, int(min_segments))
        self.max_age = max_age if max_age is not None else timedelta(days=1)
        self._now = now or _utc_now
        self._lock = threading.Lock()
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.instances_dir.mkdir(parents=True, exist_ok=True)
        self._current_hour: str | None = None
        self._current_path = self._open_hour_segment(self._now())

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
            now = self._now()
            if not isinstance(now, datetime):
                now = _utc_now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            hour_key = now.strftime("%Y%m%d-%H")
            if hour_key != self._current_hour:
                self._current_path = self._open_hour_segment_locked(now)
                self._trim_segments_locked(now=now)
            with self._current_path.open("ab") as fh:
                fh.write(data)

    def _segment_paths(self) -> list[Path]:
        return sorted(self.events_dir.glob("events-*.jsonl"))

    def _open_hour_segment(self, now: datetime) -> Path:
        with self._lock:
            return self._open_hour_segment_locked(now)

    def _open_hour_segment_locked(self, now: datetime) -> Path:
        hour_key = now.strftime("%Y%m%d-%H")
        path = self.events_dir / f"events-{hour_key}.jsonl"
        path.touch(exist_ok=True)
        self._current_hour = hour_key
        self._current_path = path
        return path

    def _segment_time(self, path: Path) -> datetime | None:
        match = _SEGMENT_NAME.match(path.name)
        if match is None:
            try:
                return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                return None
        day, hour = match.group(1), match.group(2)
        try:
            return datetime.strptime(f"{day}{hour}", "%Y%m%d%H").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _trim_segments_locked(self, *, now: datetime) -> None:
        """Drop surplus segments that are older than max_age; keep >= min_segments."""
        segments = self._segment_paths()
        cutoff = now - self.max_age
        while len(segments) > self.min_segments:
            oldest = segments[0]
            # Never delete the active hour file.
            if oldest == self._current_path:
                break
            stamp = self._segment_time(oldest)
            if stamp is None or stamp >= cutoff:
                break
            try:
                oldest.unlink(missing_ok=True)
            except OSError:
                break
            segments.pop(0)
