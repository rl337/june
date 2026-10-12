"""Critique-refine imagegen: Comfy generate + LM Studio craft/VL critique."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from june.recipes.imagegen import (
    RAIN_BIKE_HYDRANT,
    SIMPLE_STILL_LIFE_QWEN,
    FixedImageGenerator,
    FixedPromptCrafter,
    ImageProblem,
    PromptCrafter,
    ScriptedVisionCritic,
    run_imagegen_recipe,
)
from tests.integration.artifacts import artifact_dir_for

pytestmark = pytest.mark.integration


class IncompleteFirstCraft:
    """First craft deliberately omits required elements so live VL must repair."""

    def __init__(self, inner: PromptCrafter, *, first_prompt: str) -> None:
        self.inner = inner
        self.first_prompt = first_prompt
        self.turns: list[dict[str, Any]] = []

    def craft(
        self,
        problem: ImageProblem,
        *,
        prior_critique: dict[str, Any] | None = None,
    ) -> str:
        if prior_critique is None:
            text = self.first_prompt
            self.turns.append(
                {
                    "index": len(self.turns),
                    "role": "prompt_crafter",
                    "kind": "incomplete_first",
                    "request": {"prior_critique": None},
                    "response": {"image_prompt": text},
                }
            )
            return text
        before = len(getattr(self.inner, "turns", []) or [])
        text = self.inner.craft(problem, prior_critique=prior_critique)
        self.turns.extend(list(self.inner.turns[before:]))
        return text


def _write_artifacts(directory: Path, result) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if result.prompt:
        (directory / "prompt.txt").write_text(result.prompt, encoding="utf-8")
    if result.first_image_prompt:
        (directory / "image_prompt_00.txt").write_text(
            result.first_image_prompt, encoding="utf-8"
        )
    if result.image_prompt:
        (directory / "image_prompt.txt").write_text(
            result.image_prompt, encoding="utf-8"
        )
        if result.first_pass_passed is False:
            (directory / "image_prompt_01.txt").write_text(
                result.image_prompt, encoding="utf-8"
            )
    if result.first_image_bytes:
        (directory / "image_00.png").write_bytes(result.first_image_bytes)
    if result.image_bytes:
        (directory / "image.png").write_bytes(result.image_bytes)
        if result.first_pass_passed is False:
            (directory / "image_01.png").write_bytes(result.image_bytes)
    if result.first_critique:
        (directory / "critique_00.json").write_text(
            json.dumps(result.first_critique, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (directory / "critique.json").write_text(
        json.dumps(result.critique, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (directory / "turns.json").write_text(
        json.dumps(result.turns, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (directory / "events.json").write_text(
        json.dumps(result.events, indent=2, sort_keys=True, default=str) + "\n",
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
                "budget_spent": result.budget_spent,
                "first_pass_passed": result.first_pass_passed,
                "first_image_prompt": result.first_image_prompt,
                "first_critique": result.first_critique,
                "turn_count": len(result.turns),
                "event_count": len(result.events),
                "event_types": result.event_types,
                "node_statuses": result.node_statuses,
                "failures": result.failures,
                "image_prompt": result.image_prompt,
                "critique": result.critique,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def test_imagegen_critique_refine_offline_repairs(artifact_dir: Path) -> None:
    """Scripted critic fails once, then passes after refine — proves the loop."""
    result = run_imagegen_recipe(
        SIMPLE_STILL_LIFE_QWEN,
        FixedImageGenerator(),
        recipe="critique_refine",
        crafter=FixedPromptCrafter(),
        critic=ScriptedVisionCritic(
            [
                {
                    "passed": False,
                    "present": ["ceramic bowl", "red apples"],
                    "missing": ["wooden table"],
                    "forbidden_found": [],
                    "notes": "table surface not visible",
                },
                {
                    "passed": True,
                    "present": ["ceramic bowl", "red apples", "wooden table"],
                    "missing": [],
                    "forbidden_found": [],
                    "notes": "ok",
                },
            ]
        ),
        checkpoint_path=str(artifact_dir / "checkpoint.sqlite"),
    )
    _write_artifacts(artifact_dir, result)
    assert result.ok, (result.error, result.failures, result.critique)
    assert result.first_pass_passed is False
    assert result.event_types.count("core:graph_node_start") == 10
    assert result.budget_spent == 3.5  # 0.25+1+0.5+0.25+1+0.5
    roles = [t.get("role") for t in result.turns]
    assert roles.count("prompt_crafter") == 2
    assert roles.count("vision_critic") == 2
    assert (artifact_dir / "image_00.png").is_file()
    assert (artifact_dir / "image_01.png").is_file()


@pytest.mark.comfy_live
@pytest.mark.vision_live
def test_imagegen_critique_refine_live_dual_backend(
    comfy_generator,
    prompt_crafter,
    vision_critic,
) -> None:
    """Live: LM Studio text crafts + VL critiques; Comfy generates on JuneSpark."""
    artifact_dir = artifact_dir_for(
        "test_imagegen_critique_refine_live_dual_backend",
        family="imagegen",
    )
    result = run_imagegen_recipe(
        RAIN_BIKE_HYDRANT,
        comfy_generator,
        recipe="critique_refine",
        crafter=prompt_crafter,
        critic=vision_critic,
        checkpoint_path=str(artifact_dir / "checkpoint.sqlite"),
    )
    _write_artifacts(artifact_dir, result)
    assert result.ok, (
        f"error={result.error} failures={result.failures} "
        f"critique={result.critique} image_prompt={result.image_prompt!r}"
    )
    assert result.event_types[0] == "core:access_check"
    assert result.event_types[-1] == "core:graph_end"
    assert result.event_types.count("core:graph_node_start") == 10
    # Efficient: at most one repair generation (1–2 Comfy calls).
    comfy_turns = [t for t in result.turns if t.get("generator") == "comfy"]
    assert 1 <= len(comfy_turns) <= 2, comfy_turns
    critic_turns = [t for t in result.turns if t.get("role") == "vision_critic"]
    assert len(critic_turns) >= 1
    assert (artifact_dir / "image.png").is_file()
    assert result.image_prompt


@pytest.mark.comfy_live
@pytest.mark.vision_live
def test_imagegen_critique_refine_live_repairs(
    comfy_generator,
    prompt_crafter,
    vision_critic,
) -> None:
    """Live repair path: incomplete first prompt → VL fail → refine → regen → pass."""
    artifact_dir = artifact_dir_for(
        "test_imagegen_critique_refine_live_repairs",
        family="imagegen",
    )
    # Omit hydrant + rain so the first Comfy image should fail VL checklist.
    crafter = IncompleteFirstCraft(
        prompt_crafter,
        first_prompt=(
            "a red bicycle on a dry sunny sidewalk, clear blue sky, "
            "simple photo, no people, no text"
        ),
    )
    result = run_imagegen_recipe(
        RAIN_BIKE_HYDRANT,
        comfy_generator,
        recipe="critique_refine",
        crafter=crafter,
        critic=vision_critic,
        checkpoint_path=str(artifact_dir / "checkpoint.sqlite"),
    )
    _write_artifacts(artifact_dir, result)
    assert result.first_pass_passed is False, (
        f"expected first VL fail; critique={result.first_critique}"
    )
    assert result.ok, (
        f"error={result.error} failures={result.failures} "
        f"first_critique={result.first_critique} critique={result.critique} "
        f"first_prompt={result.first_image_prompt!r} "
        f"refined_prompt={result.image_prompt!r}"
    )
    comfy_turns = [t for t in result.turns if t.get("generator") == "comfy"]
    assert len(comfy_turns) == 2, comfy_turns
    assert result.budget_spent == 3.5
    assert (artifact_dir / "image_00.png").is_file()
    assert (artifact_dir / "image_01.png").is_file()
    assert (artifact_dir / "critique_00.json").is_file()
    assert (artifact_dir / "image_prompt_00.txt").is_file()
    assert (artifact_dir / "image_prompt_01.txt").is_file()
