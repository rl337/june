"""Sleep/dreaming — June self-improvement workflow over durable traces."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    EVALUATING = "evaluating"
    PROMOTED = "promoted"
    RETIRED = "retired"
    CROSS_REPO = "cross_repo"


@dataclass
class DreamProposal:
    hypothesis: str
    source_failure_class: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    status: ProposalStatus = ProposalStatus.PROPOSED
    kind: str = "orchestration_policy"
    evidence: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DreamProposal:
        payload = dict(data)
        payload["status"] = ProposalStatus(payload.get("status", ProposalStatus.PROPOSED.value))
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


class DreamingService:
    def __init__(self, store: JsonStore | None = None) -> None:
        self._store = store
        self._proposals: dict[str, DreamProposal] = {}

    def mine(
        self,
        *,
        issues: list[Any],
        outcomes: list[dict[str, Any]],
        knowledge_changes: list[dict[str, Any]] | None = None,
    ) -> list[DreamProposal]:
        failure_classes: Counter[str] = Counter()
        for issue in issues:
            failure_class = getattr(issue, "failure_class", None)
            if isinstance(issue, dict):
                failure_class = issue.get("failure_class")
            if not failure_class:
                continue
            history = getattr(issue, "history", None)
            if history is None and isinstance(issue, dict):
                history = issue.get("history") or []
            # Initial failure plus each linked recurrence in history.
            failure_classes[str(failure_class)] += max(1, len(history or []) + 1)
        proposals: list[DreamProposal] = []
        for failure_class, count in failure_classes.items():
            if not failure_class or count < 2:
                continue
            proposal = DreamProposal(
                hypothesis=f"Add orchestration guard for recurring failure '{failure_class}'",
                source_failure_class=str(failure_class),
                kind="orchestration_policy",
                evidence=[{"failure_class": failure_class, "count": count}],
                provenance={
                    "observed_failure": failure_class,
                    "path": "failure→hypothesis→experiment→promote/retire",
                },
            )
            proposals.append(self.save(proposal))

        retries = sum(int(o.get("retries", 0)) for o in outcomes)
        if retries >= 3:
            proposals.append(
                self.save(
                    DreamProposal(
                        hypothesis="Reduce retry churn via tighter template selection",
                        kind="template_composition",
                        evidence=[{"retries": retries}],
                    )
                )
            )

        if knowledge_changes:
            proposals.append(
                self.save(
                    DreamProposal(
                        hypothesis="Tighten knowledge promotion thresholds",
                        kind="retrieval_rule",
                        evidence=list(knowledge_changes[:5]),
                    )
                )
            )
        return proposals

    def save(self, proposal: DreamProposal) -> DreamProposal:
        self._proposals[proposal.id] = proposal
        if self._store is not None:
            self._store.put_item("dreams", proposal.id, proposal.to_dict())
        return proposal

    def evaluate(self, proposal_id: str, *, passed: bool) -> DreamProposal | None:
        proposal = self._proposals.get(proposal_id)
        if proposal is None and self._store is not None:
            raw = self._store.get_item("dreams", proposal_id)
            if raw:
                proposal = DreamProposal.from_dict(raw)
        if proposal is None:
            return None
        proposal.status = ProposalStatus.PROMOTED if passed else ProposalStatus.RETIRED
        proposal.provenance["evaluated_at"] = datetime.now(timezone.utc).isoformat()
        proposal.provenance["passed"] = passed
        return self.save(proposal)

    def mark_cross_repo(self, proposal_id: str) -> DreamProposal | None:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return None
        proposal.status = ProposalStatus.CROSS_REPO
        proposal.kind = "mechaharness_improvement"
        return self.save(proposal)

    def list(self) -> list[DreamProposal]:
        if self._store is not None:
            for raw in self._store.list_items("dreams"):
                proposal = DreamProposal.from_dict(raw)
                self._proposals.setdefault(proposal.id, proposal)
        return list(self._proposals.values())
