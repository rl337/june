"""Issue tracker — durable work ledger; MechaHarness runs execute work, not own it."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


class IssueStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class Issue:
    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: IssueStatus = IssueStatus.OPEN
    priority: int = 0
    goal_id: str | None = None
    parent_id: str | None = None
    owner: str | None = None
    blockers: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    knowledge_ids: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    failure_class: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Issue:
        payload = dict(data)
        payload["status"] = IssueStatus(payload.get("status", IssueStatus.OPEN.value))
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


class IssueTracker:
    def __init__(self, store: JsonStore | None = None) -> None:
        self._issues: dict[str, Issue] = {}
        self._store = store

    def put(self, issue: Issue) -> Issue:
        issue.updated_at = datetime.now(timezone.utc).isoformat()
        self._issues[issue.id] = issue
        if self._store is not None:
            self._store.put_item("issues", issue.id, issue.to_dict())
        return issue

    def get(self, issue_id: str) -> Issue | None:
        if issue_id in self._issues:
            return self._issues[issue_id]
        if self._store is None:
            return None
        raw = self._store.get_item("issues", issue_id)
        if raw is None:
            return None
        issue = Issue.from_dict(raw)
        self._issues[issue.id] = issue
        return issue

    def transition(
        self,
        issue_id: str,
        status: IssueStatus,
        *,
        note: str = "",
        owner: str | None = None,
    ) -> Issue | None:
        issue = self.get(issue_id)
        if issue is None:
            return None
        issue.history.append(
            {
                "from": issue.status.value,
                "to": status.value,
                "note": note,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        issue.status = status
        if owner is not None:
            issue.owner = owner
        return self.put(issue)

    def link_run(self, issue_id: str, run_id: str) -> Issue | None:
        issue = self.get(issue_id)
        if issue is None:
            return None
        if run_id not in issue.run_ids:
            issue.run_ids.append(run_id)
        return self.put(issue)

    def record_failure(
        self,
        *,
        title: str,
        failure_class: str,
        goal_id: str | None = None,
        run_id: str | None = None,
        note: str = "",
    ) -> Issue:
        related = [
            i
            for i in self.list()
            if i.failure_class == failure_class and i.status is not IssueStatus.DONE
        ]
        if related:
            issue = related[0]
            issue.history.append(
                {
                    "from": issue.status.value,
                    "to": issue.status.value,
                    "note": f"linked failure: {note}",
                    "at": datetime.now(timezone.utc).isoformat(),
                    "run_id": run_id,
                }
            )
            if run_id:
                issue.run_ids.append(run_id)
            return self.put(issue)
        issue = Issue(
            title=title,
            goal_id=goal_id,
            failure_class=failure_class,
            run_ids=[run_id] if run_id else [],
            provenance={"created_from": "run_failure", "note": note},
        )
        return self.put(issue)

    def list(self, *, status: IssueStatus | None = None) -> list[Issue]:
        if self._store is not None:
            for raw in self._store.list_items("issues"):
                issue = Issue.from_dict(raw)
                self._issues.setdefault(issue.id, issue)
        issues = list(self._issues.values())
        if status is not None:
            issues = [i for i in issues if i.status is status]
        return sorted(issues, key=lambda i: (-i.priority, i.created_at))

    def by_failure_class(self, failure_class: str) -> list[Issue]:
        return [i for i in self.list() if i.failure_class == failure_class]
