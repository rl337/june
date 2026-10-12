"""Durable artifact directory for the integration suite (host ↔ /artifacts)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from june.recipes.codegen.completers import CodegenCompleter
from june.recipes.codegen.graph import RecipeKind
from june.recipes.codegen.problem import CodingProblem
from june.recipes.codegen.run import CodegenRecipeResult, run_codegen_recipe

DEFAULT_CONTAINER_ARTIFACTS = "/artifacts"
DEFAULT_HOST_ARTIFACTS = "artifacts"


def artifacts_root() -> Path:
    """Resolve the suite artifact root.

    Preference order:
    1. ``JUNE_INTEGRATION_ARTIFACTS``
    2. ``/artifacts`` when ``JUNE_INTEGRATION=1`` (container default)
    3. ``./artifacts`` relative to the process cwd (local pytest)
    """
    override = (os.environ.get("JUNE_INTEGRATION_ARTIFACTS") or "").strip()
    if override:
        root = Path(override)
    elif (os.environ.get("JUNE_INTEGRATION") or "").strip() in {"1", "true", "yes"}:
        root = Path(DEFAULT_CONTAINER_ARTIFACTS)
    else:
        root = Path(DEFAULT_HOST_ARTIFACTS)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_dir_for(test_name: str, *, family: str = "codegen") -> Path:
    """Per-test directory under the artifact root (latest run overwrites)."""
    safe = re.sub(r"[^\w.\-]+", "_", test_name).strip("_") or "test"
    path = artifacts_root() / family / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_codegen_with_artifacts(
    problem: CodingProblem,
    completer: CodegenCompleter,
    artifact_dir: Path,
    *,
    recipe: RecipeKind = "oneshot",
    grants: list[object] | None = None,
) -> CodegenRecipeResult:
    """Run the recipe and always persist a full inspectable artifact bundle."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result = run_codegen_recipe(
        problem,
        completer,
        recipe=recipe,
        checkpoint_path=str(artifact_dir / "checkpoint.sqlite"),
        grants=grants,
    )
    write_codegen_artifacts(artifact_dir, result)
    return result


def write_codegen_artifacts(directory: Path, result: CodegenRecipeResult) -> None:
    """Persist the full inspectable bundle for a codegen recipe run."""
    directory.mkdir(parents=True, exist_ok=True)

    _write_text(directory / "prompt.txt", result.prompt or "")
    _write_text(directory / "raw_response.txt", result.raw_response or "")
    _write_text(directory / "script.py", result.script or "")
    if result.refine_prompt:
        _write_text(directory / "refine_prompt.txt", result.refine_prompt)

    files_dir = directory / "files"
    if result.files:
        if files_dir.exists():
            for stale in files_dir.rglob("*"):
                if stale.is_file():
                    stale.unlink()
        for rel, source in result.files.items():
            path = files_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")

    _write_json(directory / "result.json", _result_summary(result))
    _write_json(directory / "events.json", result.events)
    _write_jsonl(directory / "events.jsonl", result.events)
    _write_json(directory / "graph.json", result.graph)
    _write_json(directory / "turns.json", result.turns)
    _write_jsonl(directory / "turns.jsonl", result.turns)
    _write_json(directory / "execute_results.json", result.run_results)
    _write_json(directory / "failures.json", result.failures)
    _write_json(directory / "diagnostics.json", result.diagnostics)
    _write_json(directory / "access_checks.json", result.access_checks)
    _write_json(directory / "node_statuses.json", result.node_statuses)
    _write_json(directory / "event_types.json", result.event_types)
    if result.execute_command is not None:
        _write_json(directory / "execute_command.json", result.execute_command)
    _write_text(directory / "MANIFEST.md", _manifest(result))


def _result_summary(result: CodegenRecipeResult) -> dict[str, Any]:
    file_list = [
        "MANIFEST.md",
        "result.json",
        "events.json",
        "events.jsonl",
        "graph.json",
        "turns.json",
        "turns.jsonl",
        "prompt.txt",
        "raw_response.txt",
        "script.py",
        "execute_results.json",
        "failures.json",
        "diagnostics.json",
        "access_checks.json",
        "node_statuses.json",
        "event_types.json",
        "checkpoint.sqlite",
    ]
    if result.refine_prompt:
        file_list.append("refine_prompt.txt")
    if result.files:
        file_list.append("files/")
    if result.execute_command is not None:
        file_list.append("execute_command.json")
    return {
        "status": result.status,
        "ok": result.ok,
        "recipe": result.recipe,
        "problem_id": result.problem_id,
        "run_id": result.run_id,
        "verified": result.verified,
        "first_pass_verified": result.first_pass_verified,
        "error": result.error,
        "graph_status": result.graph_status,
        "budget_spent": result.budget_spent,
        "budget_level": result.budget_level,
        "checkpoint_durability": result.checkpoint_durability,
        "checkpoint_path": "checkpoint.sqlite",
        "package_name": result.package_name,
        "execute_command": result.execute_command,
        "turn_count": len(result.turns),
        "event_count": len(result.events),
        "file_paths": sorted(result.files),
        "files": file_list,
    }


def _manifest(result: CodegenRecipeResult) -> str:
    lines = [
        "# Codegen integration artifacts",
        "",
        f"- run_id: `{result.run_id}`",
        f"- problem_id: `{result.problem_id}`",
        f"- recipe: `{result.recipe}`",
        f"- status: `{result.status}` (ok={result.ok})",
        f"- graph_status: `{result.graph_status}`",
        f"- budget_spent: `{result.budget_spent}` level=`{result.budget_level}`",
        f"- turns: `{len(result.turns)}`",
        f"- events: `{len(result.events)}`",
    ]
    if result.first_pass_verified is not None:
        lines.append(f"- first_pass_verified: `{result.first_pass_verified}`")
    if result.package_name:
        lines.append(f"- package_name: `{result.package_name}`")
    if result.files:
        lines.append(f"- package_files: `{', '.join(sorted(result.files))}`")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "| File | Contents |",
            "|------|----------|",
            "| `result.json` | Host summary + file index |",
            "| `events.json` / `events.jsonl` | Full MechaHarness event log |",
            "| `graph.json` | Final execution graph snapshot |",
            "| `turns.json` / `turns.jsonl` | Completer request/response turns |",
            "| `prompt.txt` | Assembled coding prompt |",
            "| `refine_prompt.txt` | Repair prompt (refine recipe) |",
            "| `raw_response.txt` | Completer text used for extract |",
            "| `script.py` | Extracted primary script / `__main__` |",
            "| `files/` | Extracted multi-file package tree |",
            "| `execute_results.json` | Per-fixture stdout/stderr/exit |",
            "| `execute_command.json` | Exact execute argv |",
            "| `failures.json` | Verification failures |",
            "| `diagnostics.json` | GraphExecutor diagnostics |",
            "| `access_checks.json` | Capability check payloads |",
            "| `node_statuses.json` | Final per-node status |",
            "| `checkpoint.sqlite` | Durable MH checkpoint DB |",
            "",
        ]
    )
    return "\n".join(lines)


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[Any]) -> None:
    lines = [json.dumps(row, sort_keys=True, default=str) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
