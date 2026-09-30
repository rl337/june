"""Smoke tests for the orchestrator scaffold."""

from june.goals import Goal, GoalStatus, GoalStore
from june.harness import MechaHarnessClient
from june.issues import Issue, IssueStatus, IssueTracker
from june.policy import OrchestrationPolicy
from june.runner import TaskRunner
from june.scheduler import Scheduler, WakeReason


def test_goal_roundtrip() -> None:
    store = GoalStore()
    goal = store.put(Goal(title="Ship slice", completion_criteria="runner wired"))
    assert store.get(goal.id) is goal
    assert store.list(status=GoalStatus.ACTIVE) == [goal]


def test_scheduler_coalesce() -> None:
    sched = Scheduler()
    a = sched.enqueue(reason=WakeReason.GOAL, goal_id="g1")
    b = sched.enqueue(reason=WakeReason.GOAL, goal_id="g1")
    assert a.id == b.id
    assert len(sched.pending()) == 1
    assert a.coalesced_from


def test_task_runner_scaffold() -> None:
    sched = Scheduler()
    work = sched.enqueue(reason=WakeReason.MANUAL, goal_id="g1", payload={"task": "ping"})
    outcome = TaskRunner().run(work, template_name="direct")
    assert outcome.work_id == work.id
    assert outcome.result["template_name"] == "direct"
    assert outcome.result["goal_id"] == "g1"


def test_issue_transition() -> None:
    tracker = IssueTracker()
    issue = tracker.put(Issue(title="Wire client", goal_id="g1"))
    tracker.transition(issue.id, IssueStatus.IN_PROGRESS, note="started")
    assert issue.status is IssueStatus.IN_PROGRESS
    assert issue.history


def test_policy_high_risk() -> None:
    decision = OrchestrationPolicy().classify("external_side_effect")
    assert decision.require_approval
    assert decision.restricted_capabilities


def test_harness_bind() -> None:
    run = MechaHarnessClient().bind_template("verify_repair", bindings={"x": 1}, goal_id="g")
    assert run.template_name == "verify_repair"
    assert run.bindings["x"] == 1
