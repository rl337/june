"""Shared LM Studio / JuneSpark chat helpers for imagegen soft points."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from june.providers.junespark import JunesparkProvider

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def assistant_text(message: dict[str, Any]) -> str:
    """Prefer final content; fall back to reasoning_content for think models."""
    content = _coerce_text(message.get("content")).strip()
    if content:
        return content
    reasoning = _coerce_text(
        message.get("reasoning_content") or message.get("reasoning")
    ).strip()
    # Prefer a JSON object embedded in CoT when content never arrived.
    match = _JSON_RE.search(reasoning)
    if match:
        return match.group(0).strip()
    # Otherwise take the last quoted span or last line.
    return _finalize_reasoning(reasoning)


def _finalize_reasoning(reasoning: str) -> str:
    if not reasoning:
        return ""
    # Prefer the last double-quoted span (common in CoT "Final Output").
    quotes = re.findall(r'"([^"\n]{12,})"', reasoning)
    if quotes:
        return quotes[-1].strip()
    lines = [ln.strip() for ln in reasoning.splitlines() if ln.strip()]
    return lines[-1] if lines else ""



def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for part in value:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(value)


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("empty model response; expected JSON object")
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = _JSON_RE.search(stripped)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def png_data_url(image: bytes) -> str:
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def chat_text(
    provider: JunesparkProvider,
    messages: list[dict[str, Any]],
    *,
    model: str | None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> tuple[str, dict[str, Any]]:
    response = provider.complete(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    message = provider.extract_assistant(response)
    return assistant_text(message), response
