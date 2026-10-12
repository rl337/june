"""Acceptance bar helpers for an artifact / geometry gate (eval only).

A gate is green only when it rejects the known-malformed fixture with an
*explicit* structural mention AND accepts a clean positive — without severity
coerce. Until that bar is green, do not wire detect→retry into recipes.
"""

from __future__ import annotations

import re
from typing import Any

# Phrases that count as affirming the known malformed-bike failure modes.
# Avoid matching negations like "no duplicated …" / "not melted …".
_NEGATIVE_HIT_RE = re.compile(
    r"(?<!\bno\s)(?<!\bnot\s)(?<!\bwithout\s)("
    r"duplicat\w*\s+(sets?\s+of\s+)?(forks?|handlebars?)|"
    r"two\s+(sets?\s+of\s+)?(forks|handlebars)|"
    r"double\s+(forks?|handlebars?)|"
    r"fused\s+(forks?|handlebars?|steering)|"
    r"ghosted\s+(extra\s+)?(frame|bike|second)|"
    r"(incomplete|severed|melted)\s+(front\s+)?(wheel|rim|tire)|"
    r"(front\s+)?(wheel|rim|tire)\s+(is\s+)?(incomplete|severed|melted|broken)"
    r")",
    re.IGNORECASE,
)


def critique_text_blob(critique: dict[str, Any]) -> str:
    parts: list[str] = [str(critique.get("summary") or "")]
    for item in critique.get("artifacts") or []:
        if isinstance(item, dict):
            parts.append(str(item.get("region") or ""))
            parts.append(str(item.get("issue") or ""))
    for view in (critique.get("views") or {}).values():
        if isinstance(view, dict):
            parts.append(critique_text_blob({**view, "views": {}}))
    return "\n".join(parts)


def explicit_structural_hit(critique: dict[str, Any]) -> bool:
    """True if critique text names the known malformed-bike failure modes."""
    return bool(_NEGATIVE_HIT_RE.search(critique_text_blob(critique)))


def gate_accepts_negative(critique: dict[str, Any]) -> bool:
    """Negative fixture must be rejected with an explicit structural mention."""
    return bool(critique.get("malformed")) and explicit_structural_hit(critique)


def gate_accepts_positive(critique: dict[str, Any]) -> bool:
    """Clean fixture must not be marked malformed."""
    return not bool(critique.get("malformed"))


def majority_malformed(critiques: list[dict[str, Any]]) -> bool:
    if not critiques:
        return False
    votes = sum(1 for c in critiques if bool(c.get("malformed")))
    return votes * 2 > len(critiques)


def eval_gate_trial(
    *,
    negative: dict[str, Any],
    positive: dict[str, Any],
) -> dict[str, Any]:
    """Score one paired trial against the acceptance bar."""
    neg_ok = gate_accepts_negative(negative)
    pos_ok = gate_accepts_positive(positive)
    return {
        "negative_rejected": bool(negative.get("malformed")),
        "negative_explicit_hit": explicit_structural_hit(negative),
        "negative_pass": neg_ok,
        "positive_pass": pos_ok,
        "trial_pass": neg_ok and pos_ok,
    }
