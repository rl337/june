"""File-backed June settings bound through a prototyped pyiv Config.

Loads ``config.yaml`` then overlays process env / ``.env``. Promote a generic
file→Config helper into pyiv/pyiv-common only after this pattern stabilizes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pyiv import Config, get_injector

DEFAULT_CONFIG_NAMES = ("config.yaml", "june.yaml")


class JunesparkSettings(BaseModel):
    base_url: str | None = None
    api_key: str = "junespark"
    model: str | None = None
    timeout: float = 120.0


class ConsoleSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class ChatSettings(BaseModel):
    max_tool_turns: int = 4
    context_token_budget: int = 6000
    max_part_bytes: int = 5_000_000
    system_prompt: str = (
        "You are June, an application orchestrator assistant. Be concise and useful."
    )


class JuneSettings(BaseSettings):
    """Runtime settings for June (yaml + JUNE_/JUNESPARK_ env overlay)."""

    model_config = SettingsConfigDict(
        env_prefix="JUNE_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    data_dir: str | None = None
    junespark: JunesparkSettings = Field(default_factory=JunesparkSettings)
    console: ConsoleSettings = Field(default_factory=ConsoleSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)

    def require_junespark_base_url(self) -> str:
        url = (self.junespark.base_url or "").strip()
        if not url:
            raise ValueError(
                "junespark.base_url is required (set in config.yaml or "
                "JUNESPARK_BASE_URL / JUNE_JUNESPARK__BASE_URL)"
            )
        return url.rstrip("/")


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config file must be a mapping: {path}")
    return raw


def resolve_config_path(explicit: str | Path | None = None) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get("JUNE_CONFIG")
    if env:
        return Path(env)
    for name in DEFAULT_CONFIG_NAMES:
        candidate = Path.cwd() / name
        if candidate.is_file():
            return candidate
    return None


def load_settings(
    config_path: str | Path | None = None,
    *,
    env_file: str | Path | None = ".env",
) -> JuneSettings:
    """Merge yaml config with env/.env (env wins via pydantic-settings)."""
    path = resolve_config_path(config_path)
    yaml_data = _load_yaml(path) if path is not None else {}

    # Allow JUNESPARK_* aliases without nesting.
    alias_overlay: dict[str, Any] = {}
    if os.environ.get("JUNESPARK_BASE_URL"):
        alias_overlay.setdefault("junespark", {})["base_url"] = os.environ["JUNESPARK_BASE_URL"]
    if os.environ.get("JUNESPARK_API_KEY"):
        alias_overlay.setdefault("junespark", {})["api_key"] = os.environ["JUNESPARK_API_KEY"]
    if os.environ.get("JUNESPARK_MODEL"):
        alias_overlay.setdefault("junespark", {})["model"] = os.environ["JUNESPARK_MODEL"]
    if alias_overlay:
        yaml_data = _deep_merge(yaml_data, alias_overlay)

    env_path = None if env_file is None else Path(env_file)
    if env_path is not None and not env_path.is_file():
        env_path = None
    if env_path is not None:
        return JuneSettings(_env_file=str(env_path), **yaml_data)
    return JuneSettings(**yaml_data)


class JuneConfig(Config):
    """pyiv Config that binds a pre-built application graph from settings."""

    def __init__(
        self,
        settings: JuneSettings | None = None,
        *,
        config_path: str | Path | None = None,
        build: Callable[[JuneSettings], dict[type, Any]] | None = None,
    ) -> None:
        self._settings = settings or load_settings(config_path)
        self._build = build
        self._instances: dict[type, Any] = {}
        super().__init__()  # type: ignore[no-untyped-call]

    @property
    def settings(self) -> JuneSettings:
        return self._settings

    def configure(self) -> None:
        from june.bootstrap import build_app

        built: dict[type, Any] = (self._build or build_app)(self._settings)
        self._instances = built
        for abstract, instance in built.items():
            self.register_instance(abstract, instance)


def create_injector(
    settings: JuneSettings | None = None,
    *,
    config_path: str | Path | None = None,
) -> Any:
    """Build a pyiv injector for the June application graph."""
    return get_injector(JuneConfig(settings=settings, config_path=config_path))
