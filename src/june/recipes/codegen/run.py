"""Run incubating codegen recipes through MechaHarness host_kit."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from june.recipes.codegen.completers import CodegenCompleter
from june.recipes.codegen.graph import (
    ONESHOT_NODE_ORDER,
    PACKAGE_NODE_ORDER,
    REFINE_NODE_ORDER,
    RecipeKind,
    bound_run_for_codegen,
    build_codegen_graph,
    build_package_graph,
    build_refine_graph,
)
from june.recipes.codegen.problem import CodingProblem
from june.recipes.codegen.runners import make_codegen_runners

# Back-compat alias used by existing harness assertions.
EXPECTED_NODE_ORDER = ONESHOT_NODE_ORDER

# Offline fixed completer: generate=1.0 + execute=0.5
EXPECTED_OFFLINE_BUDGET_SPENT = 1.5
# Refine with both passes: 1.0+0.5 + repair 1.0+0.5
EXPECTED_REFINE_BUDGET_SPENT = 3.0
# Package offline: generate=1.0 + execute_module=0.5
EXPECTED_PACKAGE_BUDGET_SPENT = 1.5


@dataclass
class CodegenRecipeResult:
    """Host-facing summary of a codegen recipe run."""

    status: str
    problem_id: str
    run_id: str
    recipe: str = "oneshot"
    verified: bool = False
    script: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    raw_response: str | None = None
    prompt: str | None = None
    refine_prompt: str | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)
    run_results: list[dict[str, Any]] = field(default_factory=list)
    turns: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    graph_status: str | None = None
    budget_spent: float = 0.0
    budget_level: str | None = None
    event_types: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    access_checks: list[dict[str, Any]] = field(default_factory=list)
    node_statuses: dict[str, str] = field(default_factory=dict)
    graph: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    checkpoint_durability: str | None = None
    checkpoint_path: str | None = None
    execute_command: list[str] | None = None
    first_pass_verified: bool | None = None
    package_name: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.verified


def run_codegen_recipe(
    problem: CodingProblem,
    completer: CodegenCompleter,
    *,
    recipe: RecipeKind = "oneshot",
    checkpoint_path: str | None = None,
    grants: list[object] | None = None,
) -> CodegenRecipeResult:
    """Execute a codegen recipe variant for ``problem``."""
    from mechaharness.host_kit import host_graph_executor

    bound = bound_run_for_codegen(problem.id, recipe=recipe)
    if recipe == "refine":
        graph = build_refine_graph(problem, run_id=bound.run_id)
    elif recipe == "package":
        graph = build_package_graph(problem, run_id=bound.run_id)
    else:
        graph = build_codegen_graph(problem, run_id=bound.run_id)

    state: dict[str, Any] = {"problem": problem, "problem_id": problem.id}
    runners = make_codegen_runners(completer, state=state)
    executor = host_graph_executor(
        runners=runners,
        checkpoint_path=checkpoint_path,
        agent_id="june-codegen",
        grants=grants,
    )
    budget_policy = bound.budget.to_mechaharness()
    result = asyncio.run(
        executor.run(
            graph,
            budget_policy=budget_policy,
            run_id=bound.run_id,
            resume=False,
        )
    )
    verified = bool(state.get("verified"))
    failures = list(state.get("failures") or [])
    status = "ok" if result.status == "ok" and verified else "failed"
    raw_events = list(getattr(result, "events", None) or [])
    events = [_serialize_event(event) for event in raw_events]
    event_types = [str(event.get("type") or "") for event in events]
    access_checks = [
        dict(event.get("payload") or {})
        for event in events
        if event.get("type") == "core:access_check"
    ]
    node_statuses = {
        node_id: str(getattr(node.status, "value", node.status))
        for node_id, node in result.graph.nodes.items()
    }
    diagnostics = dict(getattr(result, "diagnostics", None) or {})
    turns = list(getattr(completer, "turns", None) or [])
    files = dict(state.get("files") or {})
    execute_command = state.get("execute_command")
    return CodegenRecipeResult(
        status=status,
        problem_id=problem.id,
        run_id=bound.run_id,
        recipe=recipe,
        verified=verified,
        script=state.get("script"),
        files=files,
        raw_response=state.get("raw_response"),
        prompt=state.get("prompt"),
        refine_prompt=state.get("refine_prompt"),
        failures=failures,
        run_results=list(state.get("run_results") or []),
        turns=turns,
        error=getattr(result, "error", None)
        or (None if verified else "verification_failed"),
        graph_status=getattr(result, "status", None),
        budget_spent=float(getattr(result, "budget_spent", 0.0) or 0.0),
        budget_level=str(getattr(result, "budget_level", "") or "") or None,
        event_types=event_types,
        events=events,
        access_checks=access_checks,
        node_statuses=node_statuses,
        graph=_serialize_graph(result.graph),
        diagnostics=diagnostics,
        checkpoint_durability=str(diagnostics.get("checkpoint_durability") or "")
        or None,
        checkpoint_path=checkpoint_path,
        execute_command=list(execute_command) if execute_command else None,
        first_pass_verified=state.get("first_pass_verified"),
        package_name=state.get("package_name") or problem.package_name,
    )


def expected_node_order(recipe: RecipeKind) -> tuple[str, ...]:
    return {
        "oneshot": ONESHOT_NODE_ORDER,
        "refine": REFINE_NODE_ORDER,
        "package": PACKAGE_NODE_ORDER,
    }[recipe]


def _serialize_event(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        dumped = event.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(event, dict):
        return dict(event)
    return {
        "type": str(getattr(event, "type", "") or ""),
        "payload": getattr(event, "payload", None),
        "run_id": getattr(event, "run_id", None),
        "agent_id": getattr(event, "agent_id", None),
        "ts": str(getattr(event, "ts", "") or ""),
    }


def _serialize_graph(graph: Any) -> dict[str, Any]:
    if hasattr(graph, "model_dump"):
        dumped = graph.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    return {}
