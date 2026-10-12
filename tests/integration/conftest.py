"""Integration fixtures: offline stubs + optional live JuneSpark / Comfy."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from june.config import JuneSettings, load_settings
from june.providers.comfy import ComfyProvider
from june.providers.junespark import JunesparkProvider
from june.recipes.codegen import FixedScriptCompleter, JunesparkCodegenCompleter
from june.recipes.imagegen import (
    ComfyImageGenerator,
    JunesparkPromptCrafter,
    JunesparkVisionCritic,
)
from tests.integration.artifacts import artifact_dir_for


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: end-to-end recipe tests intended to run in the integration container",
    )
    config.addinivalue_line(
        "markers",
        "junespark_live: requires JUNESPARK_BASE_URL (or config) reaching a live model",
    )
    config.addinivalue_line(
        "markers",
        "comfy_live: requires COMFY_BASE_URL (or config) reaching a live ComfyUI",
    )
    config.addinivalue_line(
        "markers",
        "vision_live: requires a reachable multimodal VL chat model",
    )


@pytest.fixture
def artifact_dir(request: pytest.FixtureRequest) -> Path:
    """Per-test directory under host ``artifacts/`` ↔ container ``/artifacts``."""
    family = "imagegen" if "imagegen" in request.node.nodeid else "codegen"
    return artifact_dir_for(request.node.name, family=family)


@pytest.fixture
def fixed_completer() -> FixedScriptCompleter:
    return FixedScriptCompleter()


@pytest.fixture
def junespark_settings() -> JuneSettings | None:
    base = (os.environ.get("JUNESPARK_BASE_URL") or "").strip()
    if not base:
        try:
            settings = load_settings()
        except Exception:
            return None
        if not (settings.junespark.base_url or "").strip():
            return None
        return settings
    return load_settings()


@pytest.fixture
def junespark_completer(junespark_settings: JuneSettings | None) -> JunesparkCodegenCompleter:
    if junespark_settings is None:
        pytest.skip("JUNESPARK_BASE_URL / junespark.base_url not configured")
    provider = JunesparkProvider(junespark_settings)
    model = os.environ.get("JUNESPARK_MODEL") or junespark_settings.junespark.model
    return JunesparkCodegenCompleter(provider, model=model)


@pytest.fixture
def comfy_settings() -> JuneSettings | None:
    base = (os.environ.get("COMFY_BASE_URL") or "").strip()
    if not base:
        try:
            settings = load_settings()
        except Exception:
            return None
        if not (settings.comfy.base_url or "").strip():
            return None
        return settings
    return load_settings()


@pytest.fixture
def comfy_generator(comfy_settings: JuneSettings | None) -> ComfyImageGenerator:
    if comfy_settings is None:
        pytest.skip("COMFY_BASE_URL / comfy.base_url not configured")
    # Prefer urllib when JUNE_COMFY_URLLIB=1 (some agent sandboxes allowlist it).
    client = None
    if (os.environ.get("JUNE_COMFY_URLLIB") or "").strip() in {"1", "true", "yes"}:
        from june.providers.comfy import UrllibHttpClient

        client = UrllibHttpClient(timeout=comfy_settings.comfy.timeout)
    provider = ComfyProvider(comfy_settings, client=client)
    return ComfyImageGenerator(provider)


@pytest.fixture
def local_junespark_provider() -> JunesparkProvider:
    """LM Studio / local OpenAI-compat provider for text + VL soft points."""
    base = (os.environ.get("JUNESPARK_BASE_URL") or "http://127.0.0.1:1234/v1").strip()
    return JunesparkProvider(base_url=base, api_key="lmstudio", timeout=180.0)


@pytest.fixture
def prompt_crafter(local_junespark_provider: JunesparkProvider) -> JunesparkPromptCrafter:
    model = os.environ.get("JUNE_TEXT_MODEL") or "qwen/qwen3.6-35b-a3b"
    return JunesparkPromptCrafter(local_junespark_provider, model=model)


@pytest.fixture
def vision_critic(local_junespark_provider: JunesparkProvider) -> JunesparkVisionCritic:
    model = os.environ.get("JUNE_VL_MODEL") or "qwen/qwen3-vl-8b"
    return JunesparkVisionCritic(local_junespark_provider, model=model)
