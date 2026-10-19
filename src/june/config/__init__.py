"""File-backed June settings bound through a prototyped pyiv Config.

Loads ``config.yaml`` then overlays process env / ``.env``. Promote a generic
file→Config helper into pyiv/pyiv-common only after this pattern stabilizes.

``JuneConfig`` registers pyiv ≥ 1.1 use-case injectables (``Environment``,
time, files, log, ``HttpClient``) so hosts/tests can override via
``register_instance`` / ``pyiv.override`` instead of monkeypatching OS edges.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pyiv import Config, get_injector
from pyiv.files import Filesystem, RealFilesystem
from pyiv.http import HttpClient, UrllibHttpClient
from pyiv.log import LoggerFactory, StdlibLoggerFactory
from pyiv.process import Environment, OsEnvironment
from pyiv.time import Clock, DateTimeService, PythonDateTimeService, RealClock

DEFAULT_CONFIG_NAMES = ("config.yaml", "june.yaml")


class JunesparkSettings(BaseModel):
    base_url: str | None = None
    api_key: str = "junespark"
    model: str | None = None
    timeout: float = 120.0


class ComfySettings(BaseModel):
    """ComfyUI media backend (Flux / Qwen Image workflows)."""

    base_url: str | None = None
    timeout: float = 600.0
    poll_interval: float = 1.0


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
    comfy: ComfySettings = Field(default_factory=ComfySettings)
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

    def require_comfy_base_url(self) -> str:
        url = (self.comfy.base_url or "").strip()
        if not url:
            raise ValueError(
                "comfy.base_url is required (set in config.yaml or "
                "COMFY_BASE_URL / JUNE_COMFY__BASE_URL)"
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


def _load_yaml(path: Path, *, filesystem: Filesystem | None = None) -> dict[str, Any]:
    fs = filesystem or RealFilesystem()
    if not fs.is_file(str(path)):
        return {}
    raw = yaml.safe_load(fs.read_text(str(path))) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config file must be a mapping: {path}")
    return raw


def resolve_config_path(
    explicit: str | Path | None = None,
    *,
    env: Environment | None = None,
    filesystem: Filesystem | None = None,
) -> Path | None:
    fs = filesystem or RealFilesystem()
    environment = env or OsEnvironment()
    if explicit is not None:
        return Path(explicit)
    config_env = environment.get("JUNE_CONFIG")
    if config_env:
        return Path(config_env)
    for name in DEFAULT_CONFIG_NAMES:
        candidate = Path.cwd() / name
        if fs.is_file(str(candidate)):
            return candidate
    return None


def _alias_overlay_from_env(env: Environment) -> dict[str, Any]:
    """Allow JUNESPARK_* / COMFY_* aliases without nesting."""
    alias_overlay: dict[str, Any] = {}
    if env.get("JUNESPARK_BASE_URL"):
        alias_overlay.setdefault("junespark", {})["base_url"] = env.get("JUNESPARK_BASE_URL")
    if env.get("JUNESPARK_API_KEY"):
        alias_overlay.setdefault("junespark", {})["api_key"] = env.get("JUNESPARK_API_KEY")
    if env.get("JUNESPARK_MODEL"):
        alias_overlay.setdefault("junespark", {})["model"] = env.get("JUNESPARK_MODEL")
    if env.get("COMFY_BASE_URL"):
        alias_overlay.setdefault("comfy", {})["base_url"] = env.get("COMFY_BASE_URL")
    return alias_overlay


def load_settings(
    config_path: str | Path | None = None,
    *,
    env_file: str | Path | None = ".env",
    env: Environment | None = None,
    filesystem: Filesystem | None = None,
) -> JuneSettings:
    """Merge yaml config with env/.env (env wins via pydantic-settings)."""
    environment = env or OsEnvironment()
    fs = filesystem or RealFilesystem()
    path = resolve_config_path(config_path, env=environment, filesystem=fs)
    yaml_data = _load_yaml(path, filesystem=fs) if path is not None else {}

    alias_overlay = _alias_overlay_from_env(environment)
    if alias_overlay:
        yaml_data = _deep_merge(yaml_data, alias_overlay)

    env_path = None if env_file is None else Path(env_file)
    if env_path is not None and not fs.is_file(str(env_path)):
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
        env: Environment | None = None,
        filesystem: Filesystem | None = None,
    ) -> None:
        self._env = env
        self._filesystem = filesystem
        self._settings = settings or load_settings(
            config_path,
            env=env,
            filesystem=filesystem,
        )
        self._build = build
        self._instances: dict[type, Any] = {}
        super().__init__()  # type: ignore[no-untyped-call]

    @property
    def settings(self) -> JuneSettings:
        return self._settings

    def configure(self) -> None:
        from june.bootstrap import build_app

        # pyiv ≥ 1.1 use-case injectables (same leaf edges MechaHarness registers).
        self.register_instance(Environment, self._env or OsEnvironment())
        self.register(DateTimeService, PythonDateTimeService, singleton=True)
        self.register_instance(Filesystem, self._filesystem or RealFilesystem())
        self.register(Clock, RealClock, singleton=True)
        self.register(LoggerFactory, StdlibLoggerFactory, singleton=True)
        http = UrllibHttpClient(timeout=self._settings.junespark.timeout)
        self.register_instance(HttpClient, http)

        if self._build is not None:
            built = self._build(self._settings)
        else:
            built = build_app(self._settings, http_client=http)
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
