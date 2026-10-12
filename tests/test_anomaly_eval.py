"""Unit tests for artifact-gate acceptance helpers."""

from __future__ import annotations

from june.recipes.imagegen.anomaly_eval import (
    eval_gate_trial,
    explicit_structural_hit,
    gate_accepts_negative,
    gate_accepts_positive,
    majority_malformed,
)


def test_explicit_hit_requires_known_failure_modes() -> None:
    assert explicit_structural_hit(
        {
            "malformed": True,
            "summary": "duplicated forks and melted front wheel into pavement",
            "artifacts": [],
        }
    )
    assert not explicit_structural_hit(
        {
            "malformed": True,
            "summary": "slight spoke unevenness, otherwise photoreal",
            "artifacts": [{"region": "wheel", "issue": "minor spacing", "severity": "low"}],
        }
    )
    # Negations must not count as hits.
    assert not explicit_structural_hit(
        {
            "malformed": False,
            "summary": "handlebars are mostly intact with no duplicated parts or melted geometry",
            "artifacts": [],
        }
    )


def test_gate_bar_and_majority() -> None:
    neg = {
        "malformed": True,
        "summary": "two sets of handlebars; incomplete front tire",
        "artifacts": [],
    }
    pos = {"malformed": False, "summary": "clean bike", "artifacts": []}
    assert gate_accepts_negative(neg)
    assert gate_accepts_positive(pos)
    assert eval_gate_trial(negative=neg, positive=pos)["trial_pass"]
    assert majority_malformed([neg, neg, pos])
    assert not majority_malformed([neg, pos, pos])
