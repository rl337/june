"""Integration fixtures: offline fixed completer + optional live JuneSpark."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from june.config import JuneSettings, load_settings
from june.providers.junespark import JunesparkProvider
from june.recipes.codegen import FixedScriptCompleter, JunesparkCodegenCompleter
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


@pytest.fixture
def artifact_dir(request: pytest.FixtureRequest) -> Path:
    """Per-test directory under host ``artifacts/`` ↔ container ``/artifacts``."""
    return artifact_dir_for(request.node.name)


@pytest.fixture
def fixed_completer() -> FixedScriptCompleter:
    return FixedScriptCompleter()


@pytest.fixture
def junespark_settings() -> JuneSettings | None:
    base = (os.environ.get("JUNESPARK_BASE_URL") or "").strip()
    if not base:
        # Allow config.yaml when present (operator laptop / compose mount).
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
