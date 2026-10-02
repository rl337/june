"""MechaHarness client adapters owned by June.

June selects, binds, and composes concrete ExecutionGraph realizations.
MechaHarness owns generic execution, linkage, envelopes, budgets, and checkpoints.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from june.budget import SubgraphBudget
from june.harness.visualization import (
    ExecutionFocus,
    execution_focus_from_events,
    render_focus_ascii,
)


@dataclass
class BoundRun:
    """A June-owned concrete realization ready for MechaHarness execution."""

    template_name: str
    bindings: dict[str, Any] = field(default_factory=dict)
    goal_id: str | None = None
    issue_id: str | None = None
    policy_version: str | None = None
    grants: list[str] = field(default_factory=list)
    context_refs: list[dict[str, Any]] = field(default_factory=list)
    node_kinds: list[str] = field(default_factory=lambda: ["june.task"])
    budget: SubgraphBudget = field(default_factory=SubgraphBudget)
    run_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class RunResult:
    status: str
    run_id: str
    template_name: str
    graph_checkpoint: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    verification: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class MechaHarnessClient:
    """June-side facade over MechaHarness graph primitives."""

    def __init__(
        self,
        *,
        on_graph_event: Callable[[Any], None] | None = None,
    ) -> None:
        self._available: bool | None = None
        self._graph_mod: Any | None = None
        self._on_graph_event = on_graph_event
        self._last_events: list[Any] = []

    def connect(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from mechaharness import graph as mh_graph

            self._graph_mod = mh_graph
            self._available = True
        except ImportError:
            self._graph_mod = None
            self._available = False
        return self._available

    def bind_template(
        self,
        template_name: str,
        *,
        bindings: dict[str, Any] | None = None,
        goal_id: str | None = None,
        issue_id: str | None = None,
        policy_version: str | None = None,
        grants: list[str] | None = None,
        context_refs: list[dict[str, Any]] | None = None,
        node_kinds: list[str] | None = None,
        budget: SubgraphBudget | None = None,
    ) -> BoundRun:
        return BoundRun(
            template_name=template_name,
            bindings=dict(bindings or {}),
            goal_id=goal_id,
            issue_id=issue_id,
            policy_version=policy_version,
            grants=list(grants or []),
            context_refs=list(context_refs or []),
            node_kinds=list(node_kinds or ["june.task"]),
            budget=budget if budget is not None else SubgraphBudget(),
        )

    def build_execution_graph(self, run: BoundRun) -> Any | None:
        if not self.connect() or self._graph_mod is None:
            return None
        graph = self._graph_mod.ExecutionGraph(
            id=run.run_id,
            goal=str(run.bindings.get("goal_title") or run.goal_id or run.template_name),
        )
        prev: str | None = None
        for idx, kind in enumerate(run.node_kinds):
            node = self._graph_mod.GraphNode(
                id=f"{run.run_id}:{idx}",
                kind=kind,
                goal=str(run.bindings.get("task") or run.template_name),
                payload={
                    "bindings": run.bindings,
                    "goal_id": run.goal_id,
                    "issue_id": run.issue_id,
                    "policy_version": run.policy_version,
                    "context_refs": run.context_refs,
                    "grants": run.grants,
                    "budget_policy": run.budget.to_dict(),
                },
            )
            graph.add_node(node)
            if prev is not None:
                graph.add_dependency(
                    self._graph_mod.DependencyEdge(
                        from_node=prev,
                        to_node=node.id,
                        types=["control"],
                        reason="june sequenced template realization",
                    )
                )
            prev = node.id
        return graph

    def resolve_linkage(self, run: BoundRun) -> dict[str, Any]:
        graph = self.build_execution_graph(run)
        if graph is None:
            return {
                "ok": True,
                "mode": "stub",
                "node_count": len(run.node_kinds),
                "warnings": ["mechaharness unavailable; linkage stubbed"],
                "budget_policy": run.budget.to_dict(),
            }
        ready = graph.ready_nodes()
        return {
            "ok": bool(ready) or len(graph.nodes) == 0,
            "mode": "mechaharness",
            "node_count": len(graph.nodes),
            "ready": [n.id for n in ready],
            "checkpoint": graph.checkpoint(),
            "budget_policy": run.budget.to_dict(),
        }

    def execution_focus(
        self,
        run: BoundRun,
        *,
        checkpoint: dict[str, Any] | None = None,
    ) -> ExecutionFocus | None:
        """Snapshot of the active node within the bound graph (requires events)."""
        if not self._last_events:
            cp = checkpoint or run.bindings.get("graph_checkpoint")
            if not isinstance(cp, dict):
                return None
            from june.harness.visualization import view_from_checkpoint

            return ExecutionFocus(
                root=view_from_checkpoint(cp, run_id=run.run_id),
                nested=None,
                active_run_id=run.run_id,
                active_node_id=None,
            )
        return execution_focus_from_events(
            self._last_events,
            root_run_id=run.run_id,
            root_checkpoint=checkpoint,
        )

    def render_execution_focus(
        self,
        run: BoundRun,
        *,
        checkpoint: dict[str, Any] | None = None,
        style: Literal["ascii", "mermaid"] = "ascii",
    ) -> str:
        focus = self.execution_focus(run, checkpoint=checkpoint)
        if focus is None:
            return ""
        if style == "ascii":
            return render_focus_ascii(focus)
        from june.harness.visualization import render_mermaid

        lines = [render_mermaid(focus.root)]
        if focus.nested is not None:
            lines.append(render_mermaid(focus.nested))
        return "\n\n".join(lines)

    def execute(
        self,
        run: BoundRun,
        *,
        driver: Literal["plan", "run"] = "plan",
    ) -> RunResult:
        """Realize a concrete graph with a required MechaHarness budget policy.

        June always attaches ``budget_policy`` for child runs. The control graph
        itself does not execute through GraphExecutor and stays uncapped.
        When MechaHarness is installed we build/checkpoint an ExecutionGraph
        carrying the policy for the host executor to enforce.

        ``driver="run"`` executes through MechaHarness :class:`GraphExecutor` and
        records lifecycle events for :meth:`execution_focus` / visualization.
        """
        if run.budget is None:  # pragma: no cover - dataclass default always set
            return RunResult(
                status="failed",
                run_id=run.run_id,
                template_name=run.template_name,
                error="missing_budget_policy",
                raw={"error": "child graph runs require BudgetPolicy"},
            )

        linkage = self.resolve_linkage(run)
        budget_info = run.budget.to_dict()
        # Validate against MH shape when available.
        if self.connect():
            try:
                run.budget.to_mechaharness()
            except Exception as exc:  # noqa: BLE001
                return RunResult(
                    status="failed",
                    run_id=run.run_id,
                    template_name=run.template_name,
                    error="invalid_budget_policy",
                    budget=budget_info,
                    raw={"error": str(exc)},
                )

        if not linkage.get("ok"):
            return RunResult(
                status="failed",
                run_id=run.run_id,
                template_name=run.template_name,
                error="linkage_failed",
                verification={"linkage": linkage},
                budget=budget_info,
                raw=linkage,
            )

        graph = self.build_execution_graph(run)
        if graph is None:
            return RunResult(
                status="scaffolded",
                run_id=run.run_id,
                template_name=run.template_name,
                graph_checkpoint={
                    "stub": True,
                    "bindings": run.bindings,
                    "context_refs": run.context_refs,
                    "grants": run.grants,
                    "node_kinds": run.node_kinds,
                    "budget_policy": budget_info,
                },
                verification={"linkage": linkage},
                budget=budget_info,
                raw={
                    "status": "not_implemented",
                    "mode": "stub",
                    "budget_policy": budget_info,
                },
            )

        if driver == "plan":
            checkpoint = graph.checkpoint()
            return RunResult(
                status="ready",
                run_id=run.run_id,
                template_name=run.template_name,
                graph_checkpoint=checkpoint,
                verification={"linkage": linkage},
                budget=budget_info,
                raw={
                    "status": "ready",
                    "mode": "execution_graph",
                    "budget_policy": budget_info,
                    "graph_executor_kwargs": {"budget_policy": budget_info},
                },
            )

        from june.harness.execution import run_graph

        def _remember(event: Any) -> None:
            self._last_events.append(event)
            if self._on_graph_event is not None:
                self._on_graph_event(event)

        self._last_events = []
        graph_result = run_graph(graph, run, on_event=_remember)
        checkpoint = graph_result.graph.checkpoint()
        focus = execution_focus_from_events(
            self._last_events,
            root_run_id=run.run_id,
            root_checkpoint=checkpoint,
        )
        return RunResult(
            status=graph_result.status,
            run_id=run.run_id,
            template_name=run.template_name,
            graph_checkpoint=checkpoint,
            verification={"linkage": linkage},
            budget={
                **budget_info,
                "spent": graph_result.budget_spent,
                "level": graph_result.budget_level,
            },
            raw={
                "status": graph_result.status,
                "mode": "graph_executor",
                "budget_policy": budget_info,
                "execution_focus": focus.to_dict(),
                "error": graph_result.error,
            },
        )
