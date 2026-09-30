"""Document manager — durable information substrate owned by June."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class DocumentRef:
    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    version: int = 1
    media_type: str = "text/plain"
    summary: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentStore:
    """Index/metadata store; payloads stay out of durable graph state."""

    def __init__(self) -> None:
        self._docs: dict[str, DocumentRef] = {}
        self._payloads: dict[str, str] = {}

    def put(self, ref: DocumentRef, payload: str | None = None) -> DocumentRef:
        self._docs[ref.id] = ref
        if payload is not None:
            self._payloads[ref.id] = payload
        return ref

    def discover(self, query: str = "") -> list[DocumentRef]:
        q = query.lower()
        return [
            d
            for d in self._docs.values()
            if not q or q in d.title.lower() or q in d.summary.lower()
        ]

    def load(self, doc_id: str) -> tuple[DocumentRef, str] | None:
        ref = self._docs.get(doc_id)
        if ref is None:
            return None
        return ref, self._payloads.get(doc_id, "")
