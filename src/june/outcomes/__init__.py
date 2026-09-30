"""June-level outcome measurement across MechaHarness runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


@dataclass
class OutcomeRecord:
    goal_id: str | None
    issue_id: str | None
    run_ids: list[str]
    goal_completed: bool
    graph_succeeded: bool
    orchestration_success: bool
    id: str = field(default_factory=lambda: str(uuid4()))
    correctness: float | None = None
    elapsed_seconds: float = 0.0
    retries: int = 0
    coordination_churn: int = 0
    user_interruptions: int = 0
    approval_burden: int = 0
    compute_units: float = 0.0
    policy_version: str | None = None
    harness_version: str | None = None
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutcomeRecord:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class OutcomeLedger:
    def __init__(self, store: JsonStore | None = None) -> None:
        self._store = store
        self._records: dict[str, OutcomeRecord] = {}

    def record(self, outcome: OutcomeRecord) -> OutcomeRecord:
        # Successful graph that advances wrong goal state => orchestration failure
        if outcome.graph_succeeded and not outcome.goal_completed:
            outcome.orchestration_success = False
            if not outcome.notes:
                outcome.notes = "graph_ok_but_goal_not_advanced"
        self._records[outcome.id] = outcome
        if self._store is not None:
            self._store.put_item("outcomes", outcome.id, outcome.to_dict())
        return outcome

    def for_goal(self, goal_id: str) -> list[OutcomeRecord]:
        return [r for r in self.list() if r.goal_id == goal_id]

    def list(self) -> list[OutcomeRecord]:
        if self._store is not None:
            for raw in self._store.list_items("outcomes"):
                rec = OutcomeRecord.from_dict(raw)
                self._records.setdefault(rec.id, rec)
        return list(self._records.values())

    def summary(self) -> dict[str, Any]:
        rows = self.list()
        if not rows:
            return {"count": 0}
        return {
            "count": len(rows),
            "orchestration_success_rate": (
                sum(1 for r in rows if r.orchestration_success) / len(rows)
            ),
            "goal_completion_rate": (
                sum(1 for r in rows if r.goal_completed) / len(rows)
            ),
            "avg_retries": sum(r.retries for r in rows) / len(rows),
            "avg_approval_burden": sum(r.approval_burden for r in rows) / len(rows),
            "avg_elapsed_seconds": sum(r.elapsed_seconds for r in rows) / len(rows),
        }
