"""Top-level June orchestrator composing durable subsystems."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from june.advisor import AdvisorOrchestrator
from june.documents import DocumentStore
from june.dreaming import DreamingService
from june.goals import Goal, GoalStatus, GoalStore
from june.harness import MechaHarnessClient
from june.issues import Issue, IssueTracker
from june.knowledge import KnowledgeGraph
from june.outcomes import OutcomeLedger
from june.persist import JsonStore
from june.policy import PolicyStore
from june.runner import TaskOutcome, TaskRunner
from june.scheduler import Scheduler, ScheduleSpec, WakeReason
from june.templates import TemplateRegistry


class Orchestrator:
    """Application brain: goals, schedule, issues, policy, MechaHarness binding."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        store = JsonStore(data_dir) if data_dir is not None else None
        self.store = store
        self.goals = GoalStore(store)
        self.issues = IssueTracker(store)
        self.documents = DocumentStore(store)
        self.knowledge = KnowledgeGraph(store)
        self.templates = TemplateRegistry(store)
        self.scheduler = Scheduler(store)
        self.policy_store = PolicyStore(store)
        self.policy = self.policy_store.active
        self.advisor = AdvisorOrchestrator(store)
        self.dreaming = DreamingService(store)
        self.outcomes = OutcomeLedger(store)
        self.client = MechaHarnessClient()
        self.runner = TaskRunner(
            client=self.client,
            goals=self.goals,
            issues=self.issues,
            documents=self.documents,
            knowledge=self.knowledge,
            templates=self.templates,
            policy=self.policy,
            scheduler=self.scheduler,
            advisor=self.advisor,
            outcomes=self.outcomes,
        )

    def create_goal(self, title: str, completion_criteria: str, *, priority: int = 0) -> Goal:
        return self.goals.put(
            Goal(title=title, completion_criteria=completion_criteria, priority=priority)
        )

    def create_issue(self, title: str, *, goal_id: str | None = None) -> Issue:
        return self.issues.put(Issue(title=title, goal_id=goal_id))

    def wake_goal(
        self,
        goal_id: str,
        *,
        reason: WakeReason = WakeReason.MANUAL,
        payload: dict[str, Any] | None = None,
    ) -> TaskOutcome:
        self.scheduler.enqueue(reason=reason, goal_id=goal_id, payload=payload)
        runnable = self.scheduler.next()
        assert runnable is not None
        return self.runner.run(runnable)

    def schedule_goal(self, goal_id: str, *, interval_seconds: int = 3600) -> ScheduleSpec:
        return self.scheduler.add_schedule(
            ScheduleSpec(goal_id=goal_id, interval_seconds=interval_seconds)
        )

    def tick(self) -> list[TaskOutcome]:
        self.scheduler.tick()
        outcomes: list[TaskOutcome] = []
        while True:
            work = self.scheduler.next()
            if work is None:
                break
            outcomes.append(self.runner.run(work))
        return outcomes

    def dream(self) -> list[Any]:
        return self.dreaming.mine(
            issues=self.issues.list(),
            outcomes=[r.to_dict() for r in self.outcomes.list()],
        )

    def status(self) -> dict[str, Any]:
        return {
            "goals": len(self.goals.list()),
            "active_goals": len(self.goals.list(status=GoalStatus.ACTIVE)),
            "issues": len(self.issues.list()),
            "pending_work": len(self.scheduler.pending()),
            "templates": [t.name for t in self.templates.list()],
            "promotion_candidates": [t.name for t in self.templates.candidates_for_promotion()],
            "outcomes": self.outcomes.summary(),
            "policy_version": self.policy.version,
            "mechaharness": self.client.connect(),
        }
