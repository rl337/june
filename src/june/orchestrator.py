"""Top-level June orchestrator composing durable subsystems."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from june.advisor import AdvisorOrchestrator
from june.channels import ChannelMessage, ChannelReply, ContentPart
from june.chat import CHAT_TEMPLATE
from june.control import ControlGraph, WorkQueue
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
from june.scheduler import RunnableWork, Scheduler, ScheduleSpec, WakeReason
from june.templates import GraphTemplateSpec, SoftPoint, TemplateRegistry, TemplateStatus

if TYPE_CHECKING:
    from june.chat import ChatGraphRunner
    from june.config import JuneSettings
    from june.providers.junespark import JunesparkProvider
    from june.tools import ToolRegistry


class Orchestrator:
    """Application brain: goals, schedule, issues, policy, MechaHarness binding."""

    def __init__(
        self,
        data_dir: Path | str | None = None,
        *,
        settings: JuneSettings | None = None,
    ) -> None:
        store = JsonStore(data_dir) if data_dir is not None else None
        self.store = store
        self.settings = settings
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
        self.provider: JunesparkProvider | None = None
        self.tools: ToolRegistry | None = None
        self.chat_runner: ChatGraphRunner | None = None
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
            chat_runner=None,
        )
        self.control = ControlGraph(
            queue=WorkQueue(store),
            store=store,
            on_cron_tick=self._on_cron_tick,
            on_execute_work=self._on_execute_work,
        )
        self._ensure_control_template()

    def attach_chat(
        self,
        *,
        provider: JunesparkProvider,
        tools: ToolRegistry,
        chat_runner: ChatGraphRunner,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.chat_runner = chat_runner
        self.runner.chat_runner = chat_runner

    def handle_chat(self, message: ChannelMessage) -> ChannelReply:
        """Process a channel message through the incubating june.chat subgraph."""
        work = RunnableWork(
            goal_id=None,
            issue_id=None,
            reason=WakeReason.EVENT,
            payload={
                "action": "chat",
                "template": CHAT_TEMPLATE,
                "channel_message": message.to_dict(),
                "task": message.text() or "chat",
            },
        )
        outcome = self.runner.run(work)
        reply_raw = outcome.result.get("reply") or {}
        if isinstance(reply_raw, dict) and reply_raw.get("parts") is not None:
            return ChannelReply(
                parts=[ContentPart.from_dict(p) for p in reply_raw.get("parts") or []],
                run_id=outcome.run_id or reply_raw.get("run_id"),
                model=reply_raw.get("model"),
                tool_trace=list(reply_raw.get("tool_trace") or []),
                notes=list(reply_raw.get("notes") or []),
                raw={"outcome_status": outcome.status, **dict(reply_raw.get("raw") or {})},
            )
        text = str(reply_raw.get("text") if isinstance(reply_raw, dict) else reply_raw or "")
        return ChannelReply(
            parts=[ContentPart.text_part(text or f"chat status={outcome.status}")],
            run_id=outcome.run_id,
            model=None,
            notes=[f"decision={outcome.decision}"],
        )

    def _ensure_control_template(self) -> None:
        if self.templates.get(ControlGraph.GRAPH_NAME) is not None:
            return
        self.templates.register(
            GraphTemplateSpec(
                name=ControlGraph.GRAPH_NAME,
                description=(
                    "June control loop: cron tick, channel polls, and due work "
                    "with a max 100ms tick"
                ),
                status=TemplateStatus.INCUBATING,
                node_kinds=list(ControlGraph.NODE_KINDS),
                soft_points=[
                    asdict(SoftPoint("pollers", "Telegram/Discord/webapp adapters")),
                    asdict(SoftPoint("cron", "June ScheduleSpec materialization")),
                    asdict(SoftPoint("execute_work", "TaskRunner / MechaHarness binding")),
                ],
                provenance={"owns": "june", "entry": "june run"},
            )
        )

    def _enqueue_control_work(self, work: RunnableWork) -> None:
        self.control.schedule_work(
            {
                "goal_id": work.goal_id,
                "issue_id": work.issue_id,
                "reason": work.reason.value,
                "payload": work.payload,
                "work_id": work.id,
            }
        )

    def _on_cron_tick(self) -> list[dict[str, Any]]:
        woken = self.scheduler.tick()
        events: list[dict[str, Any]] = []
        for work in woken:
            self._enqueue_control_work(work)
            events.append({"type": "schedule_wake", "work_id": work.id})
        while True:
            work = self.scheduler.next()
            if work is None:
                break
            self._enqueue_control_work(work)
            events.append({"type": "runnable", "work_id": work.id})
        return events

    def _on_execute_work(self, payload: dict[str, Any]) -> dict[str, Any]:
        work = RunnableWork(
            id=str(payload.get("work_id") or ""),
            goal_id=payload.get("goal_id"),
            issue_id=payload.get("issue_id"),
            reason=WakeReason(payload.get("reason", WakeReason.MANUAL.value)),
            payload=dict(payload.get("payload") or payload),
        )
        if not work.id:
            work.id = str(uuid4())
        outcome = self.runner.run(work)
        return {
            "work_id": outcome.work_id,
            "status": outcome.status,
            "decision": outcome.decision,
            "run_id": outcome.run_id,
        }

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
        run_at: datetime | None = None,
    ) -> TaskOutcome:
        """Enqueue goal work onto the control queue and execute it synchronously.

        Long-lived operation uses `june run`, which drains the same queue on the
        ≤100ms tick. This path is for interactive CLI wakes.
        """
        work = self.scheduler.enqueue(reason=reason, goal_id=goal_id, payload=payload)
        self.control.schedule_work(
            {
                "goal_id": work.goal_id,
                "issue_id": work.issue_id,
                "reason": work.reason.value,
                "payload": work.payload,
                "work_id": work.id,
            },
            run_at=run_at or datetime.now(timezone.utc),
        )
        return self.runner.run(work)

    def schedule_goal(self, goal_id: str, *, interval_seconds: int = 3600) -> ScheduleSpec:
        return self.scheduler.add_schedule(
            ScheduleSpec(goal_id=goal_id, interval_seconds=interval_seconds)
        )

    def tick(self) -> list[TaskOutcome]:
        """One control-graph step (cron/polls/due work), returning execute outcomes."""
        step = self.control.step()
        return [
            TaskOutcome(
                work_id=str(raw.get("work_id", "")),
                status=str(raw.get("status", "unknown")),
                result=raw,
                run_id=raw.get("run_id"),
                decision=str(raw.get("decision", "complete")),
            )
            for raw in step.work_outcomes
        ]

    def run(
        self,
        *,
        max_steps: int | None = None,
        should_stop: Any = None,
    ) -> list[Any]:
        """Single entrypoint: run the June control graph loop."""
        return self.control.run(max_steps=max_steps, should_stop=should_stop)

    def dream(self) -> list[Any]:
        return self.dreaming.mine(
            issues=self.issues.list(),
            outcomes=[r.to_dict() for r in self.outcomes.list()],
        )

    def status(self) -> dict[str, Any]:
        junespark: dict[str, Any] = {}
        if self.settings is not None:
            junespark = {
                "base_url": self.settings.junespark.base_url,
                "model": self.settings.junespark.model,
                "configured": bool(self.settings.junespark.base_url),
            }
        return {
            "goals": len(self.goals.list()),
            "active_goals": len(self.goals.list(status=GoalStatus.ACTIVE)),
            "issues": len(self.issues.list()),
            "pending_work": len(self.scheduler.pending()),
            "control": self.control.describe(),
            "templates": [spec.name for spec in self.templates.list()],
            "promotion_candidates": [
                spec.name for spec in self.templates.candidates_for_promotion()
            ],
            "outcomes": self.outcomes.summary(),
            "policy_version": self.policy.version,
            "mechaharness": self.client.connect(),
            "junespark": junespark,
        }
