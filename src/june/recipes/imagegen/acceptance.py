"""Prompt → explicit acceptance criteria (thinking model) + per-criterion VL score."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from june.providers.junespark import JunesparkProvider
from june.recipes.imagegen.llm import chat_text, parse_json_object, png_data_url
from june.recipes.imagegen.problem import ImageProblem


@dataclass(frozen=True)
class AcceptanceCriterion:
    id: str
    text: str
    kind: str = "other"  # count | structure | pose | color | composition | other

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "text": self.text, "kind": self.kind}


@dataclass
class AcceptanceSpec:
    criteria: list[AcceptanceCriterion] = field(default_factory=list)
    source_prompt: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_prompt": self.source_prompt,
            "criteria": [c.to_dict() for c in self.criteria],
            "raw": self.raw,
        }


class AcceptanceSpecCrafter(Protocol):
    turns: list[dict[str, Any]]

    def expand(
        self,
        problem: ImageProblem,
        *,
        image_prompt: str | None = None,
    ) -> AcceptanceSpec: ...


class CriteriaScorer(Protocol):
    turns: list[dict[str, Any]]

    def score(
        self,
        image: bytes,
        spec: AcceptanceSpec,
        *,
        image_prompt: str = "",
    ) -> dict[str, Any]: ...


def criteria_from_payload(payload: dict[str, Any]) -> list[AcceptanceCriterion]:
    items = payload.get("criteria") or payload.get("constraints") or []
    out: list[AcceptanceCriterion] = []
    for i, item in enumerate(items):
        if isinstance(item, str):
            out.append(
                AcceptanceCriterion(id=f"c{i}", text=item.strip(), kind="other")
            )
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("criterion") or item.get("check") or "").strip()
        if not text:
            continue
        cid = str(item.get("id") or f"c{i}").strip() or f"c{i}"
        kind = str(item.get("kind") or item.get("type") or "other").strip().lower()
        out.append(AcceptanceCriterion(id=cid, text=text, kind=kind))
    return out


class JunesparkAcceptanceSpecCrafter:
    """Heavy text/thinking model expands a prompt into explicit image constraints."""

    def __init__(
        self,
        provider: JunesparkProvider,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.turns: list[dict[str, Any]] = []

    def expand(
        self, problem: ImageProblem, *, image_prompt: str | None = None
    ) -> AcceptanceSpec:
        prompt = (image_prompt or problem.prompt).strip()
        system = (
            "You write explicit visual acceptance criteria for a text-to-image prompt. "
            "Return JSON ONLY:\n"
            '{"criteria": [{"id": str, "text": str, "kind": '
            '"count|structure|pose|color|composition|other"}]}\n'
            "Rules:\n"
            "- Each criterion must be a concrete, checkable visual fact "
            "(like unit-test assertions for the image).\n"
            "- Include count constraints (exactly N of subject when implied).\n"
            "- For physical objects (bikes, animals, people, vehicles), ALWAYS include "
            "structure criteria: single coherent instance, well-formed anatomy/geometry, "
            "no duplicated parts (forks, limbs, heads), complete unbroken key parts "
            "(wheels, limbs).\n"
            "- Include color/pose/setting criteria implied by the prompt.\n"
            "- Prefer 5–12 criteria. No markdown."
        )
        user = (
            f"Goal title: {problem.title}\n"
            f"Image prompt:\n{prompt}\n"
            f"Already listed required elements: {list(problem.required)}\n"
            f"Forbidden: {list(problem.forbidden)}\n"
            "Expand into explicit acceptance criteria."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        text, response = chat_text(
            self.provider,
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        try:
            payload = parse_json_object(text)
            criteria = criteria_from_payload(payload)
            if not criteria:
                raise ValueError("empty criteria list")
        except (ValueError, json.JSONDecodeError) as first_err:
            # One retry — thinking models sometimes exhaust tokens in CoT.
            retry_messages = list(messages) + [
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was not valid JSON with a non-empty "
                        "criteria array. Reply again with JSON ONLY."
                    ),
                }
            ]
            text, response = chat_text(
                self.provider,
                retry_messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            try:
                payload = parse_json_object(text)
                criteria = criteria_from_payload(payload)
            except (ValueError, json.JSONDecodeError) as second_err:
                raise RuntimeError(
                    f"acceptance spec parse failed after retry; "
                    f"first={first_err!r} second={second_err!r} raw={text[:400]!r}"
                ) from second_err
            if not criteria:
                raise RuntimeError(
                    f"acceptance spec empty after retry; raw={text[:400]!r}"
                ) from first_err
        spec = AcceptanceSpec(criteria=criteria, source_prompt=prompt, raw=payload)
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "acceptance_spec",
                "kind": "junespark",
                "request": {"model": self.model, "messages": messages},
                "response": {"spec": spec.to_dict(), "api": response},
            }
        )
        return spec



class JunesparkCriteriaScorer:
    """VL model scores each acceptance criterion pass/fail with evidence."""

    def __init__(
        self,
        provider: JunesparkProvider,
        *,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1536,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.turns: list[dict[str, Any]] = []

    def score(
        self,
        image: bytes,
        spec: AcceptanceSpec,
        *,
        image_prompt: str = "",
    ) -> dict[str, Any]:
        listed = "\n".join(
            f"- id={c.id} kind={c.kind}: {c.text}" for c in spec.criteria
        )
        system = (
            "You are a strict visual QA judge. For EACH acceptance criterion, "
            "decide pass/fail from the image alone. Reply JSON ONLY:\n"
            '{"results": [{"id": str, "passed": bool, "evidence": str}], '
            '"passed_all": bool}\n'
            "evidence must say what you see that justifies the pass/fail "
            "(name duplicated parts, missing pieces, wrong counts, etc.). "
            "Be willing to fail structure criteria when geometry is broken.\n"
            "For bicycle structure criteria, explicitly check and mention: "
            "how many front forks, how many handlebar sets, whether each wheel "
            "is a complete closed circle (not melted/severed into the ground), "
            "and whether a second ghosted/overlapping bike frame is present."
        )
        user_text = (
            f"Image prompt:\n{image_prompt or spec.source_prompt}\n\n"
            f"Criteria:\n{listed}\n"
        )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": png_data_url(image)}},
                ],
            },
        ]
        text, response = chat_text(
            self.provider,
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        payload = parse_json_object(text)
        by_id = {c.id: c for c in spec.criteria}
        results: list[dict[str, Any]] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or "")
            crit = by_id.get(cid)
            results.append(
                {
                    "id": cid,
                    "passed": bool(item.get("passed")),
                    "evidence": str(item.get("evidence") or ""),
                    "kind": crit.kind if crit else "",
                    "text": crit.text if crit else "",
                }
            )
        # Fill any missing ids as failed unknowns.
        seen = {r["id"] for r in results}
        for crit in spec.criteria:
            if crit.id not in seen:
                results.append(
                    {
                        "id": crit.id,
                        "passed": False,
                        "evidence": "criterion missing from VL response",
                        "kind": crit.kind,
                        "text": crit.text,
                    }
                )
        passed_all = all(bool(r.get("passed")) for r in results) if results else False
        out = {
            "passed_all": passed_all,
            "results": results,
            "failed": [r for r in results if not r.get("passed")],
        }
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "criteria_scorer",
                "kind": "junespark",
                "request": {
                    "model": self.model,
                    "criterion_ids": [c.id for c in spec.criteria],
                    "image_bytes": len(image),
                },
                "response": {"score": out, "raw_text": text, "api": response},
            }
        )
        return out


class JunesparkCoverageAuditor:
    """Thinking model: map known anomalies → which criteria would catch them."""

    def __init__(
        self,
        provider: JunesparkProvider,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.turns: list[dict[str, Any]] = []

    def audit(
        self,
        spec: AcceptanceSpec,
        known_anomalies: list[dict[str, Any]],
    ) -> dict[str, Any]:
        crit_lines = "\n".join(
            f"- {c.id} [{c.kind}]: {c.text}" for c in spec.criteria
        )
        anom_lines = "\n".join(
            f"- a{i}: region={a.get('region')}; issue={a.get('issue')}"
            for i, a in enumerate(known_anomalies)
        )
        system = (
            "You audit whether acceptance criteria would catch known image defects. "
            "Return JSON ONLY:\n"
            '{"coverage": [{"anomaly_id": str, "criterion_ids": [str], '
            '"rationale": str}], "uncovered": [str], "all_covered": bool}\n'
            "For each known anomaly, list criterion ids that would FAIL if that "
            "anomaly were present. Prefer structure criteria for geometry bugs. "
            "uncovered = anomaly ids with empty criterion_ids."
        )
        user = (
            f"Acceptance criteria:\n{crit_lines}\n\n"
            f"Known anomalies in a defective render of this prompt:\n{anom_lines}\n"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        text, response = chat_text(
            self.provider,
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        try:
            payload = parse_json_object(text)
        except (ValueError, json.JSONDecodeError):
            text, response = chat_text(
                self.provider,
                list(messages)
                + [
                    {
                        "role": "user",
                        "content": "Reply again with JSON ONLY for the coverage audit.",
                    }
                ],
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            payload = parse_json_object(text)
        coverage = list(payload.get("coverage") or [])
        uncovered = [str(x) for x in (payload.get("uncovered") or [])]
        # Recompute all_covered honestly from coverage rows.
        expected = {f"a{i}" for i in range(len(known_anomalies))}
        covered_ids: set[str] = set()
        for row in coverage:
            if not isinstance(row, dict):
                continue
            aid = str(row.get("anomaly_id") or "")
            cids = [str(x) for x in (row.get("criterion_ids") or []) if str(x)]
            if aid and cids:
                covered_ids.add(aid)
            elif aid:
                uncovered.append(aid)
        uncovered = sorted(set(uncovered) | (expected - covered_ids))
        all_covered = expected <= covered_ids and not uncovered
        out = {
            "coverage": coverage,
            "uncovered": uncovered,
            "all_covered": all_covered,
            "covered_ids": sorted(covered_ids),
        }
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "coverage_auditor",
                "kind": "junespark",
                "request": {"model": self.model, "messages": messages},
                "response": {"audit": out, "raw_text": text, "api": response},
            }
        )
        return out
