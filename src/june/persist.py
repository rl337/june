"""JSON-directory persistence for June-owned durable state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStore:
    """Simple durable store: one JSON file per collection."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, collection: str) -> Path:
        return self.root / f"{collection}.json"

    def load(self, collection: str) -> dict[str, Any]:
        path = self._path(collection)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, collection: str, data: dict[str, Any]) -> None:
        path = self._path(collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")

    def get_item(self, collection: str, item_id: str) -> dict[str, Any] | None:
        return self.load(collection).get(item_id)

    def put_item(self, collection: str, item_id: str, item: dict[str, Any]) -> None:
        data = self.load(collection)
        data[item_id] = item
        self.save(collection, data)

    def delete_item(self, collection: str, item_id: str) -> None:
        data = self.load(collection)
        data.pop(item_id, None)
        self.save(collection, data)

    def list_items(self, collection: str) -> list[dict[str, Any]]:
        return list(self.load(collection).values())
