"""Eval helpers: did VL fail covered criteria for the right structural reasons?"""

from __future__ import annotations

import re
from typing import Any

# Evidence that names the known rain_bike malformation modes.
_REASON_PATTERNS: dict[str, re.Pattern[str]] = {
    "front_wheel": re.compile(
        r"(incomplete|severed|melted|broken|warped|missing|cut\s*off|"
        r"not\s+a\s+complete|dissolv|seam|misalign)\w*.{0,80}(wheel|rim|tire)|"
        r"(wheel|rim|tire).{0,80}(incomplete|severed|melted|broken|warped|"
        r"missing|seam|misalign|duplicat)",
        re.IGNORECASE | re.DOTALL,
    ),
    "forks_handlebars": re.compile(
        r"(duplicat|two\s+sets?|double|fused|extra|misalign).{0,60}(fork|handle)|"
        r"(fork|handle).{0,60}(duplicat|two|double|fused|extra|misalign)",
        re.IGNORECASE | re.DOTALL,
    ),
    "ghost_frame": re.compile(
        r"(ghost|overlap|second|extra|double|duplicat|seam|misalign|"
        r"broken).{0,60}(frame|bike)|"
        r"(frame|bike).{0,60}(ghost|overlap|second|extra|double|duplicat|"
        r"seam|misalign|broken)",
        re.IGNORECASE | re.DOTALL,
    ),
}

_ANOMALY_REASON_KEYS = (
    ("front wheel", "front_wheel"),
    ("fork", "forks_handlebars"),
    ("handle", "forks_handlebars"),
    ("frame", "ghost_frame"),
)


def reason_key_for_anomaly(anomaly: dict[str, Any]) -> str | None:
    blob = f"{anomaly.get('region', '')} {anomaly.get('issue', '')}".lower()
    for needle, key in _ANOMALY_REASON_KEYS:
        if needle in blob:
            return key
    return None


def evidence_matches_reason(evidence: str, reason_key: str) -> bool:
    pattern = _REASON_PATTERNS.get(reason_key)
    if pattern is None:
        return False
    return bool(pattern.search(evidence or ""))


def score_trigger_alignment(
    *,
    known_anomalies: list[dict[str, Any]],
    coverage: dict[str, Any],
    score: dict[str, Any],
) -> dict[str, Any]:
    """For each covered anomaly, check a mapped failed criterion cites the right defect."""
    failed_by_id = {
        str(r.get("id")): r
        for r in (score.get("results") or [])
        if isinstance(r, dict) and not r.get("passed")
    }
    rows: list[dict[str, Any]] = []
    for i, anomaly in enumerate(known_anomalies):
        aid = f"a{i}"
        reason_key = reason_key_for_anomaly(anomaly)
        mapped: list[str] = []
        for cov in coverage.get("coverage") or []:
            if not isinstance(cov, dict):
                continue
            if str(cov.get("anomaly_id") or "") != aid:
                continue
            mapped = [str(x) for x in (cov.get("criterion_ids") or [])]
            break
        failed_mapped = [cid for cid in mapped if cid in failed_by_id]
        matched_evidence: list[dict[str, str]] = []
        for cid in failed_mapped:
            ev = str(failed_by_id[cid].get("evidence") or "")
            if reason_key and evidence_matches_reason(ev, reason_key):
                matched_evidence.append({"criterion_id": cid, "evidence": ev})
        rows.append(
            {
                "anomaly_id": aid,
                "reason_key": reason_key,
                "mapped_criterion_ids": mapped,
                "failed_mapped_ids": failed_mapped,
                "correct_reason_hits": matched_evidence,
                "aligned": bool(matched_evidence),
                "region": anomaly.get("region"),
                "issue": anomaly.get("issue"),
            }
        )
    aligned = sum(1 for r in rows if r["aligned"])
    return {
        "rows": rows,
        "aligned_count": aligned,
        "anomaly_count": len(known_anomalies),
        "all_aligned": aligned == len(known_anomalies) and len(known_anomalies) > 0,
        "any_aligned": aligned > 0,
        "structure_failures": [
            r
            for r in (score.get("results") or [])
            if isinstance(r, dict)
            and not r.get("passed")
            and str(r.get("kind") or "") == "structure"
        ],
    }
