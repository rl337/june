"""Shared assertions for cost, permissions, and observability on recipe runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from june.recipes.codegen.graph import RecipeKind
from june.recipes.codegen.run import (
    EXPECTED_OFFLINE_BUDGET_SPENT,
    EXPECTED_PACKAGE_BUDGET_SPENT,
    EXPECTED_REFINE_BUDGET_SPENT,
    CodegenRecipeResult,
    expected_node_order,
)

# Exact event-type skeleton for a successful linear graph run (no graph_node snapshots).
# access_check → graph_start → (node_start, node_end)×N → graph_end
INFERENCE_NODE_KINDS = frozenset(
    {
        "june.codegen.generate",
        "june.codegen.repair_generate",
    }
)


def assert_successful_codegen_harness(
    result: CodegenRecipeResult,
    *,
    recipe: RecipeKind | None = None,
    expect_budget_spent: float | None = EXPECTED_OFFLINE_BUDGET_SPENT,
    durable_checkpoint: bool = True,
    expect_turns: int | None = None,
    max_turns: int | None = None,
) -> None:
    """Assert MH host contracts after a successful codegen recipe run."""
    kind: RecipeKind = recipe or result.recipe  # type: ignore[assignment]

    assert result.ok, (
        f"graph={result.graph_status} error={result.error} "
        f"failures={result.failures} budget={result.budget_spent}"
    )
    assert result.graph_status == "ok"
    assert result.verified is True
    assert result.failures == []
    assert result.script is not None and result.script.strip()

    # Permissions: GraphExecute granted and allowed at dispatch.
    assert result.access_checks, "expected core:access_check event(s)"
    check = result.access_checks[0]
    assert check.get("tool") == "graph_executor"
    assert "core:graph.execute" in (check.get("required") or [])
    assert "core:graph.execute" in (check.get("granted") or [])
    assert check.get("allowed") is True
    assert len(result.access_checks) == 1, "expected a single access_check at dispatch"

    # Cost / budget.
    assert result.budget_level == "ok"
    assert result.budget_spent > 0.0
    if expect_budget_spent is not None:
        assert result.budget_spent == expect_budget_spent, (
            f"budget_spent={result.budget_spent} expected={expect_budget_spent}"
        )

    assert_event_log_shape(result, recipe=kind)
    assert_inference_efficiency(
        result,
        recipe=kind,
        expect_turns=expect_turns,
        max_turns=max_turns,
    )

    # Diagnostics from host_kit / GraphExecutor.
    assert result.diagnostics.get("resumed") is False
    assert result.diagnostics.get("effect_dispatches") == 0
    if durable_checkpoint:
        assert result.checkpoint_durability == "durable"
        assert result.diagnostics.get("checkpoint_durability") == "durable"


def assert_event_log_shape(
    result: CodegenRecipeResult,
    *,
    recipe: RecipeKind | None = None,
) -> None:
    """Assert the MechaHarness event log matches the linear recipe topology."""
    kind: RecipeKind = recipe or result.recipe  # type: ignore[assignment]
    nodes = expected_node_order(kind)
    types = result.event_types

    assert types[0] == "core:access_check"
    assert types[1] == "core:graph_start"
    assert types[-1] == "core:graph_end"
    assert types.count("core:access_check") == 1
    assert types.count("core:graph_start") == 1
    assert types.count("core:graph_end") == 1
    assert types.count("core:graph_node_start") == len(nodes)
    assert types.count("core:graph_node_end") == len(nodes)

    # Exact skeleton: no extra event types between start/end for these recipes.
    expected_types = (
        ["core:access_check", "core:graph_start"]
        + [t for _ in nodes for t in ("core:graph_node_start", "core:graph_node_end")]
        + ["core:graph_end"]
    )
    assert types == expected_types, (
        f"event type sequence mismatch for {kind}:\n"
        f"  got={types}\n  expected={expected_types}"
    )
    assert len(result.events) == len(expected_types)

    start_ids = [
        str((event.get("payload") or {}).get("node_id") or "")
        for event in result.events
        if event.get("type") == "core:graph_node_start"
    ]
    end_ids = [
        str((event.get("payload") or {}).get("node_id") or "")
        for event in result.events
        if event.get("type") == "core:graph_node_end"
    ]
    assert start_ids == list(nodes), start_ids
    assert end_ids == list(nodes), end_ids

    for event in result.events:
        if event.get("type") != "core:graph_node_end":
            continue
        payload = event.get("payload") or {}
        assert payload.get("status") == "succeeded", payload
        assert int(payload.get("attempt") or 0) == 1, payload

    for node_id in nodes:
        assert result.node_statuses.get(node_id) == "succeeded", result.node_statuses

    # Graph-start payload should advertise the same node count / kinds.
    start_payload = next(
        (e.get("payload") or {})
        for e in result.events
        if e.get("type") == "core:graph_start"
    )
    assert int(start_payload.get("node_count") or 0) == len(nodes)
    kinds = set(start_payload.get("kinds") or [])
    assert len(kinds) == len(nodes) or len(kinds) >= 1


def assert_inference_efficiency(
    result: CodegenRecipeResult,
    *,
    recipe: RecipeKind | None = None,
    expect_turns: int | None = None,
    max_turns: int | None = None,
) -> None:
    """Assert completer/inference call counts match the recipe's efficient path."""
    kind: RecipeKind = recipe or result.recipe  # type: ignore[assignment]
    turns = len(result.turns)
    if expect_turns is not None:
        assert turns == expect_turns, (
            f"inference turns={turns} expected={expect_turns} recipe={kind}"
        )
    if max_turns is not None:
        assert turns <= max_turns, (
            f"inference turns={turns} exceeded max={max_turns} recipe={kind}"
        )

    if kind == "oneshot":
        assert turns == 1, f"oneshot must make exactly 1 inference call, got {turns}"
        assert result.budget_spent == EXPECTED_OFFLINE_BUDGET_SPENT or (
            # Live may keep the same cost model (generate=1 + execute=0.5).
            result.budget_spent == 1.5
        )
    elif kind == "package":
        assert turns == 1, f"package must make exactly 1 inference call, got {turns}"
        assert result.budget_spent == EXPECTED_PACKAGE_BUDGET_SPENT or (
            result.budget_spent == 1.5
        )
    elif kind == "refine":
        # Efficient paths: first-pass success → 1 call / 1.5; repair → 2 calls / 3.0.
        assert turns in (1, 2), f"refine turns must be 1 or 2, got {turns}"
        if result.first_pass_verified:
            assert turns == 1
            assert result.budget_spent == 1.5
        else:
            assert turns == 2
            assert result.budget_spent == EXPECTED_REFINE_BUDGET_SPENT
            assert result.refine_prompt

    # Each turn should look like a real request/response record.
    for turn in result.turns:
        assert "request" in turn and "response" in turn
        assert (turn.get("response") or {}).get("text")


def assert_failed_verification(
    result: CodegenRecipeResult,
    *,
    expect_turns: int = 1,
) -> None:
    """Assert the graph ran but verification rejected the artifact."""
    assert result.ok is False
    assert result.verified is False
    assert result.failures, "expected verification failures"
    assert result.access_checks and result.access_checks[0].get("allowed") is True
    assert result.budget_spent > 0.0
    assert len(result.turns) == expect_turns
    assert result.event_types[0] == "core:access_check"
    assert result.event_types[1] == "core:graph_start"
    assert result.event_types[-1] == "core:graph_end"
    # Verify is terminal failure with max_attempts=1 — no retry storm.
    if result.recipe == "oneshot":
        nodes = expected_node_order("oneshot")
        assert result.node_statuses.get("verify") == "failed"
        assert result.event_types.count("core:graph_node_start") == len(nodes)
        assert result.event_types.count("core:graph_node_end") == len(nodes)
        verify_ends = [
            e
            for e in result.events
            if e.get("type") == "core:graph_node_end"
            and (e.get("payload") or {}).get("node_id") == "verify"
        ]
        assert len(verify_ends) == 1
        assert (verify_ends[0].get("payload") or {}).get("status") == "failed"
        assert (verify_ends[0].get("payload") or {}).get("attempt") == 1


def assert_refine_repaired(result: CodegenRecipeResult) -> None:
    """Assert refine path failed first pass then succeeded after repair."""
    assert_successful_codegen_harness(
        result,
        recipe="refine",
        expect_budget_spent=EXPECTED_REFINE_BUDGET_SPENT,
        expect_turns=2,
        max_turns=2,
    )
    assert result.first_pass_verified is False
    assert result.refine_prompt


def assert_refine_live_efficiency(result: CodegenRecipeResult) -> None:
    """Live refine may skip repair if first pass already verifies."""
    assert_successful_codegen_harness(
        result,
        recipe="refine",
        expect_budget_spent=None,
        max_turns=2,
    )
    assert_inference_efficiency(result, recipe="refine", max_turns=2)


def assert_package_artifacts(
    result: CodegenRecipeResult,
    artifact_dir: Path,
    *,
    package_name: str = "wordstats",
) -> None:
    """Assert multi-file package outputs and `python -m` execution."""
    assert_successful_codegen_harness(
        result,
        recipe="package",
        expect_budget_spent=EXPECTED_PACKAGE_BUDGET_SPENT,
        expect_turns=1,
        max_turns=1,
    )
    assert result.package_name == package_name
    assert any(p.endswith("__main__.py") for p in result.files)
    assert any(
        p.startswith(f"{package_name}/") and not p.endswith("__main__.py")
        for p in result.files
    )
    assert result.execute_command is not None
    assert result.execute_command[-2:] == ["-m", package_name]
    files_root = artifact_dir / "files"
    for rel in result.files:
        assert (files_root / rel).is_file(), rel


def assert_denied_without_execute_grant(result: CodegenRecipeResult) -> None:
    """Assert GraphExecute is required and denial is observable."""
    assert result.ok is False
    assert result.verified is False
    assert result.graph_status == "denied"
    assert result.budget_spent == 0.0
    assert result.access_checks, "expected denied access_check"
    check = result.access_checks[0]
    assert check.get("allowed") is False
    assert "core:graph.execute" in (check.get("required") or [])
    assert "core:graph.execute" not in (check.get("granted") or [])
    assert result.event_types == [
        "core:access_check",
        "core:graph_start",
        "core:graph_end",
    ]
    assert len(result.turns) == 0
    assert "core:graph_node_start" not in result.event_types


def summarize_efficiency(result: CodegenRecipeResult) -> dict[str, Any]:
    """Compact efficiency snapshot for artifact / debugging."""
    return {
        "recipe": result.recipe,
        "turns": len(result.turns),
        "events": len(result.events),
        "budget_spent": result.budget_spent,
        "first_pass_verified": result.first_pass_verified,
        "node_start_order": [
            (e.get("payload") or {}).get("node_id")
            for e in result.events
            if e.get("type") == "core:graph_node_start"
        ],
    }
