"""Refine recipe: one-shot fails on buggy RPN; refine graph repairs it."""

from __future__ import annotations

from pathlib import Path

import pytest

from june.recipes.codegen import (
    BAD_RPN_SOLUTION,
    REFERENCE_RPN_SOLUTION,
    RPN_EVAL,
    FixedScriptCompleter,
    ScriptedSequenceCompleter,
)
from tests.integration.artifacts import run_codegen_with_artifacts
from tests.integration.harness_assertions import (
    assert_event_log_shape,
    assert_failed_verification,
    assert_inference_efficiency,
    assert_refine_live_efficiency,
    assert_refine_repaired,
    summarize_efficiency,
)

pytestmark = pytest.mark.integration


def test_codegen_rpn_oneshot_fails_with_buggy_script(artifact_dir: Path) -> None:
    """Same buggy first answer fails under the one-shot recipe."""
    result = run_codegen_with_artifacts(
        RPN_EVAL,
        FixedScriptCompleter(BAD_RPN_SOLUTION),
        artifact_dir,
        recipe="oneshot",
    )
    assert_failed_verification(result, expect_turns=1)
    assert_inference_efficiency(result, recipe="oneshot", expect_turns=1)
    assert (artifact_dir / "failures.json").is_file()
    assert (artifact_dir / "turns.jsonl").is_file()


def test_codegen_rpn_refine_succeeds_after_repair(artifact_dir: Path) -> None:
    """Refine graph: turn1 buggy, turn2 reference fix → verified."""
    completer = ScriptedSequenceCompleter([BAD_RPN_SOLUTION, REFERENCE_RPN_SOLUTION])
    result = run_codegen_with_artifacts(
        RPN_EVAL,
        completer,
        artifact_dir,
        recipe="refine",
    )
    assert_refine_repaired(result)
    assert_event_log_shape(result, recipe="refine")
    assert (artifact_dir / "refine_prompt.txt").is_file()
    assert summarize_efficiency(result)["turns"] == 2


@pytest.mark.junespark_live
def test_codegen_rpn_refine_junespark(junespark_completer, artifact_dir: Path) -> None:
    """Live refine must verify with at most two inference calls."""
    result = run_codegen_with_artifacts(
        RPN_EVAL,
        junespark_completer,
        artifact_dir,
        recipe="refine",
    )
    assert_refine_live_efficiency(result)
    assert "api" in (result.turns[0].get("response") or {})
    assert (artifact_dir / "events.jsonl").is_file()
    assert (artifact_dir / "turns.jsonl").is_file()
