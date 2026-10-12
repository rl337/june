"""Criteria-refine compose: host loop binds evaluate_criteria with max_retries."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from june.recipes.imagegen.acceptance import (
    JunesparkAcceptanceSpecCrafter,
    JunesparkCriteriaScorer,
)
from june.recipes.imagegen.critics import FixedPromptCrafter
from june.recipes.imagegen.evaluate import (
    BoundEvaluateCriteria,
    EvaluateResult,
    FixedImageEvaluator,
)
from june.recipes.imagegen.generators import FixedImageGenerator
from june.recipes.imagegen.problem import HAND_FIVE_FINGERS, SIMPLE_STILL_LIFE_QWEN
from june.recipes.imagegen.run import (
    DEFAULT_CRITERIA_MAX_RETRIES,
    run_imagegen_recipe,
)
from tests.integration.artifacts import artifact_dir_for

pytestmark = pytest.mark.integration


def _write_artifacts(directory: Path, result: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if result.prompt:
        (directory / "prompt.txt").write_text(result.prompt, encoding="utf-8")
    if result.image_prompt:
        (directory / "image_prompt.txt").write_text(
            result.image_prompt, encoding="utf-8"
        )
    if result.first_image_prompt:
        (directory / "image_prompt_00.txt").write_text(
            result.first_image_prompt, encoding="utf-8"
        )
    if result.first_image_bytes:
        (directory / "image_00.png").write_bytes(result.first_image_bytes)
    if result.image_bytes:
        (directory / "image.png").write_bytes(result.image_bytes)
    for i, attempt in enumerate(result.attempts or []):
        prompt = attempt.get("image_prompt")
        if isinstance(prompt, str) and prompt:
            (directory / f"image_prompt_{i:02d}.txt").write_text(
                prompt, encoding="utf-8"
            )
    if result.acceptance_spec:
        (directory / "acceptance_spec.json").write_text(
            json.dumps(result.acceptance_spec, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if result.first_critique:
        (directory / "critique_00.json").write_text(
            json.dumps(result.first_critique, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (directory / "critique.json").write_text(
        json.dumps(result.critique, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (directory / "attempts.json").write_text(
        json.dumps(
            [
                {k: v for k, v in row.items() if k != "image_bytes"}
                for row in (result.attempts or [])
            ],
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    (directory / "turns.json").write_text(
        json.dumps(result.turns, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (directory / "result.json").write_text(
        json.dumps(
            {
                "ok": result.ok,
                "status": result.status,
                "recipe": result.recipe,
                "backend": result.backend,
                "problem_id": result.problem_id,
                "run_id": result.run_id,
                "max_retries": result.max_retries,
                "attempt_count": len(result.attempts or []),
                "first_pass_passed": result.first_pass_passed,
                "failures": result.failures,
                "image_prompt": result.image_prompt,
                "critique": result.critique,
                "diagnostics": result.diagnostics,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def test_imagegen_criteria_refine_offline_retry_loop(artifact_dir: Path) -> None:
    """Fail twice then pass — proves configurable max_retries (not a single repair)."""
    max_retries = 2
    assert max_retries == DEFAULT_CRITERIA_MAX_RETRIES
    evaluator = FixedImageEvaluator(
        [
            EvaluateResult(
                passed=False,
                failed=[
                    {
                        "id": "structure_01",
                        "kind": "structure",
                        "text": "exactly five fingers",
                        "evidence": "six digits visible",
                        "passed": False,
                    }
                ],
                summary="finger count wrong",
                score={"passed_all": False},
            ),
            EvaluateResult(
                passed=False,
                failed=[
                    {
                        "id": "structure_01",
                        "kind": "structure",
                        "text": "exactly five fingers",
                        "evidence": "fused fingers",
                        "passed": False,
                    }
                ],
                summary="still malformed",
                score={"passed_all": False},
            ),
            EvaluateResult(
                passed=True,
                failed=[],
                summary="ok",
                score={"passed_all": True},
            ),
        ]
    )
    result = run_imagegen_recipe(
        HAND_FIVE_FINGERS,
        FixedImageGenerator(),
        recipe="criteria_refine",
        crafter=FixedPromptCrafter(),
        evaluator=evaluator,
        max_retries=max_retries,
    )
    _write_artifacts(artifact_dir, result)
    assert result.ok, (result.error, result.failures, result.critique)
    assert result.recipe == "criteria_refine"
    assert result.max_retries == max_retries
    assert len(result.attempts) == 3  # first + 2 repairs
    assert result.first_pass_passed is False
    assert [a["passed"] for a in result.attempts] == [False, False, True]
    roles = [t.get("role") for t in result.turns]
    assert roles.count("prompt_crafter") == 3  # initial + 2 refine crafts
    assert roles.count("image_evaluator") == 3
    assert result.diagnostics.get("compose") == "host_loop"
    assert result.diagnostics.get("max_retries") == max_retries


def test_imagegen_criteria_refine_offline_exhausts_retries(artifact_dir: Path) -> None:
    """When every evaluate fails, loop stops after max_retries repairs."""
    max_retries = 1
    result = run_imagegen_recipe(
        SIMPLE_STILL_LIFE_QWEN,
        FixedImageGenerator(),
        recipe="criteria_refine",
        crafter=FixedPromptCrafter(),
        evaluator=FixedImageEvaluator(
            [
                EvaluateResult(
                    passed=False,
                    failed=[{"id": "c1", "text": "missing bowl", "evidence": "no"}],
                    summary="fail",
                    score={"passed_all": False},
                ),
            ]
        ),
        max_retries=max_retries,
    )
    _write_artifacts(artifact_dir, result)
    assert not result.ok
    assert len(result.attempts) == max_retries + 1
    assert result.max_retries == max_retries
    assert any(f.get("reason") == "criteria_failed" for f in result.failures)


@pytest.mark.comfy_live
@pytest.mark.vision_live
def test_imagegen_criteria_refine_live_hand_fingers(
    comfy_generator,
    prompt_crafter,
    local_junespark_provider,
) -> None:
    """Live compose: craft → generate → evaluate_criteria × max_retries on hands."""
    artifact_dir = artifact_dir_for(
        "test_imagegen_criteria_refine_live_hand_fingers",
        family="imagegen",
    )
    text_model = os.environ.get("JUNE_TEXT_MODEL") or "qwen/qwen3.6-35b-a3b"
    vl_model = (
        os.environ.get("JUNE_VL_SCORE_MODEL")
        or os.environ.get("JUNE_VL_MODEL")
        or "google/gemma-4-31b-qat"
    )
    max_retries = int(os.environ.get("JUNE_CRITERIA_MAX_RETRIES") or "2")
    evaluator = BoundEvaluateCriteria(
        JunesparkAcceptanceSpecCrafter(local_junespark_provider, model=text_model),
        JunesparkCriteriaScorer(local_junespark_provider, model=vl_model),
        checkpoint_dir=str(artifact_dir / "eval_checkpoints"),
    )
    result = run_imagegen_recipe(
        HAND_FIVE_FINGERS,
        comfy_generator,
        recipe="criteria_refine",
        crafter=prompt_crafter,
        evaluator=evaluator,
        max_retries=max_retries,
    )
    _write_artifacts(artifact_dir, result)
    # Persist each attempt image when available via first/final only; attempts
    # record sizes. Live assert: loop ran within budget and produced PNG bytes.
    assert result.max_retries == max_retries
    assert 1 <= len(result.attempts) <= max_retries + 1
    assert result.image_bytes and result.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert (artifact_dir / "image.png").is_file()
    assert (artifact_dir / "attempts.json").is_file()
    # Soft live gate: prefer pass, but always record attempts for inspection.
    # Hands are artifact-prone; failure after retries is still useful evidence.
    if not result.ok:
        pytest.xfail(
            f"criteria_refine exhausted retries "
            f"(attempts={len(result.attempts)} failed={result.failures})"
        )
