"""E2E imagegen recipe: Comfy-backed Flux2 / Qwen Image text-to-image."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from june.recipes.imagegen import (
    EXPECTED_OFFLINE_BUDGET_SPENT,
    SIMPLE_STILL_LIFE_FLUX2,
    SIMPLE_STILL_LIFE_QWEN,
    FixedImageGenerator,
    run_imagegen_recipe,
)
from tests.integration.artifacts import artifact_dir_for

pytestmark = pytest.mark.integration


def _write_imagegen_artifacts(directory: Path, result) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if result.prompt:
        (directory / "prompt.txt").write_text(result.prompt, encoding="utf-8")
    if result.image_bytes:
        (directory / "image.png").write_bytes(result.image_bytes)
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
                "backend": result.backend,
                "problem_id": result.problem_id,
                "run_id": result.run_id,
                "budget_spent": result.budget_spent,
                "budget_level": result.budget_level,
                "turn_count": len(result.turns),
                "event_count": len(result.events),
                "event_types": result.event_types,
                "node_statuses": result.node_statuses,
                "failures": result.failures,
                "image_bytes": len(result.image_bytes or b""),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _assert_imagegen_success(
    result,
    *,
    expect_budget: float | None = EXPECTED_OFFLINE_BUDGET_SPENT,
) -> None:
    assert result.ok, (result.error, result.failures)
    assert result.graph_status == "ok"
    assert result.image_bytes and result.image_bytes.startswith(b"\x89PNG")
    assert result.access_checks and result.access_checks[0].get("allowed") is True
    assert result.budget_level == "ok"
    if expect_budget is not None:
        assert result.budget_spent == expect_budget
    assert result.event_types[0] == "core:access_check"
    assert result.event_types[1] == "core:graph_start"
    assert result.event_types[-1] == "core:graph_end"
    assert result.event_types.count("core:graph_node_start") == 4
    assert len(result.turns) == 1
    for node_id in ("prompt", "generate", "persist", "verify"):
        assert result.node_statuses.get(node_id) == "succeeded"


def test_imagegen_still_life_offline(artifact_dir: Path) -> None:
    result = run_imagegen_recipe(
        SIMPLE_STILL_LIFE_QWEN,
        FixedImageGenerator(),
        checkpoint_path=str(artifact_dir / "checkpoint.sqlite"),
    )
    _write_imagegen_artifacts(artifact_dir, result)
    _assert_imagegen_success(result)
    assert (artifact_dir / "image.png").is_file()


@pytest.mark.comfy_live
def test_imagegen_qwen_comfy_live(comfy_generator, tmp_path: Path) -> None:
    artifact_dir = artifact_dir_for("test_imagegen_qwen_comfy_live", family="imagegen")
    result = run_imagegen_recipe(
        SIMPLE_STILL_LIFE_QWEN,
        comfy_generator,
        checkpoint_path=str(artifact_dir / "checkpoint.sqlite"),
    )
    _write_imagegen_artifacts(artifact_dir, result)
    _assert_imagegen_success(result, expect_budget=None)
    assert result.backend == "qwen_image"
    assert "api" not in (result.turns[0].get("response") or {})
    assert result.turns[0].get("generator") == "comfy"
    assert (result.turns[0].get("response") or {}).get("prompt_id")


@pytest.mark.comfy_live
def test_imagegen_flux2_comfy_live(comfy_generator, tmp_path: Path) -> None:
    artifact_dir = artifact_dir_for("test_imagegen_flux2_comfy_live", family="imagegen")
    result = run_imagegen_recipe(
        SIMPLE_STILL_LIFE_FLUX2,
        comfy_generator,
        checkpoint_path=str(artifact_dir / "checkpoint.sqlite"),
    )
    _write_imagegen_artifacts(artifact_dir, result)
    _assert_imagegen_success(result, expect_budget=None)
    assert result.backend == "flux2"
    assert result.turns[0].get("generator") == "comfy"
