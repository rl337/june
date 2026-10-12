"""Unit tests for acceptance-criteria VL alignment helpers."""

from __future__ import annotations

from june.recipes.imagegen.criteria_eval import (
    evidence_matches_reason,
    score_trigger_alignment,
)


def test_evidence_reason_patterns() -> None:
    assert evidence_matches_reason(
        "front tire is melted into the wet pavement", "front_wheel"
    )
    assert evidence_matches_reason(
        "two sets of handlebars fused at the stem", "forks_handlebars"
    )
    assert evidence_matches_reason(
        "The bicycle frame appears broken or duplicated in the middle section",
        "ghost_frame",
    )
    assert not evidence_matches_reason(
        "bicycle is red and leaning on hydrant", "front_wheel"
    )


def test_score_trigger_alignment() -> None:
    known = [
        {
            "region": "forks / handlebars",
            "issue": "duplicated or fused steering assembly",
        },
        {
            "region": "front wheel",
            "issue": "rim/tire severed or melted into pavement",
        },
    ]
    coverage = {
        "coverage": [
            {"anomaly_id": "a0", "criterion_ids": ["bike_form"]},
            {"anomaly_id": "a1", "criterion_ids": ["wheel_intact"]},
        ]
    }
    score = {
        "results": [
            {
                "id": "bike_form",
                "passed": False,
                "kind": "structure",
                "evidence": "duplicated forks and handlebars visible",
            },
            {
                "id": "wheel_intact",
                "passed": False,
                "kind": "structure",
                "evidence": "front wheel melted into pavement",
            },
            {"id": "sky", "passed": True, "kind": "color", "evidence": "overcast ok"},
        ]
    }
    out = score_trigger_alignment(
        known_anomalies=known, coverage=coverage, score=score
    )
    assert out["all_aligned"]
    assert out["aligned_count"] == 2
