"""JSON-directory persistence for June-owned durable state."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


class JsonStore:
    """Simple durable store: one JSON file per collection.

    Mutations are serialized per collection and written via temp+rename so a
    concurrent reader never observes a partial file.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def _path(self, collection: str) -> Path:
        return self.root / f"{collection}.json"

    def _lock_for(self, collection: str) -> threading.RLock:
        with self._locks_guard:
            lock = self._locks.get(collection)
            if lock is None:
                lock = threading.RLock()
                self._locks[collection] = lock
            return lock

    def load(self, collection: str) -> dict[str, Any]:
        path = self._path(collection)
        with self._lock_for(collection):
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}

    def save(self, collection: str, data: dict[str, Any]) -> None:
        path = self._path(collection)
        with self._lock_for(collection):
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(data, indent=2, sort_keys=True, default=str)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{collection}.",
                suffix=".tmp",
                dir=str(path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise

    def get_item(self, collection: str, item_id: str) -> dict[str, Any] | None:
        return self.load(collection).get(item_id)

    def put_item(self, collection: str, item_id: str, item: dict[str, Any]) -> None:
        with self._lock_for(collection):
            data = self.load(collection)
            data[item_id] = item
            self.save(collection, data)

    def delete_item(self, collection: str, item_id: str) -> None:
        with self._lock_for(collection):
            data = self.load(collection)
            data.pop(item_id, None)
            self.save(collection, data)

    def list_items(self, collection: str) -> list[dict[str, Any]]:
        return list(self.load(collection).values())

    def update_item(
        self,
        collection: str,
        item_id: str,
        mutator: Any,
    ) -> dict[str, Any] | None:
        """Atomically load-modify-save one item under the collection lock."""
        with self._lock_for(collection):
            data = self.load(collection)
            current = data.get(item_id)
            if current is None:
                return None
            updated_raw = mutator(dict(current))
            if not isinstance(updated_raw, dict):
                return None
            updated: dict[str, Any] = updated_raw
            data[item_id] = updated
            self.save(collection, data)
            return updated
