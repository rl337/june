"""Unit tests for imagegen workflows / verify (no Comfy / network)."""

from __future__ import annotations

from june.recipes.imagegen import (
    build_flux2_t2i_workflow,
    build_qwen_image_t2i_workflow,
    minimal_png_bytes,
)
from june.recipes.imagegen.verify import verify_image_bytes


def test_minimal_png_verifies() -> None:
    data = minimal_png_bytes(width=32, height=32)
    assert verify_image_bytes(data, min_bytes=16) == []


def test_verify_rejects_empty() -> None:
    assert verify_image_bytes(b"", min_bytes=1)[0]["reason"] == "empty_image"


def test_qwen_workflow_shape() -> None:
    wf = build_qwen_image_t2i_workflow(prompt="a red apple")
    assert wf["unet"]["inputs"]["unet_name"].startswith("qwen_image")
    assert wf["clip"]["inputs"]["type"] == "qwen_image"
    assert wf["encode"]["class_type"] == "TextEncodeQwenImage21"
    assert "images.image_1" not in wf["encode"]["inputs"]
    assert wf["sample"]["inputs"]["latent_image"] == ["encode", 2]


def test_flux2_workflow_shape() -> None:
    wf = build_flux2_t2i_workflow(prompt="a red apple")
    assert wf["unet"]["inputs"]["unet_name"].startswith("flux2")
    assert wf["clip"]["inputs"]["type"] == "flux2"
    assert wf["latent"]["class_type"] == "EmptyFlux2LatentImage"
    assert wf["guide"]["class_type"] == "FluxGuidance"
