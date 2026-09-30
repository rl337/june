"""Tests covering orchestration requirements scaffold."""

from __future__ import annotations

from pathlib import Path

from june.advisor import AdvisorOrchestrator, AdvisorRequest
from june.documents import DocumentRef
from june.dreaming import DreamingService
from june.goals import Goal, GoalStatus, GoalStore
from june.harness import MechaHarnessClient
from june.issues import IssueStatus, IssueTracker
from june.knowledge import FactKind, KnowledgeFact
from june.orchestrator import Orchestrator
from june.outcomes import OutcomeLedger, OutcomeRecord
from june.persist import JsonStore
from june.policy import OrchestrationPolicy
from june.runner import TaskRunner
from june.scheduler import Scheduler, ScheduleSpec, WakeReason
from june.templates import TemplateRegistry, TemplateStatus


def test_goal_roundtrip_and_steering(tmp_path: Path) -> None:
    store = GoalStore(JsonStore(tmp_path))
    goal = store.put(Goal(title="Ship slice", completion_criteria="runner wired"))
    store.steer(goal.id, "focus on harness binding")
    reloaded = GoalStore(JsonStore(tmp_path)).get(goal.id)
    assert reloaded is not None
    assert reloaded.transitions
    assert "steering:" in reloaded.transitions[-1]["reason"]


def test_scheduler_coalesce_retry_and_schedule(tmp_path: Path) -> None:
    sched = Scheduler(JsonStore(tmp_path))
    a = sched.enqueue(reason=WakeReason.GOAL, goal_id="g1")
    b = sched.enqueue(reason=WakeReason.GOAL, goal_id="g1")
    assert a.id == b.id
    assert a.coalesced_from
    work = sched.next()
    assert work is not None
    retried = sched.retry(work, backoff_seconds=0)
    assert retried is not None
    assert retried.attempt == 1
    sched.add_schedule(
        ScheduleSpec(
            goal_id="g1",
            interval_seconds=1,
            next_run_at="2000-01-01T00:00:00+00:00",
        )
    )
    woken = sched.tick()
    assert woken


def test_task_runner_lifecycle(tmp_path: Path) -> None:
    orch = Orchestrator(tmp_path)
    goal = orch.create_goal("Ping", "done when marked")
    issue = orch.create_issue("Do ping", goal_id=goal.id)
    orch.documents.put(DocumentRef(title="notes", summary="context"), payload="hello")
    fact = orch.knowledge.propose(
        KnowledgeFact(subject=goal.id, predicate="needs", object="harness", kind=FactKind.STABLE)
    )
    orch.knowledge.promote(fact.id)
    orch.scheduler.enqueue(
        reason=WakeReason.MANUAL,
        goal_id=goal.id,
        issue_id=issue.id,
        payload={"task": "ping", "mark_goal_complete": True, "query": "notes"},
    )
    runnable = orch.scheduler.next()
    assert runnable is not None
    outcome = orch.runner.run(runnable)
    assert outcome.decision == "complete"
    assert outcome.run_id
    assert orch.goals.get(goal.id).status is GoalStatus.COMPLETED
    assert orch.issues.get(issue.id).status is IssueStatus.DONE
    assert orch.outcomes.summary()["count"] == 1


def test_policy_high_risk_and_metrics() -> None:
    policy = OrchestrationPolicy()
    decision = policy.classify("external_side_effect")
    assert decision.require_approval
    assert "network_write" in decision.restricted_capabilities
    policy.record_metric("approval_request", approved=False)
    assert policy.metrics
    assert policy.retire_rule("external_side_effect")


def test_template_incubation_promotion() -> None:
    registry = TemplateRegistry()
    for _ in range(3):
        registry.record_use("direct")
    spec = registry.get("direct")
    assert spec is not None
    assert spec.status is TemplateStatus.CANDIDATE
    registry.mark_promoted("direct", mechaharness_template="mh.direct")
    assert registry.get("direct").status is TemplateStatus.PROMOTED


def test_advisor_and_dreaming(tmp_path: Path) -> None:
    advisor = AdvisorOrchestrator(JsonStore(tmp_path))
    assert advisor.should_consult("goal_mutation")
    response = advisor.consult(
        AdvisorRequest(trigger="goal_mutation", question="mutate?", evidence_refs=[])
    )
    advisor.record_outcome(response.request_id, improved=True, changed=True)
    tracker = IssueTracker()
    tracker.record_failure(title="a", failure_class="boom", note="1")
    tracker.record_failure(title="b", failure_class="boom", note="2")
    dreams = DreamingService(JsonStore(tmp_path)).mine(
        issues=tracker.list(),
        outcomes=[{"retries": 4}],
    )
    assert dreams
    assert any(d.source_failure_class == "boom" for d in dreams)


def test_outcome_orchestration_failure_on_wrong_goal_advance() -> None:
    ledger = OutcomeLedger()
    rec = ledger.record(
        OutcomeRecord(
            goal_id="g",
            issue_id=None,
            run_ids=["r1"],
            goal_completed=False,
            graph_succeeded=True,
            orchestration_success=True,
        )
    )
    assert rec.orchestration_success is False
    assert "graph_ok_but_goal_not_advanced" in rec.notes


def test_harness_bind_and_stub_execute() -> None:
    client = MechaHarnessClient()
    run = client.bind_template("direct", bindings={"x": 1}, goal_id="g")
    result = client.execute(run)
    assert result.template_name == "direct"
    assert result.status in {"scaffolded", "ready", "failed"}


def test_denied_action_path() -> None:
    runner = TaskRunner(
        policy=OrchestrationPolicy(),
        approval_callback=lambda decision, work: False,
    )
    sched = Scheduler()
    work = sched.enqueue(
        reason=WakeReason.MANUAL,
        goal_id="g1",
        payload={"action": "external_side_effect"},
    )
    outcome = runner.run(work)
    assert outcome.status == "denied"
    assert outcome.decision == "deny"


def test_subgraph_budget_attached_and_scaled_by_consequence() -> None:
    from june.budget import SubgraphBudget, budget_for_decision
    from june.policy import Consequence, PolicyDecision

    low = budget_for_decision(
        PolicyDecision(
            allow=True,
            require_approval=False,
            consequence=Consequence.LOW,
            reason="test",
        )
    )
    assert low.hard_limit == 32.0
    critical = budget_for_decision(
        PolicyDecision(
            allow=True,
            require_approval=True,
            consequence=Consequence.CRITICAL,
            reason="test",
        )
    )
    assert critical.hard_limit == 16.0
    assert SubgraphBudget.unlimited().hard_limit is None

    runner = TaskRunner()
    sched = Scheduler()
    work = sched.enqueue(
        reason=WakeReason.MANUAL,
        goal_id="g1",
        payload={"task": "budgeted", "budget_policy": {"soft_limit": 1, "hard_limit": 2}},
    )
    outcome = runner.run(work)
    assert outcome.policy["budget_policy"]["hard_limit"] == 2
    assert outcome.result["budget_policy"]["soft_limit"] == 1


def test_hard_budget_exceeded_escalates() -> None:
    from june.budget import SubgraphBudget
    from june.harness import RunResult
    from june.runner import TaskRunner
    from june.scheduler import RunnableWork, WakeReason

    runner = TaskRunner()
    work = RunnableWork(goal_id="g", issue_id=None, reason=WakeReason.MANUAL)
    decision = runner._decide(
        work,
        RunResult(
            status="hard_budget_exceeded",
            run_id="r1",
            template_name="direct",
            budget=SubgraphBudget(soft_limit=1, hard_limit=2).to_dict(),
        ),
    )
    assert decision == "escalate"


def test_work_queue_sleep_caps_at_100ms_or_next_job() -> None:
    from datetime import datetime, timedelta, timezone

    from june.control import ControlJobKind, WorkQueue

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    queue = WorkQueue()
    assert queue.sleep_seconds(now) == 0.1

    queue.schedule(
        ControlJobKind.EXECUTE_WORK,
        run_at=now + timedelta(milliseconds=30),
        payload={"task": "soon"},
    )
    assert abs(queue.sleep_seconds(now) - 0.03) < 1e-6

    queue.schedule(
        ControlJobKind.EXECUTE_WORK,
        run_at=now - timedelta(milliseconds=1),
        payload={"task": "due"},
    )
    assert queue.sleep_seconds(now) == 0.0


def test_control_graph_tick_and_early_wake() -> None:
    from datetime import datetime, timedelta, timezone

    from june.control import ControlGraph, ControlJobKind, WorkQueue

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    slept: list[float] = []

    def clock() -> datetime:
        return now["t"]

    def sleeper(seconds: float) -> None:
        slept.append(seconds)
        now["t"] = now["t"] + timedelta(seconds=seconds)

    executed: list[dict] = []
    graph = ControlGraph(
        queue=WorkQueue(),
        max_tick_seconds=0.1,
        poll_interval_seconds=0.1,
        clock=clock,
        sleeper=sleeper,
        on_execute_work=lambda payload: executed.append(payload) or {"ok": True},
    )
    graph.bootstrap()
    # Next pollers are due immediately at bootstrap time → first step sleeps 0.
    step1 = graph.step()
    assert step1.slept_seconds == 0.0
    assert ControlJobKind.CRON_TICK.value in step1.jobs_run
    assert ControlJobKind.POLL_TELEGRAM.value in step1.jobs_run

    # Schedule work sooner than the 100ms poll cadence.
    graph.schedule_work({"task": "urgent"}, run_at=now["t"] + timedelta(milliseconds=25))
    step2 = graph.step()
    assert abs(step2.slept_seconds - 0.025) < 1e-6
    assert executed
    assert executed[-1]["task"] == "urgent"


def test_orchestrator_run_registers_control_template(tmp_path: Path) -> None:
    orch = Orchestrator(tmp_path)
    assert orch.templates.get("june.control") is not None
    results = orch.run(max_steps=1)
    assert len(results) == 1
    assert "control.cron_tick" in results[0].jobs_run
