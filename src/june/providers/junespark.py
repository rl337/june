"""June-owned OpenAI-compat client for the junespark inference endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from june.config import JuneSettings, JunesparkSettings


@dataclass
class ModelCapabilities:
    tools: bool = True
    vision: bool = False
    media_generation: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "tools": self.tools,
            "vision": self.vision,
            "media_generation": self.media_generation,
        }


@dataclass
class ModelInfo:
    id: str
    owned_by: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owned_by": self.owned_by,
            "capabilities": self.capabilities.to_dict(),
        }


def infer_capabilities(model_id: str, raw: dict[str, Any] | None = None) -> ModelCapabilities:
    """Best-effort capability probe from model id / metadata."""
    del raw  # reserved for future server-provided capability fields
    lower = model_id.lower()
    vision_hints = ("vision", "vl", "llava", "qwen2.5-vl", "qwen-vl", "pixtral", "gemini")
    media_hints = ("image", "t2i", "flux", "sdxl", "comfy")
    no_tools = ("embed", "rerank", "tts", "whisper")
    return ModelCapabilities(
        tools=not any(h in lower for h in no_tools),
        vision=any(h in lower for h in vision_hints),
        media_generation=any(h in lower for h in media_hints),
    )


class JunesparkProvider:
    """HTTP client for junespark OpenAI-compatible inference."""

    def __init__(
        self,
        settings: JuneSettings | JunesparkSettings | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        if isinstance(settings, JuneSettings):
            js = settings.junespark
            self.base_url = (base_url or js.base_url or "").rstrip("/")
            self.api_key = api_key if api_key is not None else js.api_key
            self.default_model = model if model is not None else js.model
            self.timeout = timeout if timeout != 120.0 else js.timeout
        elif isinstance(settings, JunesparkSettings):
            self.base_url = (base_url or settings.base_url or "").rstrip("/")
            self.api_key = api_key if api_key is not None else settings.api_key
            self.default_model = model if model is not None else settings.model
            self.timeout = timeout if timeout != 120.0 else settings.timeout
        else:
            self.base_url = (base_url or "").rstrip("/")
            self.api_key = api_key or "junespark"
            self.default_model = model
            self.timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=self.timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _url(self, path: str) -> str:
        if not self.base_url:
            raise ValueError("junespark base_url is not configured")
        base = self.base_url
        if base.endswith("/v1"):
            return f"{base}{path}"
        return f"{base}/v1{path}"

    def list_models(self) -> list[ModelInfo]:
        resp = self._client.get(self._url("/models"), headers=self._headers())
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("data") if isinstance(payload, dict) else payload
        models: list[ModelInfo] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or item.get("model") or "")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    owned_by=item.get("owned_by"),
                    raw=item,
                    capabilities=infer_capabilities(model_id, item),
                )
            )
        return models

    def select_model(self, preferred: str | None = None) -> ModelInfo | None:
        models = self.list_models()
        if not models:
            return None
        want = preferred or self.default_model
        if want:
            for model in models:
                if model.id == want:
                    return model
        return models[0]

    def probe_capabilities(self, model: str | None = None) -> ModelCapabilities:
        info = self.select_model(model)
        if info is None:
            return infer_capabilities(model or self.default_model or "unknown")
        return info.capabilities

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Chat completions with multimodal content parts and optional tools."""
        body: dict[str, Any] = {
            "model": model or self.default_model or "default",
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        resp = self._client.post(
            self._url("/chat/completions"),
            headers=self._headers(),
            content=json.dumps(body),
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("chat completions response must be an object")
        return payload

    def extract_assistant(self, response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices") or []
        if not choices:
            return {"role": "assistant", "content": ""}
        message = choices[0].get("message") or {}
        return dict(message)
