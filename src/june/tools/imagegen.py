"""``generate_image`` tool soft-point for the interactive chat recipe."""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import uuid4

from june.config import JuneSettings
from june.documents import DocumentRef, DocumentStore
from june.recipes.imagegen.generators import FixedImageGenerator, ImageGenerator
from june.recipes.imagegen.problem import ImageProblem
from june.recipes.imagegen.run import (
    DEFAULT_CRITERIA_MAX_RETRIES,
    run_imagegen_recipe,
)
from june.tools import ToolRegistry, ToolSpec


def register_generate_image_tool(
    registry: ToolRegistry,
    *,
    documents: DocumentStore | None = None,
    settings: JuneSettings | None = None,
    generator: ImageGenerator | None = None,
) -> None:
    """Register chat tool that binds ``june.imagegen`` and returns media JSON."""

    def generate_image(args: dict[str, Any]) -> str:
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return json.dumps({"error": "prompt is required"})
        recipe = str(args.get("recipe") or "oneshot").strip() or "oneshot"
        if recipe not in {"oneshot", "criteria_refine"}:
            return json.dumps(
                {"error": "recipe must be oneshot or criteria_refine"}
            )
        backend = str(args.get("backend") or "qwen_image").strip() or "qwen_image"
        max_retries = int(args.get("max_retries") or DEFAULT_CRITERIA_MAX_RETRIES)
        negative = str(args.get("negative_prompt") or "")
        width = int(args.get("width") or 768)
        height = int(args.get("height") or 768)

        problem = ImageProblem(
            id=f"chat-{uuid4().hex[:8]}",
            title="chat generate_image",
            prompt=prompt,
            negative_prompt=negative,
            backend=backend,  # type: ignore[arg-type]
            width=width,
            height=height,
            metadata={"source": "chat_tool", "recipe": recipe},
        )

        gen = generator
        if gen is None:
            gen = _live_or_fixed_generator(settings)

        kwargs: dict[str, Any] = {"recipe": recipe}
        if recipe == "criteria_refine":
            from june.recipes.imagegen.critics import FixedPromptCrafter
            from june.recipes.imagegen.evaluate import FixedImageEvaluator

            kwargs["crafter"] = FixedPromptCrafter()
            kwargs["evaluator"] = FixedImageEvaluator(
                results=None  # default fail-then-pass for offline; live overridden below
            )
            kwargs["max_retries"] = max_retries
            # Live path: bind Junespark expand/score when configured.
            live_eval = _try_bound_evaluator(settings)
            if live_eval is not None:
                kwargs["crafter"] = live_eval[0]
                kwargs["evaluator"] = live_eval[1]

        result = run_imagegen_recipe(problem, gen, **kwargs)
        if not result.image_bytes:
            return json.dumps(
                {
                    "ok": False,
                    "error": result.error or "no_image",
                    "failures": result.failures,
                    "recipe": recipe,
                }
            )

        media = _persist_or_data_url(
            result.image_bytes,
            documents=documents,
            name=f"{problem.id}.png",
        )
        return json.dumps(
            {
                "ok": bool(result.ok or result.image_bytes),
                "recipe": recipe,
                "backend": backend,
                "verified": result.verified,
                "image_prompt": result.image_prompt,
                "media": media,
                "failures": result.failures,
            }
        )

    registry.register(
        ToolSpec(
            name="generate_image",
            description=(
                "Generate an image with June's incubating imagegen recipe "
                "(Comfy oneshot or criteria_refine). Returns a media part for "
                "the chat reply."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "negative_prompt": {"type": "string"},
                    "recipe": {
                        "type": "string",
                        "enum": ["oneshot", "criteria_refine"],
                    },
                    "backend": {
                        "type": "string",
                        "enum": ["qwen_image", "flux2"],
                    },
                    "max_retries": {"type": "integer"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                },
                "required": ["prompt"],
            },
            handler=generate_image,
        )
    )


def _live_or_fixed_generator(settings: JuneSettings | None) -> ImageGenerator:
    if settings is not None and (settings.comfy.base_url or "").strip():
        from june.providers.comfy import ComfyProvider
        from june.recipes.imagegen.generators import ComfyImageGenerator

        return ComfyImageGenerator(ComfyProvider(settings))
    return FixedImageGenerator()


def _try_bound_evaluator(
    settings: JuneSettings | None,
) -> tuple[Any, Any] | None:
    if settings is None or not (settings.junespark.base_url or "").strip():
        return None
    try:
        from june.providers.junespark import JunesparkProvider
        from june.recipes.imagegen.acceptance import (
            JunesparkAcceptanceSpecCrafter,
            JunesparkCriteriaScorer,
        )
        from june.recipes.imagegen.critics import JunesparkPromptCrafter
        from june.recipes.imagegen.evaluate import BoundEvaluateCriteria

        provider = JunesparkProvider(settings)
        text_model = settings.junespark.model
        crafter = JunesparkPromptCrafter(provider, model=text_model)
        evaluator = BoundEvaluateCriteria(
            JunesparkAcceptanceSpecCrafter(provider, model=text_model),
            JunesparkCriteriaScorer(provider, model=text_model),
        )
        return crafter, evaluator
    except Exception:  # noqa: BLE001
        return None


def _persist_or_data_url(
    image: bytes,
    *,
    documents: DocumentStore | None,
    name: str,
) -> dict[str, Any]:
    b64 = base64.b64encode(image).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"
    if documents is None:
        return {
            "kind": "image",
            "url": data_url,
            "media_type": "image/png",
            "name": name,
        }
    ref = DocumentRef(
        id=f"img-{uuid4().hex[:12]}",
        title=name,
        media_type="image/png",
        provenance={"source": "generate_image"},
    )
    documents.put(ref, data_url)
    return {
        "kind": "image",
        "document_id": ref.id,
        "media_type": "image/png",
        "name": name,
        "url": data_url,
    }
