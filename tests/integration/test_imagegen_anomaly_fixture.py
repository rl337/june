"""Anomaly fixture characterization — not a claim that VL is a reliable gate."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from june.recipes.imagegen import RAIN_BIKE_HYDRANT, JunesparkVisionCritic
from june.recipes.imagegen.anomaly_eval import (
    eval_gate_trial,
    explicit_structural_hit,
    majority_malformed,
)
from june.recipes.imagegen.critics import JunesparkAnomalyCritic
from june.recipes.imagegen.fixtures import (
    RAIN_BIKE_CLEAN_POSITIVE,
    RAIN_BIKE_HYDRANT_MALFORMED,
    load_fixture_bytes,
    load_fixture_meta,
    load_fixture_views,
)
from tests.integration.artifacts import artifact_dir_for

pytestmark = pytest.mark.integration

_FOCUS = (
    "Focus on the red bicycle: front wheel, forks, handlebars, and frame. "
    "Look for duplicated steering parts, ghosted extra frames, and a "
    "broken or melted front wheel."
)


def test_rain_bike_hydrant_malformed_fixture_present() -> None:
    meta = load_fixture_meta()
    data = load_fixture_bytes()
    views = load_fixture_views()
    clean = load_fixture_bytes(RAIN_BIKE_CLEAN_POSITIVE)
    assert meta["id"] == RAIN_BIKE_HYDRANT_MALFORMED
    assert meta["known_anomalies"]
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 100_000
    assert "front" in views
    assert views["front"].startswith(b"\x89PNG\r\n\x1a\n")
    assert clean.startswith(b"\x89PNG\r\n\x1a\n")


def test_anomaly_eval_bar_helpers_unit() -> None:
    """Bar helpers score explicit hits without severity coerce."""
    weak = {
        "malformed": True,
        "summary": "minor distortion, otherwise fine",
        "artifacts": [{"region": "wheel", "issue": "slight uneven spokes", "severity": "medium"}],
    }
    strong = {
        "malformed": True,
        "summary": "duplicated forks and handlebars; front tire melted into pavement",
        "artifacts": [
            {
                "region": "forks",
                "issue": "two sets of forks fused at the stem",
                "severity": "high",
            }
        ],
    }
    clean = {"malformed": False, "summary": "intact bicycle", "artifacts": []}
    assert explicit_structural_hit(strong) is True
    assert explicit_structural_hit(weak) is False
    trial = eval_gate_trial(negative=strong, positive=clean)
    assert trial["trial_pass"] is True
    trial_weak = eval_gate_trial(negative=weak, positive=clean)
    assert trial_weak["trial_pass"] is False


@pytest.mark.vision_live
def test_anomaly_critic_characterization_malformed_fixture(
    local_junespark_provider,
    vision_critic: JunesparkVisionCritic,
) -> None:
    """Record raw VL anomaly judgment; checklist must still pass.

    Does **not** assert malformed=True — Qwen3-VL-8B often soft-pedals this
    known defect. Artifacts under artifacts/imagegen/ document the gap.
    """
    meta = load_fixture_meta()
    image = load_fixture_bytes()
    views = load_fixture_views()
    prompt = str(meta.get("image_prompt") or "")
    artifact_dir = artifact_dir_for(
        "test_anomaly_critic_characterization_malformed_fixture",
        family="imagegen",
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "image.png").write_bytes(image)
    (artifact_dir / "image_front.png").write_bytes(views["front"])

    checklist = vision_critic.critique(
        RAIN_BIKE_HYDRANT, image, image_prompt=prompt
    )
    anomaly = JunesparkAnomalyCritic(
        local_junespark_provider,
        model=vision_critic.model,
    ).critique_anomalies(
        image,
        image_prompt=prompt,
        views=views,
        focus=_FOCUS,
    )
    bar = {
        "checklist_passed": bool(checklist.get("passed")),
        "model_malformed": bool(anomaly.get("malformed")),
        "explicit_structural_hit": explicit_structural_hit(anomaly),
        "gate_negative_pass": bool(anomaly.get("malformed"))
        and explicit_structural_hit(anomaly),
        "note": (
            "Characterization only. A green artifact gate requires "
            "gate_negative_pass across trials plus a clean positive true-negative."
        ),
    }

    (artifact_dir / "checklist.json").write_text(
        json.dumps(checklist, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "anomaly.json").write_text(
        json.dumps(anomaly, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "result.json").write_text(
        json.dumps(bar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    assert checklist.get("passed") is True, checklist
    # Intentionally no assert on anomaly.malformed — that is the open eval gap.


@pytest.mark.vision_live
def test_anomaly_gate_eval_self_consistency(
    local_junespark_provider,
    vision_critic: JunesparkVisionCritic,
) -> None:
    """Eval-only: K independent critiques on malformed vs clean; record bar status.

    Does not fail the suite when the gate is red — that is the expected state
    for Qwen3-VL-8B until a stronger judge clears the acceptance bar.
    """
    trials = 3
    meta = load_fixture_meta()
    negative_img = load_fixture_bytes()
    negative_views = load_fixture_views()
    positive_img = load_fixture_bytes(RAIN_BIKE_CLEAN_POSITIVE)
    prompt = str(meta.get("image_prompt") or "")
    artifact_dir = artifact_dir_for(
        "test_anomaly_gate_eval_self_consistency",
        family="imagegen",
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    critic = JunesparkAnomalyCritic(
        local_junespark_provider,
        model=vision_critic.model,
        temperature=0.2,
    )
    negative_runs: list[dict] = []
    positive_runs: list[dict] = []
    trial_scores: list[dict] = []
    for _ in range(trials):
        neg = critic.critique_anomalies(
            negative_img,
            image_prompt=prompt,
            views=negative_views,
            focus=_FOCUS,
        )
        pos = critic.critique_anomalies(
            positive_img,
            image_prompt="a red bicycle on a dry sunny sidewalk",
            focus=_FOCUS,
        )
        negative_runs.append(neg)
        positive_runs.append(pos)
        trial_scores.append(eval_gate_trial(negative=neg, positive=pos))

    majority_neg = majority_malformed(negative_runs)
    majority_pos_bad = majority_malformed(positive_runs)
    trials_passed = sum(1 for t in trial_scores if t["trial_pass"])
    bar_green = trials_passed == trials and majority_neg and not majority_pos_bad

    payload = {
        "model": vision_critic.model,
        "trials": trials,
        "trials_passed": trials_passed,
        "majority_negative_malformed": majority_neg,
        "majority_positive_malformed": majority_pos_bad,
        "bar_green": bar_green,
        "trial_scores": trial_scores,
        "negative_malformed_votes": dict(
            Counter(bool(r.get("malformed")) for r in negative_runs)
        ),
        "positive_malformed_votes": dict(
            Counter(bool(r.get("malformed")) for r in positive_runs)
        ),

        "negative_explicit_hits": sum(
            1 for r in negative_runs if explicit_structural_hit(r)
        ),
        "acceptance_bar": {
            "negative": (
                "malformed=true AND explicit mention of duplicate "
                "forks/handlebars and/or incomplete/melted front wheel"
            ),
            "positive": "malformed=false on rain_bike_clean_positive",
            "metric": f"all {trials} paired trials pass; majority vote agrees",
        },
        "recipe_policy": (
            "critique_refine stays semantic-checklist-only. "
            "Do not wire artifact_retry until bar_green is true."
        ),
    }
    (artifact_dir / "eval.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "negative_runs.json").write_text(
        json.dumps(negative_runs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "positive_runs.json").write_text(
        json.dumps(positive_runs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Always succeed as a recording probe; bar_green is the signal to read.
    assert (artifact_dir / "eval.json").is_file()
    assert payload["recipe_policy"]
