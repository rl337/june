"""Committed image fixtures for imagegen critique / anomaly tests."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

RAIN_BIKE_HYDRANT_MALFORMED = "rain_bike_hydrant_malformed"
RAIN_BIKE_CLEAN_POSITIVE = "rain_bike_clean_positive"


def fixtures_dir() -> Path:
    """Resolve ``tests/fixtures/imagegen`` from checkout or integration CWD.

    In the integration container june is installed into site-packages, so
    walking from ``__file__`` never reaches ``/app/tests``. Prefer an explicit
    override, then CWD (pytest ``/app``), then source-tree parents.
    """
    candidates: list[Path] = []
    override = (os.environ.get("JUNE_IMAGEGEN_FIXTURES") or "").strip()
    if override:
        candidates.append(Path(override))
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidates.append(parent / "tests" / "fixtures" / "imagegen")
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "tests" / "fixtures" / "imagegen")
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "tests/fixtures/imagegen not found "
        f"(cwd={cwd}, module={here}; set JUNE_IMAGEGEN_FIXTURES or run from checkout)"
    )


def fixture_path(name: str = RAIN_BIKE_HYDRANT_MALFORMED) -> Path:
    path = fixtures_dir() / f"{name}.png"
    if not path.is_file():
        raise FileNotFoundError(f"missing imagegen fixture: {path}")
    return path


@lru_cache(maxsize=8)
def load_fixture_bytes(name: str = RAIN_BIKE_HYDRANT_MALFORMED) -> bytes:
    return fixture_path(name).read_bytes()


@lru_cache(maxsize=8)
def load_fixture_meta(name: str = RAIN_BIKE_HYDRANT_MALFORMED) -> dict[str, Any]:
    path = fixtures_dir() / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing imagegen fixture meta: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"fixture meta must be an object: {path}")
    return payload


def load_fixture_views(name: str = RAIN_BIKE_HYDRANT_MALFORMED) -> dict[str, bytes]:
    """Load named PNG views from fixture meta (excludes the primary ``full`` image)."""
    meta = load_fixture_meta(name)
    root = fixtures_dir()
    views: dict[str, bytes] = {}
    for item in meta.get("views") or []:
        if not isinstance(item, dict):
            continue
        view_name = str(item.get("name") or "")
        filename = str(item.get("file") or "")
        if not view_name or not filename or view_name == "full":
            continue
        path = root / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing fixture view: {path}")
        views[view_name] = path.read_bytes()
    return views


