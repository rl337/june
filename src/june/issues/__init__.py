"""Issue tracker — durable work ledger; MechaHarness runs execute work, not own it."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


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
    blockers: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class IssueTracker:
    def __init__(self) -> None:
        self._issues: dict[str, Issue] = {}

    def put(self, issue: Issue) -> Issue:
        issue.updated_at = datetime.now(timezone.utc)
        self._issues[issue.id] = issue
        return issue

    def get(self, issue_id: str) -> Issue | None:
        return self._issues.get(issue_id)

    def transition(self, issue_id: str, status: IssueStatus, *, note: str = "") -> Issue | None:
        issue = self._issues.get(issue_id)
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
        issue.updated_at = datetime.now(timezone.utc)
        return issue

    def list(self, *, status: IssueStatus | None = None) -> list[Issue]:
        issues = list(self._issues.values())
        if status is not None:
            issues = [i for i in issues if i.status is status]
        return sorted(issues, key=lambda i: (-i.priority, i.created_at))
