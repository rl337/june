"""Fixed image-generation problems for the imagegen integration suite."""

from __future__ import annotations

from dataclasses import dataclass, field

from june.recipes.imagegen.workflows import ImageBackend


@dataclass(frozen=True)
class ImageProblem:
    """A deterministic text-to-image task with lightweight verify constraints."""

    id: str
    title: str
    prompt: str
    negative_prompt: str = ""
    backend: ImageBackend = "qwen_image"
    width: int = 768
    height: int = 768
    seed: int = 42
    steps: int = 20
    min_bytes: int = 64
    require_png: bool = True
    required: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ("text", "watermark", "logo")
    metadata: dict[str, str] = field(default_factory=dict)

    def prompt_text(self) -> str:
        req = ", ".join(self.required) if self.required else "(none)"
        ban = ", ".join(self.forbidden) if self.forbidden else "(none)"
        return (
            f"# {self.title}\n\n"
            f"Backend: {self.backend}\n"
            f"Size: {self.width}x{self.height}\n"
            f"Seed: {self.seed}\n"
            f"Steps: {self.steps}\n"
            f"Required elements: {req}\n"
            f"Forbidden elements: {ban}\n\n"
            f"Positive prompt / goal:\n{self.prompt.strip()}\n\n"
            f"Negative prompt:\n{self.negative_prompt.strip() or '(none)'}\n"
        )


SIMPLE_STILL_LIFE_QWEN = ImageProblem(
    id="still_life_qwen",
    title="Simple still life (Qwen Image)",
    prompt=(
        "A simple ceramic bowl of red apples on a wooden table, soft daylight, "
        "clean composition, no text, no watermark."
    ),
    negative_prompt="text, watermark, logo, blurry, low quality",
    backend="qwen_image",
    width=768,
    height=768,
    steps=12,
    required=("ceramic bowl", "red apples", "wooden table"),
    metadata={"backend": "qwen_image", "kind": "t2i"},
)


SIMPLE_STILL_LIFE_FLUX2 = ImageProblem(
    id="still_life_flux2",
    title="Simple still life (Flux2)",
    prompt=(
        "A simple ceramic bowl of red apples on a wooden table, soft daylight, "
        "clean composition, no text, no watermark."
    ),
    negative_prompt="text, watermark, logo, blurry, low quality",
    backend="flux2",
    width=768,
    height=768,
    steps=12,
    required=("ceramic bowl", "red apples", "wooden table"),
    metadata={"backend": "flux2", "kind": "t2i"},
)


# Classic diffusion failure mode: finger count / hand geometry.
HAND_FIVE_FINGERS = ImageProblem(
    id="hand_five_fingers",
    title="Hand with five digits holding a red apple",
    prompt=(
        "Photoreal close-up of a single adult human right hand holding a shiny red "
        "apple. The hand has exactly five digits total: one thumb and four fingers, "
        "correct human anatomy, natural skin texture, soft window light, plain solid "
        "background, no extra limbs, no text."
    ),
    negative_prompt=(
        "extra fingers, six fingers, missing fingers, fused fingers, mutated hands, "
        "extra hands, text, watermark, logo, blurry, low quality"
    ),
    backend="qwen_image",
    width=768,
    height=768,
    steps=16,
    seed=11,
    required=(
        "exactly one human hand",
        "exactly five digits total (one thumb and four fingers)",
        "red apple held by the hand",
    ),
    forbidden=("text", "watermark", "logo", "extra hands", "extra fingers"),
    metadata={"backend": "qwen_image", "kind": "t2i_criteria_refine"},
)


# Deliberately specific so a vague first prompt may fail VL critique once.
RAIN_BIKE_HYDRANT = ImageProblem(
    id="rain_bike_hydrant",
    title="Red bike and yellow hydrant in rain",
    prompt=(
        "Urban sidewalk scene: a red bicycle leaning against a bright yellow fire "
        "hydrant during rainfall, wet pavement reflections, overcast daylight, "
        "photoreal, no people, no text."
    ),
    negative_prompt="people, text, watermark, logo, sunny clear sky, dry pavement",
    backend="qwen_image",
    width=768,
    height=768,
    steps=16,
    seed=7,
    required=(
        "red bicycle",
        "yellow fire hydrant",
        "rain or wet pavement",
    ),
    forbidden=("text", "watermark", "logo", "people"),
    metadata={"backend": "qwen_image", "kind": "t2i_critique"},
)


def problem_by_id(problem_id: str) -> ImageProblem:
    catalog = {
        SIMPLE_STILL_LIFE_QWEN.id: SIMPLE_STILL_LIFE_QWEN,
        SIMPLE_STILL_LIFE_FLUX2.id: SIMPLE_STILL_LIFE_FLUX2,
        RAIN_BIKE_HYDRANT.id: RAIN_BIKE_HYDRANT,
        HAND_FIVE_FINGERS.id: HAND_FIVE_FINGERS,
    }
    try:
        return catalog[problem_id]
    except KeyError as exc:
        raise ValueError(f"unknown image problem id: {problem_id!r}") from exc
