"""Knowledge graph — June state, not harness context."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


class FactKind(str, Enum):
    EVENT = "event"
    EVIDENCE = "evidence"
    INFERRED = "inferred"
    STABLE = "stable"


@dataclass
class KnowledgeFact:
    subject: str
    predicate: str
    object: str
    id: str = field(default_factory=lambda: str(uuid4()))
    kind: FactKind = FactKind.INFERRED
    confidence: float = 1.0
    valid_from: str | None = None
    valid_to: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    authoritative: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeFact:
        payload = dict(data)
        payload["kind"] = FactKind(payload.get("kind", FactKind.INFERRED.value))
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


class KnowledgeGraph:
    """Scoped query surface; promotion to authoritative knowledge is June policy."""

    def __init__(self, store: JsonStore | None = None) -> None:
        self._facts: dict[str, KnowledgeFact] = {}
        self._store = store

    def propose(self, fact: KnowledgeFact) -> KnowledgeFact:
        fact.authoritative = False
        self._facts[fact.id] = fact
        if self._store is not None:
            self._store.put_item("knowledge", fact.id, fact.to_dict())
        return fact

    def promote(self, fact_id: str) -> KnowledgeFact | None:
        fact = self.get(fact_id)
        if fact is None:
            return None
        fact.authoritative = True
        if fact.kind is FactKind.INFERRED:
            fact.kind = FactKind.STABLE
        self._facts[fact.id] = fact
        if self._store is not None:
            self._store.put_item("knowledge", fact.id, fact.to_dict())
        return fact

    def get(self, fact_id: str) -> KnowledgeFact | None:
        if fact_id in self._facts:
            return self._facts[fact_id]
        if self._store is None:
            return None
        raw = self._store.get_item("knowledge", fact_id)
        if raw is None:
            return None
        fact = KnowledgeFact.from_dict(raw)
        self._facts[fact.id] = fact
        return fact

    def query(
        self,
        *,
        subject: str | None = None,
        kind: FactKind | None = None,
        authoritative_only: bool = False,
    ) -> list[KnowledgeFact]:
        if self._store is not None:
            for raw in self._store.list_items("knowledge"):
                fact = KnowledgeFact.from_dict(raw)
                self._facts.setdefault(fact.id, fact)
        facts = list(self._facts.values())
        if subject is not None:
            facts = [f for f in facts if f.subject == subject]
        if kind is not None:
            facts = [f for f in facts if f.kind is kind]
        if authoritative_only:
            facts = [f for f in facts if f.authoritative]
        return facts

    def scoped_context(self, *, subject: str | None = None) -> list[dict[str, Any]]:
        """Materialize a small ContextProvider-style payload for MechaHarness."""
        return [
            {
                "id": f.id,
                "subject": f.subject,
                "predicate": f.predicate,
                "object": f.object,
                "kind": f.kind.value,
                "confidence": f.confidence,
                "authoritative": f.authoritative,
                "provenance": f.provenance,
            }
            for f in self.query(subject=subject, authoritative_only=True)
        ]
