"""Document manager — durable information substrate owned by June."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


@dataclass
class DocumentRef:
    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    version: int = 1
    media_type: str = "text/plain"
    summary: str = ""
    access: str = "internal"
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentRef:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DocumentStore:
    """Index/metadata store; payloads stay out of durable graph state."""

    def __init__(self, store: JsonStore | None = None) -> None:
        self._docs: dict[str, DocumentRef] = {}
        self._payloads: dict[str, str] = {}
        self._store = store

    def put(self, ref: DocumentRef, payload: str | None = None) -> DocumentRef:
        existing = self.get(ref.id)
        if existing is not None and payload is not None:
            ref.version = existing.version + 1
        self._docs[ref.id] = ref
        if payload is not None:
            self._payloads[ref.id] = payload
        if self._store is not None:
            self._store.put_item("documents", ref.id, ref.to_dict())
            if payload is not None:
                self._store.put_item("document_payloads", ref.id, {"text": payload})
        return ref

    def get(self, doc_id: str) -> DocumentRef | None:
        if doc_id in self._docs:
            return self._docs[doc_id]
        if self._store is None:
            return None
        raw = self._store.get_item("documents", doc_id)
        if raw is None:
            return None
        ref = DocumentRef.from_dict(raw)
        self._docs[ref.id] = ref
        return ref

    def discover(self, query: str = "") -> list[DocumentRef]:
        if self._store is not None:
            for raw in self._store.list_items("documents"):
                ref = DocumentRef.from_dict(raw)
                self._docs.setdefault(ref.id, ref)
        q = query.lower()
        return [
            d
            for d in self._docs.values()
            if not q or q in d.title.lower() or q in d.summary.lower()
        ]

    def load(self, doc_id: str) -> tuple[DocumentRef, str] | None:
        ref = self.get(doc_id)
        if ref is None:
            return None
        if doc_id in self._payloads:
            return ref, self._payloads[doc_id]
        if self._store is not None:
            raw = self._store.get_item("document_payloads", doc_id)
            if raw is not None:
                text = str(raw.get("text", ""))
                self._payloads[doc_id] = text
                return ref, text
        return ref, ""

    def as_context_items(self, query: str = "", *, limit: int = 5) -> list[dict[str, Any]]:
        """Lightweight index entries for ContextProvider-style discovery."""
        items = []
        for ref in self.discover(query)[:limit]:
            items.append(
                {
                    "id": ref.id,
                    "title": ref.title,
                    "summary": ref.summary,
                    "version": ref.version,
                    "media_type": ref.media_type,
                    "provenance": ref.provenance,
                }
            )
        return items
