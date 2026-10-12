"""Prompt crafting and vision critique soft points for imagegen refine."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from june.providers.junespark import JunesparkProvider
from june.recipes.imagegen.llm import chat_text, parse_json_object, png_data_url
from june.recipes.imagegen.problem import ImageProblem


class PromptCrafter(Protocol):
    turns: list[dict[str, Any]]

    def craft(
        self,
        problem: ImageProblem,
        *,
        prior_critique: dict[str, Any] | None = None,
    ) -> str: ...


class VisionCritic(Protocol):
    turns: list[dict[str, Any]]

    def critique(
        self,
        problem: ImageProblem,
        image: bytes,
        *,
        image_prompt: str,
    ) -> dict[str, Any]: ...


class AnomalyCritic(Protocol):
    """Structural / geometric QA — orthogonal to element checklists."""

    turns: list[dict[str, Any]]

    def critique_anomalies(
        self,
        image: bytes,
        *,
        image_prompt: str = "",
        focus: str = "",
    ) -> dict[str, Any]: ...


class FixedPromptCrafter:
    def __init__(self, prompt: str | None = None) -> None:
        self.prompt = prompt
        self.turns: list[dict[str, Any]] = []

    def craft(self, problem: ImageProblem, *, prior_critique: dict[str, Any] | None = None) -> str:
        text = self.prompt or problem.prompt
        if prior_critique and not prior_critique.get("passed"):
            missing = ", ".join(prior_critique.get("missing") or []) or "unspecified gaps"
            notes = str(prior_critique.get("notes") or "").strip()
            text = f"{text}. Emphasize clearly visible: {missing}."
            if notes:
                text = f"{text} Fix: {notes[:400]}"
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "prompt_crafter",
                "kind": "fixed",
                "request": {"prior_critique": prior_critique},
                "response": {"image_prompt": text},
            }
        )
        return text


class ScriptedVisionCritic:
    """Offline critic: returns scripted critiques in order (last repeats)."""

    def __init__(self, critiques: Sequence[dict[str, Any]]) -> None:
        if not critiques:
            raise ValueError("ScriptedVisionCritic requires at least one critique")
        self.critiques = list(critiques)
        self.turns: list[dict[str, Any]] = []
        self._index = 0

    def critique(self, problem: ImageProblem, image: bytes, *, image_prompt: str) -> dict[str, Any]:
        del problem, image, image_prompt
        idx = min(self._index, len(self.critiques) - 1)
        payload = dict(self.critiques[idx])
        self._index += 1
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "vision_critic",
                "kind": "scripted",
                "response": payload,
            }
        )
        return payload


class JunesparkPromptCrafter:
    """Text LLM that turns a goal + optional critique into a Comfy image prompt."""

    def __init__(
        self,
        provider: JunesparkProvider,
        *,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.turns: list[dict[str, Any]] = []

    def craft(self, problem: ImageProblem, *, prior_critique: dict[str, Any] | None = None) -> str:
        system = (
            "You write concise, concrete text-to-image prompts for diffusion models. "
            "Return ONLY the image prompt text — no markdown, no JSON, no preamble."
        )
        user = (
            f"Goal title: {problem.title}\n"
            f"Goal description:\n{problem.prompt}\n"
            f"Required visual elements: {list(problem.required)}\n"
            f"Forbidden elements: {list(problem.forbidden)}\n"
        )
        if prior_critique and not prior_critique.get("passed"):
            failed = prior_critique.get("failed_criteria") or []
            failed_lines = "\n".join(
                f"- {row.get('id')} ({row.get('kind')}): {row.get('text')} "
                f"| evidence: {row.get('evidence')}"
                for row in failed
                if isinstance(row, dict)
            )
            user += (
                "\nPrevious image FAILED acceptance criteria.\n"
                f"Missing / failed: {prior_critique.get('missing')}\n"
                f"Notes:\n{prior_critique.get('notes')}\n"
            )
            if failed_lines:
                user += f"Failed criteria detail:\n{failed_lines}\n"
            user += (
                "Rewrite the image prompt so every failed criterion is unmistakable. "
                "For structure failures, state exact counts (fingers, forks, limbs) "
                "and forbid duplicates/mutations explicitly.\n"
            )
        else:
            user += "\nWrite the first image prompt.\n"
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
        text = text.strip().strip('"')
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "prompt_crafter",
                "kind": "junespark",
                "request": {"messages": messages, "model": self.model},
                "response": {"image_prompt": text, "api": response},
            }
        )
        if not text:
            raise RuntimeError("prompt crafter returned empty text")
        return text


class JunesparkVisionCritic:
    """Multimodal VL critic that returns a structured pass/fail checklist."""

    def __init__(
        self,
        provider: JunesparkProvider,
        *,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 768,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.turns: list[dict[str, Any]] = []

    def critique(self, problem: ImageProblem, image: bytes, *, image_prompt: str) -> dict[str, Any]:
        system = (
            "You are a strict visual QA critic for text-to-image outputs. "
            "Inspect the image and answer with JSON ONLY using this schema:\n"
            '{"passed": bool, "present": [str], "missing": [str], '
            '"forbidden_found": [str], "notes": str}\n'
            "Mark passed=true only if every required element is clearly visible "
            "and no forbidden element is present."
        )
        user_text = (
            f"Image prompt used:\n{image_prompt}\n\n"
            f"Required elements: {list(problem.required)}\n"
            f"Forbidden elements: {list(problem.forbidden)}\n"
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
        payload.setdefault("passed", False)
        payload.setdefault("present", [])
        payload.setdefault("missing", [])
        payload.setdefault("forbidden_found", [])
        payload.setdefault("notes", "")
        payload["present"] = [str(x) for x in (payload.get("present") or [])]
        payload["missing"] = [str(x) for x in (payload.get("missing") or [])]
        payload["forbidden_found"] = [
            str(x) for x in (payload.get("forbidden_found") or [])
        ]
        # Trust the VL checklist, but never allow passed=true with gaps.
        if payload["missing"] or payload["forbidden_found"]:
            payload["passed"] = False
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "vision_critic",
                "kind": "junespark",
                "request": {
                    "model": self.model,
                    "required": list(problem.required),
                    "forbidden": list(problem.forbidden),
                    "image_prompt": image_prompt,
                    "image_bytes": len(image),
                },
                "response": {"critique": payload, "raw_text": text, "api": response},
            }
        )
        return payload


class JunesparkAnomalyCritic:
    """VL structural inspector — raw model judgment only (no severity coerce).

    Qwen3-VL-8B is **not** a reliable generate→detect→retry gate for unknown
    geometry artifacts. Optional ``views`` are recorded per-label; aggregation
    is OR of each view's own ``malformed`` flag (model-reported), not a
    medium-severity heuristic that hid false negatives in earlier probes.
    """

    def __init__(
        self,
        provider: JunesparkProvider,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.turns: list[dict[str, Any]] = []

    def critique_anomalies(
        self,
        image: bytes,
        *,
        image_prompt: str = "",
        focus: str = "",
        views: dict[str, bytes] | None = None,
    ) -> dict[str, Any]:
        focus_text = focus.strip() or (
            "Inspect primary subjects carefully for duplicated or fused parts, "
            "broken wheels/limbs, ghosted extra objects, and impossible joins."
        )
        labeled: list[tuple[str, bytes]] = [("full", image)]
        for name, data in (views or {}).items():
            if name == "full" or not data:
                continue
            labeled.append((str(name), bytes(data)))

        per_view: dict[str, dict[str, Any]] = {}
        for label, data in labeled:
            per_view[label] = self._critique_one(
                data, image_prompt=image_prompt, focus=focus_text, view=label
            )

        artifacts: list[dict[str, Any]] = []
        summaries: list[str] = []
        for label, payload in per_view.items():
            if payload.get("summary"):
                summaries.append(f"{label}: {payload['summary']}")
            for item in payload.get("artifacts") or []:
                if isinstance(item, dict):
                    artifacts.append({**item, "view": label})

        # Honest aggregate: only what the model itself marked malformed.
        malformed = any(bool(v.get("malformed")) for v in per_view.values())
        qualities = [str(v.get("overall_quality") or "") for v in per_view.values()]
        if any(q == "poor" for q in qualities):
            overall = "poor"
        elif any(q == "fair" for q in qualities):
            overall = "fair"
        elif any(q == "excellent" for q in qualities) and all(
            q in {"good", "excellent", ""} for q in qualities
        ):
            overall = "excellent" if all(q == "excellent" for q in qualities) else "good"
        else:
            overall = qualities[0] if qualities else "unknown"

        result = {
            "malformed": malformed,
            "artifacts": artifacts,
            "overall_quality": overall,
            "summary": " | ".join(summaries) if summaries else "",
            "views": per_view,
        }
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "anomaly_critic",
                "kind": "junespark",
                "request": {
                    "model": self.model,
                    "image_prompt": image_prompt,
                    "focus": focus_text,
                    "view_names": [name for name, _ in labeled],
                    "image_bytes": len(image),
                },
                "response": {"critique": result},
            }
        )
        return result

    def _critique_one(
        self,
        image: bytes,
        *,
        image_prompt: str,
        focus: str,
        view: str,
    ) -> dict[str, Any]:
        system = (
            "You are a meticulous inspector for AI-generated photos. "
            "Focus on geometric / anatomical malformations, duplicated parts, "
            "impossible structure, melted/clipped geometry, and local artifacts. "
            "Reply with JSON ONLY using this schema:\n"
            '{"malformed": bool, "artifacts": [{"region": str, "issue": str, '
            '"severity": "low|medium|high"}], '
            '"overall_quality": "poor|fair|good|excellent", "summary": str}\n'
            "Set malformed=true only when you are confident of a structural "
            "defect (duplicated parts, impossible joins, incomplete limbs/wheels). "
            "Vague aesthetic complaints are not malformations."
        )
        user_text = f"View: {view}\n{focus}\n"
        if image_prompt:
            user_text += f"\nImage prompt used:\n{image_prompt}\n"
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
        text, _response = chat_text(
            self.provider,
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        payload = parse_json_object(text)
        payload.setdefault("malformed", False)
        payload.setdefault("artifacts", [])
        payload.setdefault("overall_quality", "unknown")
        payload.setdefault("summary", "")
        artifacts = []
        for item in payload.get("artifacts") or []:
            if not isinstance(item, dict):
                continue
            artifacts.append(
                {
                    "region": str(item.get("region") or ""),
                    "issue": str(item.get("issue") or ""),
                    "severity": str(item.get("severity") or "medium").lower(),
                }
            )
        payload["artifacts"] = artifacts
        payload["overall_quality"] = str(payload.get("overall_quality") or "").lower()
        payload["malformed"] = bool(payload.get("malformed"))
        return payload



