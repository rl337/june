"""E2E codegen recipe: generate Python for sum-of-multiples, execute, verify."""

from __future__ import annotations

from pathlib import Path

import pytest

from june.recipes.codegen import (
    SUM_MULTIPLES_OF_3_OR_5,
    FixedScriptCompleter,
)
from tests.integration.artifacts import run_codegen_with_artifacts
from tests.integration.harness_assertions import (
    assert_denied_without_execute_grant,
    assert_event_log_shape,
    assert_inference_efficiency,
    assert_successful_codegen_harness,
)

pytestmark = pytest.mark.integration


def test_codegen_sum_multiples_offline(
    fixed_completer: FixedScriptCompleter,
    artifact_dir: Path,
) -> None:
    """Deterministic path: fixed completer emits a known-good script."""
    result = run_codegen_with_artifacts(
        SUM_MULTIPLES_OF_3_OR_5,
        fixed_completer,
        artifact_dir,
    )
    assert_successful_codegen_harness(result, expect_turns=1, max_turns=1)
    assert_event_log_shape(result, recipe="oneshot")
    assert_inference_efficiency(result, recipe="oneshot", expect_turns=1)
    assert "print" in (result.script or "")
    assert (artifact_dir / "events.jsonl").is_file()
    assert (artifact_dir / "turns.jsonl").is_file()
    assert len(result.events) == 13


def test_codegen_denied_without_graph_execute_grant(
    fixed_completer: FixedScriptCompleter,
    artifact_dir: Path,
) -> None:
    """Empty host grants must fail the GraphExecute capability check."""
    result = run_codegen_with_artifacts(
        SUM_MULTIPLES_OF_3_OR_5,
        fixed_completer,
        artifact_dir,
        grants=[],
    )
    assert_denied_without_execute_grant(result)
    assert (artifact_dir / "events.json").is_file()
    assert (artifact_dir / "access_checks.json").is_file()


@pytest.mark.junespark_live
def test_codegen_sum_multiples_junespark(
    junespark_completer,
    artifact_dir: Path,
) -> None:
    """Live JuneSpark heavy/reason model generates a script that passes fixtures."""
    result = run_codegen_with_artifacts(
        SUM_MULTIPLES_OF_3_OR_5,
        junespark_completer,
        artifact_dir,
    )
    assert_successful_codegen_harness(
        result,
        expect_budget_spent=None,
        expect_turns=1,
        max_turns=1,
    )
    assert_event_log_shape(result, recipe="oneshot")
    assert_inference_efficiency(result, recipe="oneshot", expect_turns=1, max_turns=1)
    lowered = (result.script or "").lower()
    assert "input" in lowered or "stdin" in lowered or "sys.stdin" in lowered
    assert result.raw_response is not None and result.raw_response.strip()
    assert "api" in (result.turns[0].get("response") or {})
    assert (artifact_dir / "turns.jsonl").is_file()
    assert (artifact_dir / "events.jsonl").is_file()
    assert len(result.events) == 13
