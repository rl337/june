"""Package recipe: multi-file wordstats with __main__.py + helper submodule."""

from __future__ import annotations

from pathlib import Path

import pytest

from june.recipes.codegen import (
    REFERENCE_WORDSTATS_FILES,
    WORD_STATS_PKG,
    FixedPackageCompleter,
)
from tests.integration.artifacts import run_codegen_with_artifacts
from tests.integration.harness_assertions import (
    assert_event_log_shape,
    assert_inference_efficiency,
    assert_package_artifacts,
    assert_successful_codegen_harness,
)

pytestmark = pytest.mark.integration


def test_codegen_wordstats_package_offline(artifact_dir: Path) -> None:
    """Fixed package completer emits path-annotated fences; `python -m` verifies."""
    result = run_codegen_with_artifacts(
        WORD_STATS_PKG,
        FixedPackageCompleter(REFERENCE_WORDSTATS_FILES),
        artifact_dir,
        recipe="package",
    )
    assert_package_artifacts(result, artifact_dir, package_name="wordstats")
    assert_event_log_shape(result, recipe="package")
    assert (artifact_dir / "files" / "wordstats" / "__main__.py").is_file()
    assert (artifact_dir / "files" / "wordstats" / "stats.py").is_file()
    assert result.execute_command is not None
    assert result.execute_command[-2:] == ["-m", "wordstats"]


@pytest.mark.junespark_live
def test_codegen_wordstats_package_junespark(
    junespark_completer,
    artifact_dir: Path,
) -> None:
    """Live model must emit a path-annotated package that verifies in one call."""
    result = run_codegen_with_artifacts(
        WORD_STATS_PKG,
        junespark_completer,
        artifact_dir,
        recipe="package",
    )
    assert_successful_codegen_harness(
        result,
        recipe="package",
        expect_budget_spent=None,
        expect_turns=1,
        max_turns=1,
    )
    assert_inference_efficiency(result, recipe="package", expect_turns=1, max_turns=1)
    assert_event_log_shape(result, recipe="package")
    assert result.package_name == "wordstats"
    assert any(p.endswith("__main__.py") for p in result.files)
    assert any(p.endswith("stats.py") for p in result.files)
    assert result.execute_command is not None
    assert result.execute_command[-2:] == ["-m", "wordstats"]
    assert "api" in (result.turns[0].get("response") or {})
    assert (artifact_dir / "files" / "wordstats" / "__main__.py").is_file()
