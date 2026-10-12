"""Completers for the codegen recipe (live JuneSpark/LM Studio or fixed offline)."""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from june.providers.junespark import JunesparkProvider
from june.recipes.codegen.problem import REFERENCE_SOLUTION


class CodegenCompleter(Protocol):
    """Minimal host completer: prompt text in → model/assistant text out."""

    turns: list[dict[str, Any]]

    def generate(self, prompt: str) -> str: ...


class FixedScriptCompleter:
    """Deterministic offline completer that returns a known-good solution."""

    def __init__(self, script: str = REFERENCE_SOLUTION) -> None:
        self.script = script
        self.turns: list[dict[str, Any]] = []

    def generate(self, prompt: str) -> str:
        text = f"```python\n{self.script.rstrip()}\n```\n"
        self.turns.append(
            {
                "index": len(self.turns),
                "completer": "fixed",
                "request": {
                    "messages": [{"role": "user", "content": prompt}],
                },
                "response": {
                    "text": text,
                },
            }
        )
        return text


class ScriptedSequenceCompleter:
    """Return scripted responses in order (cycles the last if exhausted)."""

    def __init__(self, responses: Sequence[str]) -> None:
        if not responses:
            raise ValueError("ScriptedSequenceCompleter requires at least one response")
        self.responses = list(responses)
        self.turns: list[dict[str, Any]] = []
        self._index = 0

    def generate(self, prompt: str) -> str:
        idx = min(self._index, len(self.responses) - 1)
        body = self.responses[idx]
        self._index += 1
        if "```" in body:
            text = body if body.endswith("\n") else body + "\n"
        else:
            text = f"```python\n{body.rstrip()}\n```\n"
        self.turns.append(
            {
                "index": len(self.turns),
                "completer": "scripted_sequence",
                "request": {
                    "messages": [{"role": "user", "content": prompt}],
                    "sequence_index": idx,
                },
                "response": {
                    "text": text,
                },
            }
        )
        return text


class FixedPackageCompleter:
    """Emit path-annotated fences for a fixed multi-file package."""

    def __init__(self, files: dict[str, str]) -> None:
        if not files:
            raise ValueError("FixedPackageCompleter requires files")
        self.files = dict(files)
        self.turns: list[dict[str, Any]] = []

    def generate(self, prompt: str) -> str:
        chunks: list[str] = []
        for path, source in self.files.items():
            chunks.append(f"```python path={path}\n{source.rstrip()}\n```\n")
        text = "\n".join(chunks)
        self.turns.append(
            {
                "index": len(self.turns),
                "completer": "fixed_package",
                "request": {
                    "messages": [{"role": "user", "content": prompt}],
                    "paths": sorted(self.files),
                },
                "response": {
                    "text": text,
                },
            }
        )
        return text


class JunesparkCodegenCompleter:
    """Live OpenAI-compat completer against JuneSpark / LM Studio."""

    def __init__(
        self,
        provider: JunesparkProvider,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system = system or (
            "You write correct, minimal Python using the standard library only "
            "(no third-party imports). "
            "Put any chain-of-thought in reasoning only. "
            "The final assistant content MUST be the required fenced python "
            "block(s) and nothing else."
        )
        self.turns: list[dict[str, Any]] = []

    def generate(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": prompt},
        ]
        response = self.provider.complete(
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        message = self.provider.extract_assistant(response)
        text = _assistant_text_for_codegen(message)
        self.turns.append(
            {
                "index": len(self.turns),
                "completer": "junespark",
                "request": {
                    "messages": messages,
                    "model": self.model or self.provider.default_model,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                },
                "response": {
                    "text": text,
                    "assistant_message": message,
                    "api": response,
                },
            }
        )
        return text


def _assistant_text_for_codegen(message: dict[str, Any]) -> str:
    """Prefer final ``content``; fall back to ``reasoning_content`` for think models."""
    content = _coerce_text(message.get("content")).strip()
    reasoning = _coerce_text(
        message.get("reasoning_content") or message.get("reasoning")
    ).strip()
    if content:
        return content
    return reasoning


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
