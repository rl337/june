"""Extract Python script(s) from a model response; enforce stdlib-only imports."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable

_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_FENCE_PATH_RE = re.compile(
    r"```(?:python|py)?[^\n]*?\bpath\s*=\s*([^\s`]+)[^\n]*\n(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
_FILE_HEADER_RE = re.compile(
    r"^\s*#\s*file:\s*(\S+)\s*\n(.*)$",
    re.IGNORECASE | re.DOTALL,
)

# Fallback when sys.stdlib_module_names is unavailable (Python < 3.10).
_FALLBACK_STDLIB = frozenset(
    {
        "__future__",
        "abc",
        "argparse",
        "array",
        "ast",
        "asyncio",
        "base64",
        "bisect",
        "builtins",
        "calendar",
        "collections",
        "contextlib",
        "copy",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "functools",
        "hashlib",
        "heapq",
        "io",
        "itertools",
        "json",
        "math",
        "operator",
        "os",
        "pathlib",
        "queue",
        "random",
        "re",
        "statistics",
        "string",
        "struct",
        "sys",
        "tempfile",
        "textwrap",
        "time",
        "typing",
        "unicodedata",
        "uuid",
    }
)


def extract_python_script(text: str) -> str:
    """Return the first fenced python block, or the stripped raw text if unfenced."""
    match = _FENCE_RE.search(text or "")
    if match:
        script = match.group(1).strip() + "\n"
    else:
        stripped = (text or "").strip()
        if not stripped:
            raise ValueError("empty model response; no python script found")
        if "```" in stripped:
            raise ValueError("malformed fenced block in model response")
        script = stripped + "\n"
    assert_stdlib_only(script)
    return script


def extract_python_files(
    text: str,
    *,
    require_main: bool = True,
    min_files: int = 2,
    allowed_local_packages: Iterable[str] | None = None,
) -> dict[str, str]:
    """Extract path-annotated python fences into a relative path → source map."""
    files: dict[str, str] = {}
    for match in _FENCE_PATH_RE.finditer(text or ""):
        path = _normalize_path(match.group(1))
        body = match.group(2).strip() + "\n"
        files[path] = body

    if not files:
        # Fallback: fences whose first line is `# file: path`.
        for match in _FENCE_RE.finditer(text or ""):
            body = match.group(1)
            header = _FILE_HEADER_RE.match(body)
            if not header:
                continue
            path = _normalize_path(header.group(1))
            files[path] = header.group(2).strip() + "\n"

    if len(files) < min_files:
        raise ValueError(
            f"expected at least {min_files} path-annotated python files, got {len(files)}"
        )
    if require_main and not any(path.endswith("__main__.py") for path in files):
        raise ValueError("package extract requires a __main__.py file")

    local = set(allowed_local_packages or ())
    for path in files:
        top = path.split("/", 1)[0]
        if top.endswith(".py"):
            continue
        local.add(top)

    for _path, source in files.items():
        assert_stdlib_only(source, allowed_local_packages=local)
    return files


def assert_stdlib_only(
    source: str,
    *,
    allowed_local_packages: Iterable[str] | None = None,
) -> None:
    """Raise ValueError if ``source`` imports anything outside the stdlib (+ locals)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"generated code is not valid Python: {exc}") from exc

    allowed_local = {name.split(".")[0] for name in (allowed_local_packages or ())}
    stdlib = _stdlib_module_names()
    banned: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if not _is_allowed_import(root, stdlib=stdlib, local=allowed_local):
                    banned.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import within the generated package.
                continue
            if not node.module:
                continue
            root = node.module.split(".", 1)[0]
            if not _is_allowed_import(root, stdlib=stdlib, local=allowed_local):
                banned.append(node.module)

    if banned:
        raise ValueError(
            "non-stdlib imports are not allowed: " + ", ".join(sorted(set(banned)))
        )


def _is_allowed_import(
    root: str, *, stdlib: frozenset[str], local: set[str]
) -> bool:
    if root in stdlib or root in local:
        return True
    return False


def _stdlib_module_names() -> frozenset[str]:
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return frozenset(names) | {"__future__"}
    return _FALLBACK_STDLIB


def _normalize_path(path: str) -> str:
    cleaned = path.strip().strip("\"'")
    cleaned = cleaned.lstrip("./")
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise ValueError(f"invalid generated file path: {path!r}")
    return cleaned
