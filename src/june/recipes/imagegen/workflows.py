"""API-format ComfyUI workflows for models currently loaded on JuneSpark Comfy."""

from __future__ import annotations

from typing import Any, Literal

ImageBackend = Literal["qwen_image", "flux2"]

# Discovered on 192.168.1.21:8188 (ComfyUI 0.37.2).
QWEN_UNET = "qwen_image_2.1_int8_convrot.safetensors"
QWEN_CLIP = "qwen3vl_8b_int8_convrot.safetensors"
QWEN_VAE = "qwen_image_2.1_vae_bf16.safetensors"

FLUX2_UNET = "flux2_dev_fp8mixed.safetensors"
FLUX2_CLIP = "mistral_3_small_flux2_bf16.safetensors"
FLUX2_VAE = "flux2-vae.safetensors"


def build_qwen_image_t2i_workflow(
    *,
    prompt: str,
    negative_prompt: str = "",
    width: int = 768,
    height: int = 768,
    seed: int = 42,
    steps: int = 20,
    cfg: float = 1.0,
    filename_prefix: str = "june/qwen_image",
    unet_name: str = QWEN_UNET,
    clip_name: str = QWEN_CLIP,
    vae_name: str = QWEN_VAE,
) -> dict[str, Any]:
    """Text-to-image graph matching the host's Qwen Image 2.1 node set.

    ``TextEncodeQwenImage21`` emits positive/negative conditioning and a latent.
    Reference images are omitted (autogrow min=0) for pure T2I.
    """
    del width, height  # resolution is square-ish via encoder; latent comes from encode
    return {
        "unet": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "clip": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": clip_name,
                "type": "qwen_image",
                "device": "default",
            },
        },
        "vae": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
        },
        "encode": {
            "class_type": "TextEncodeQwenImage21",
            "inputs": {
                "clip": ["clip", 0],
                "vae": ["vae", 0],
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "resolution": 768,
            },
        },
        "sample": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["unet", 0],
                "positive": ["encode", 0],
                "negative": ["encode", 1],
                "latent_image": ["encode", 2],
                "seed": int(seed),
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "decode": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]},
        },
        "save": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["decode", 0],
                "filename_prefix": filename_prefix,
            },
        },
    }


def build_flux2_t2i_workflow(
    *,
    prompt: str,
    negative_prompt: str = "",
    width: int = 768,
    height: int = 768,
    seed: int = 42,
    steps: int = 20,
    cfg: float = 1.0,
    guidance: float = 3.5,
    filename_prefix: str = "june/flux2",
    unet_name: str = FLUX2_UNET,
    clip_name: str = FLUX2_CLIP,
    vae_name: str = FLUX2_VAE,
) -> dict[str, Any]:
    """Text-to-image graph for Flux2 using EmptyFlux2LatentImage + FluxGuidance."""
    return {
        "unet": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "clip": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": clip_name,
                "type": "flux2",
                "device": "default",
            },
        },
        "vae": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
        },
        "pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["clip", 0]},
        },
        "neg": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["clip", 0]},
        },
        "guide": {
            "class_type": "FluxGuidance",
            "inputs": {"conditioning": ["pos", 0], "guidance": float(guidance)},
        },
        "latent": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": 1,
            },
        },
        "sample": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["unet", 0],
                "positive": ["guide", 0],
                "negative": ["neg", 0],
                "latent_image": ["latent", 0],
                "seed": int(seed),
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "decode": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]},
        },
        "save": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["decode", 0],
                "filename_prefix": filename_prefix,
            },
        },
    }


def build_workflow(
    backend: ImageBackend,
    *,
    prompt: str,
    negative_prompt: str = "",
    width: int = 768,
    height: int = 768,
    seed: int = 42,
    steps: int = 20,
    **kwargs: Any,
) -> dict[str, Any]:
    if backend == "qwen_image":
        return build_qwen_image_t2i_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            steps=steps,
            **kwargs,
        )
    if backend == "flux2":
        return build_flux2_t2i_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            steps=steps,
            **kwargs,
        )
    raise ValueError(f"unknown image backend: {backend!r}")
