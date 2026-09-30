"""Task runner — June orchestration around MechaHarness execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from june.advisor import AdvisorOrchestrator, AdvisorRequest
from june.documents import DocumentStore
from june.goals import GoalStatus, GoalStore
from june.harness import BoundRun, MechaHarnessClient, RunResult
from june.issues import IssueStatus, IssueTracker
from june.knowledge import KnowledgeGraph
from june.outcomes import OutcomeLedger, OutcomeRecord
from june.policy import OrchestrationPolicy, PolicyDecision
from june.scheduler import RunnableWork, Scheduler
from june.templates import TemplateRegistry


@dataclass
class TaskOutcome:
    work_id: str
    status: str
    result: dict[str, Any]
    run_id: str | None = None
    decision: str = "complete"
    policy: dict[str, Any] = field(default_factory=dict)


class TaskRunner:
    """Load state → select/bind → linkage → execute → write back → decide."""

    def __init__(
        self,
        *,
        client: MechaHarnessClient | None = None,
        goals: GoalStore | None = None,
        issues: IssueTracker | None = None,
        documents: DocumentStore | None = None,
        knowledge: KnowledgeGraph | None = None,
        templates: TemplateRegistry | None = None,
        policy: OrchestrationPolicy | None = None,
        scheduler: Scheduler | None = None,
        advisor: AdvisorOrchestrator | None = None,
        outcomes: OutcomeLedger | None = None,
        approval_callback: Callable[[PolicyDecision, RunnableWork], bool] | None = None,
    ) -> None:
        self.client = client or MechaHarnessClient()
        self.goals = goals or GoalStore()
        self.issues = issues or IssueTracker()
        self.documents = documents or DocumentStore()
        self.knowledge = knowledge or KnowledgeGraph()
        self.templates = templates or TemplateRegistry()
        self.policy = policy or OrchestrationPolicy()
        self.scheduler = scheduler or Scheduler()
        self.advisor = advisor or AdvisorOrchestrator()
        self.outcomes = outcomes or OutcomeLedger()
        self.approval_callback = approval_callback

    def run(self, work: RunnableWork, *, template_name: str | None = None) -> TaskOutcome:
        started = datetime.now(timezone.utc)
        goal = self.goals.get(work.goal_id) if work.goal_id else None
        issue = self.issues.get(work.issue_id) if work.issue_id else None

        action = str(work.payload.get("action", "task"))
        decision = self.policy.classify(action)
        if decision.require_approval:
            approved = True
            if self.approval_callback is not None:
                approved = self.approval_callback(decision, work)
            self.policy.record_metric(
                "approval_request",
                approved=approved,
                action=action,
                work_id=work.id,
            )
            if not approved:
                self.policy.record_metric("denied_action", action=action, work_id=work.id)
                return TaskOutcome(
                    work_id=work.id,
                    status="denied",
                    result={"reason": decision.reason},
                    decision="deny",
                    policy={
                        "require_approval": True,
                        "consequence": decision.consequence.value,
                        "reason": decision.reason,
                    },
                )

        if issue is not None:
            self.issues.transition(issue.id, IssueStatus.IN_PROGRESS, note="task_runner")

        selected = template_name or str(work.payload.get("template", "direct"))
        spec = self.templates.record_use(selected) or self.templates.get("direct")
        assert spec is not None

        query = str(work.payload.get("query", ""))
        context_refs = list(self.documents.as_context_items(query, limit=3))
        subject = goal.id if goal is not None else None
        context_refs.extend(self.knowledge.scoped_context(subject=subject))

        bound = self.client.bind_template(
            spec.mechaharness_template or spec.name,
            bindings={
                "wake_reason": work.reason.value,
                "goal_title": None if goal is None else goal.title,
                "task": work.payload.get("task") or (None if goal is None else goal.title),
                **work.payload,
            },
            goal_id=work.goal_id,
            issue_id=work.issue_id,
            policy_version=self.policy.version,
            grants=decision.grants,
            context_refs=context_refs,
            node_kinds=spec.node_kinds,
        )

        if self.advisor.should_consult(
            action if action in self.advisor.HIGH_VALUE_TRIGGERS else "",
            failure_count=work.attempt,
        ) or work.attempt >= 2:
            advice = self.advisor.consult(
                AdvisorRequest(
                    trigger="repeated_failure" if work.attempt >= 2 else action,
                    question=f"Proceed with template {spec.name}?",
                    evidence_refs=context_refs,
                    goal_id=work.goal_id,
                    issue_id=work.issue_id,
                )
            )
            bound.bindings["advisor_guidance"] = advice.guidance

        run_result = self.client.execute(bound)
        self._write_back(work, bound, run_result, goal_id=work.goal_id, issue_id=work.issue_id)

        next_decision = self._decide(work, run_result)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        graph_ok = run_result.status in {"ready", "ok", "scaffolded"}
        goal_done = False
        if goal is not None and next_decision == "complete" and graph_ok:
            # Product success is independent of raw graph readiness; require explicit criteria flag.
            goal_done = bool(work.payload.get("mark_goal_complete"))
            if goal_done:
                self.goals.transition(goal.id, GoalStatus.COMPLETED, reason="task_runner_complete")
            if issue is not None and goal_done:
                self.issues.transition(issue.id, IssueStatus.DONE, note="goal_complete")

        self.outcomes.record(
            OutcomeRecord(
                goal_id=work.goal_id,
                issue_id=work.issue_id,
                run_ids=[run_result.run_id],
                goal_completed=goal_done,
                graph_succeeded=graph_ok,
                orchestration_success=goal_done or (graph_ok and next_decision == "complete"),
                elapsed_seconds=elapsed,
                retries=work.attempt,
                approval_burden=1 if decision.require_approval else 0,
                policy_version=self.policy.version,
                harness_version=str(run_result.raw.get("mode")),
                notes=run_result.error or "",
            )
        )

        return TaskOutcome(
            work_id=work.id,
            status=run_result.status,
            result={
                "run": run_result.raw,
                "verification": run_result.verification,
                "checkpoint": run_result.graph_checkpoint,
                "template": spec.name,
            },
            run_id=run_result.run_id,
            decision=next_decision,
            policy={
                "require_approval": decision.require_approval,
                "consequence": decision.consequence.value,
                "grants": decision.grants,
                "reason": decision.reason,
            },
        )

    def _write_back(
        self,
        work: RunnableWork,
        bound: BoundRun,
        run_result: RunResult,
        *,
        goal_id: str | None,
        issue_id: str | None,
    ) -> None:
        if goal_id:
            self.goals.link_run(goal_id, run_result.run_id)
        if issue_id:
            self.issues.link_run(issue_id, run_result.run_id)
        if run_result.status == "failed":
            self.issues.record_failure(
                title=f"Run failed for work {work.id}",
                failure_class=str(run_result.error or "run_failed"),
                goal_id=goal_id,
                run_id=run_result.run_id,
                note=str(run_result.raw),
            )

    def _decide(self, work: RunnableWork, run_result: RunResult) -> str:
        if run_result.status in {"denied"}:
            return "deny"
        if run_result.status == "failed":
            retried = self.scheduler.retry(work, backoff_seconds=1)
            return "retry" if retried is not None else "escalate"
        if run_result.status in {"ready", "ok", "scaffolded"}:
            return "complete"
        return "reschedule"

    def realize(self, run: BoundRun) -> RunResult:
        return self.client.execute(run)
