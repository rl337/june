"""Image generators for the imagegen recipe (fixture offline or live Comfy)."""

from __future__ import annotations

import struct
import zlib
from typing import Any, Protocol

from june.providers.comfy import ComfyProvider
from june.recipes.imagegen.workflows import ImageBackend, build_workflow

# 1x1 opaque PNG (stdlib-only fixture for offline CI).
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def minimal_png_bytes(
    *,
    width: int = 64,
    height: int = 64,
    rgb: tuple[int, int, int] = (40, 120, 200),
) -> bytes:
    """Build a solid-color PNG without third-party deps."""
    r, g, b = rgb
    raw = b"".join(b"\x00" + bytes([r, g, b]) * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        _PNG_SIG
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


class ImageGenerator(Protocol):
    turns: list[dict[str, Any]]

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        backend: ImageBackend = "qwen_image",
        width: int = 768,
        height: int = 768,
        seed: int = 42,
        steps: int = 20,
    ) -> bytes: ...


class FixedImageGenerator:
    """Offline DI stub that returns a deterministic PNG."""

    def __init__(self, image: bytes | None = None) -> None:
        self.image = image if image is not None else minimal_png_bytes()
        self.turns: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        backend: ImageBackend = "qwen_image",
        width: int = 768,
        height: int = 768,
        seed: int = 42,
        steps: int = 20,
    ) -> bytes:
        self.turns.append(
            {
                "index": len(self.turns),
                "generator": "fixed",
                "request": {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "backend": backend,
                    "width": width,
                    "height": height,
                    "seed": seed,
                    "steps": steps,
                },
                "response": {"bytes": len(self.image), "format": "png"},
            }
        )
        return self.image


class ComfyImageGenerator:
    """Live generator that submits a backend-specific Comfy workflow."""

    def __init__(self, provider: ComfyProvider) -> None:
        self.provider = provider
        self.turns: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        backend: ImageBackend = "qwen_image",
        width: int = 768,
        height: int = 768,
        seed: int = 42,
        steps: int = 20,
    ) -> bytes:
        workflow = build_workflow(
            backend,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            steps=steps,
        )
        result, data = self.provider.generate(workflow)
        self.turns.append(
            {
                "index": len(self.turns),
                "generator": "comfy",
                "request": {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "backend": backend,
                    "width": width,
                    "height": height,
                    "seed": seed,
                    "steps": steps,
                    "workflow": workflow,
                },
                "response": {
                    "prompt_id": result.prompt_id,
                    "images": [ref.to_dict() for ref in result.images],
                    "bytes": len(data),
                    "status": result.status,
                },
            }
        )
        return data
