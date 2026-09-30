"""Advisor orchestration — June triggers; MechaHarness owns the generic interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


@dataclass
class AdvisorRequest:
    trigger: str
    question: str
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    goal_id: str | None = None
    issue_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AdvisorResponse:
    request_id: str
    guidance: str
    changed_orchestration: bool = False
    outcome_improved: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AdvisorOrchestrator:
    """Sparse June-side advisor consultation at high-value boundaries."""

    HIGH_VALUE_TRIGGERS = {
        "goal_mutation",
        "repeated_failure",
        "conflicting_knowledge",
        "external_side_effect",
        "high_consequence_completion",
    }

    def __init__(self, store: JsonStore | None = None) -> None:
        self._store = store
        self._history: list[dict[str, Any]] = []

    def should_consult(self, trigger: str, *, failure_count: int = 0) -> bool:
        if trigger in self.HIGH_VALUE_TRIGGERS:
            return True
        return failure_count >= 2

    def consult(self, request: AdvisorRequest) -> AdvisorResponse:
        # Generic Advisor execution remains a MechaHarness facility. June records
        # the product decision context and a non-binding placeholder guidance.
        guidance = (
            f"Advisor stub for trigger={request.trigger}: "
            f"review evidence ({len(request.evidence_refs)} refs) before committing."
        )
        response = AdvisorResponse(
            request_id=request.id,
            guidance=guidance,
            changed_orchestration=False,
            raw={"mode": "stub", "non_binding": True},
        )
        entry = {"request": asdict(request), "response": asdict(response)}
        self._history.append(entry)
        if self._store is not None:
            self._store.put_item("advisor", request.id, entry)
        return response

    def record_outcome(self, request_id: str, *, improved: bool, changed: bool) -> None:
        for entry in self._history:
            if entry["request"]["id"] == request_id:
                entry["response"]["outcome_improved"] = improved
                entry["response"]["changed_orchestration"] = changed
                if self._store is not None:
                    self._store.put_item("advisor", request_id, entry)
                return

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)
