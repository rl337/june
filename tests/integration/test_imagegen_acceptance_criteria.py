"""Thinking-model acceptance criteria → VL score on malformed bike fixture."""

from __future__ import annotations

import json
import os

import pytest

from june.recipes.imagegen.acceptance import (
    JunesparkAcceptanceSpecCrafter,
    JunesparkCoverageAuditor,
    JunesparkCriteriaScorer,
)
from june.recipes.imagegen.criteria_eval import score_trigger_alignment
from june.recipes.imagegen.fixtures import (
    load_fixture_bytes,
    load_fixture_meta,
    load_fixture_views,
)
from june.recipes.imagegen.problem import RAIN_BIKE_HYDRANT
from tests.integration.artifacts import artifact_dir_for

pytestmark = pytest.mark.integration


@pytest.mark.vision_live
def test_bike_acceptance_criteria_catch_malformed_fixture(
    local_junespark_provider,
) -> None:
    """Expand bike prompt → criteria cover known anomalies → VL fails for right reasons.

    Heavy text model writes the spec and audits coverage; VL scores the preserved
    malformed bicycle image (full + front crop). Artifacts land under
    ``artifacts/imagegen/test_bike_acceptance_criteria_catch_malformed_fixture/``.
    """
    meta = load_fixture_meta()
    image = load_fixture_bytes()
    views = load_fixture_views()
    prompt = str(meta.get("image_prompt") or RAIN_BIKE_HYDRANT.prompt)
    known = list(meta.get("known_anomalies") or [])
    assert known, "fixture meta must list known_anomalies"

    text_model = os.environ.get("JUNE_TEXT_MODEL") or "qwen/qwen3.6-35b-a3b"
    # Qwen3-VL-8B soft-passes structure on this fixture; Gemma cites duplicate
    # forks/handlebars. Override with JUNE_VL_SCORE_MODEL if needed.
    vl_model = (
        os.environ.get("JUNE_VL_SCORE_MODEL")
        or os.environ.get("JUNE_VL_MODEL")
        or "google/gemma-4-31b-qat"
    )

    artifact_dir = artifact_dir_for(
        "test_bike_acceptance_criteria_catch_malformed_fixture",
        family="imagegen",
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "image.png").write_bytes(image)
    (artifact_dir / "image_front.png").write_bytes(views["front"])

    crafter = JunesparkAcceptanceSpecCrafter(
        local_junespark_provider, model=text_model
    )
    auditor = JunesparkCoverageAuditor(
        local_junespark_provider, model=text_model
    )
    scorer = JunesparkCriteriaScorer(local_junespark_provider, model=vl_model)

    spec = crafter.expand(RAIN_BIKE_HYDRANT, image_prompt=prompt)
    coverage = auditor.audit(spec, known)
    score_full = scorer.score(image, spec, image_prompt=prompt)
    score_front = scorer.score(views["front"], spec, image_prompt=prompt)
    align_full = score_trigger_alignment(
        known_anomalies=known, coverage=coverage, score=score_full
    )
    align_front = score_trigger_alignment(
        known_anomalies=known, coverage=coverage, score=score_front
    )

    best_align = (
        align_front
        if align_front["aligned_count"] >= align_full["aligned_count"]
        else align_full
    )
    best_score = (
        score_front
        if align_front["aligned_count"] >= align_full["aligned_count"]
        else score_full
    )

    payload = {
        "text_model": text_model,
        "vl_model": vl_model,
        "prompt": prompt,
        "spec": spec.to_dict(),
        "coverage": coverage,
        "score_full": score_full,
        "score_front": score_front,
        "align_full": align_full,
        "align_front": align_front,
        "best_align": best_align,
    }
    (artifact_dir / "spec.json").write_text(
        json.dumps(spec.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "score_full.json").write_text(
        json.dumps(score_full, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "score_front.json").write_text(
        json.dumps(score_front, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    # 1) Thinking model criteria must cover known anomalies in theory.
    assert coverage.get("all_covered") is True, (
        f"acceptance criteria miss known anomalies: {coverage}"
    )
    structure = [c for c in spec.criteria if c.kind == "structure"]
    assert structure, f"expected structure criteria, got {spec.to_dict()}"

    # 2) VL must fail at least one mapped criterion for the correct defect reason.
    assert best_align.get("any_aligned") is True, (
        "VL did not fail covered criteria for the known malformation reasons. "
        f"best_align={best_align} score={best_score}"
    )
    assert best_score.get("failed"), best_score
