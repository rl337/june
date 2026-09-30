"""Knowledge graph — June state, not harness context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class KnowledgeFact:
    subject: str
    predicate: str
    object: str
    id: str = field(default_factory=lambda: str(uuid4()))
    confidence: float = 1.0
    provenance: dict[str, Any] = field(default_factory=dict)
    authoritative: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeGraph:
    """Scoped query surface; promotion to authoritative knowledge is June policy."""

    def __init__(self) -> None:
        self._facts: dict[str, KnowledgeFact] = {}

    def propose(self, fact: KnowledgeFact) -> KnowledgeFact:
        fact.authoritative = False
        self._facts[fact.id] = fact
        return fact

    def promote(self, fact_id: str) -> KnowledgeFact | None:
        fact = self._facts.get(fact_id)
        if fact is None:
            return None
        fact.authoritative = True
        return fact

    def query(self, *, subject: str | None = None) -> list[KnowledgeFact]:
        facts = list(self._facts.values())
        if subject is not None:
            facts = [f for f in facts if f.subject == subject]
        return facts

    def scoped_context(self, *, subject: str | None = None) -> list[dict[str, Any]]:
        """Materialize a small ContextProvider-style payload for MechaHarness."""
        return [
            {
                "subject": f.subject,
                "predicate": f.predicate,
                "object": f.object,
                "confidence": f.confidence,
                "authoritative": f.authoritative,
            }
            for f in self.query(subject=subject)
            if f.authoritative
        ]
