"""June-owned ComfyUI HTTP client (queue prompt → poll history → fetch image)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from pyiv.http import HttpClient, UrllibHttpClient

from june.config import ComfySettings, JuneSettings

# Re-export for integration fixtures that imported the old June-local client.
__all__ = [
    "ComfyImageRef",
    "ComfyJobResult",
    "ComfyProvider",
    "UrllibHttpClient",
]


@dataclass(frozen=True)
class ComfyImageRef:
    """Pointer to an image in Comfy's view API."""

    filename: str
    subfolder: str = ""
    type: str = "output"

    def to_dict(self) -> dict[str, str]:
        return {
            "filename": self.filename,
            "subfolder": self.subfolder,
            "type": self.type,
        }


@dataclass
class ComfyJobResult:
    prompt_id: str
    images: list[ComfyImageRef]
    outputs: dict[str, Any]
    status: dict[str, Any]


class ComfyProvider:
    """Minimal ComfyUI API client for text-to-image workflow submission.

    Defaults to pyiv ``UrllibHttpClient``. Tests may inject ``MemoryHttpClient``
    or an httpx ``Client`` that accepts ``json=``.
    """

    def __init__(
        self,
        settings: JuneSettings | ComfySettings | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 600.0,
        poll_interval: float = 1.0,
        client: HttpClient | Any | None = None,
    ) -> None:
        if isinstance(settings, JuneSettings):
            cfg = settings.comfy
            self.base_url = (base_url or cfg.base_url or "").rstrip("/")
            self.timeout = timeout if timeout != 600.0 else cfg.timeout
            self.poll_interval = (
                poll_interval if poll_interval != 1.0 else cfg.poll_interval
            )
        elif isinstance(settings, ComfySettings):
            self.base_url = (base_url or settings.base_url or "").rstrip("/")
            self.timeout = timeout if timeout != 600.0 else settings.timeout
            self.poll_interval = (
                poll_interval if poll_interval != 1.0 else settings.poll_interval
            )
        else:
            self.base_url = (base_url or "").rstrip("/")
            self.timeout = timeout
            self.poll_interval = poll_interval
        self._owns_client = client is None
        self._client = client or UrllibHttpClient(timeout=self.timeout)
        self.client_id = f"june-{uuid.uuid4().hex[:8]}"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _url(self, path: str) -> str:
        if not self.base_url:
            raise ValueError("comfy.base_url is not configured")
        return f"{self.base_url}{path}"

    def system_stats(self) -> dict[str, Any]:
        resp = self._client.get(self._url("/system_stats"))
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("system_stats must return an object")
        return payload

    def list_models(self, folder: str) -> list[str]:
        resp = self._client.get(self._url(f"/models/{folder}"))
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            raise ValueError(f"models/{folder} must return a list")
        return [str(item) for item in payload]

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        body = {"prompt": workflow, "client_id": self.client_id}
        resp = self._client.post(self._url("/prompt"), json=body)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("prompt response must be an object")
        if payload.get("error"):
            raise RuntimeError(f"comfy prompt error: {payload.get('error')}")
        node_errors = payload.get("node_errors") or {}
        if node_errors:
            raise RuntimeError(f"comfy node_errors: {node_errors}")
        prompt_id = str(payload.get("prompt_id") or "")
        if not prompt_id:
            raise RuntimeError(f"comfy prompt missing prompt_id: {payload}")
        return prompt_id

    def get_history(self, prompt_id: str) -> dict[str, Any] | None:
        resp = self._client.get(self._url(f"/history/{prompt_id}"))
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            return None
        item = payload.get(prompt_id)
        return item if isinstance(item, dict) else None

    def wait_for_job(self, prompt_id: str, *, timeout: float | None = None) -> ComfyJobResult:
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)
        while time.monotonic() < deadline:
            item = self.get_history(prompt_id)
            if item is not None:
                status = dict(item.get("status") or {})
                if status.get("status_str") == "error" or status.get("completed") is False:
                    messages = status.get("messages") or []
                    raise RuntimeError(f"comfy job failed: {messages}")
                if status.get("completed") is True or item.get("outputs"):
                    images = _images_from_outputs(dict(item.get("outputs") or {}))
                    return ComfyJobResult(
                        prompt_id=prompt_id,
                        images=images,
                        outputs=dict(item.get("outputs") or {}),
                        status=status,
                    )
            time.sleep(self.poll_interval)
        raise TimeoutError(f"comfy job timed out: {prompt_id}")

    def fetch_image(self, ref: ComfyImageRef) -> bytes:
        query = urlencode(ref.to_dict())
        resp = self._client.get(self._url(f"/view?{query}"))
        resp.raise_for_status()
        return resp.content

    def generate(
        self,
        workflow: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> tuple[ComfyJobResult, bytes]:
        """Queue workflow, wait, and return the first output image bytes."""
        prompt_id = self.queue_prompt(workflow)
        result = self.wait_for_job(prompt_id, timeout=timeout)
        if not result.images:
            raise RuntimeError(f"comfy job produced no images: {prompt_id}")
        data = self.fetch_image(result.images[0])
        if not data:
            raise RuntimeError(f"comfy image download empty: {result.images[0]}")
        return result, data


def _images_from_outputs(outputs: dict[str, Any]) -> list[ComfyImageRef]:
    images: list[ComfyImageRef] = []
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        for item in node_out.get("images") or []:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename") or "")
            if not filename:
                continue
            images.append(
                ComfyImageRef(
                    filename=filename,
                    subfolder=str(item.get("subfolder") or ""),
                    type=str(item.get("type") or "output"),
                )
            )
    return images
