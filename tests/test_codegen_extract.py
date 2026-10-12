"""Unit tests for codegen script extraction (no MechaHarness / network)."""

from __future__ import annotations

import pytest

from june.recipes.codegen.extract import (
    assert_stdlib_only,
    extract_python_files,
    extract_python_script,
)
from june.recipes.codegen.problem import REFERENCE_SOLUTION, SUM_MULTIPLES_OF_3_OR_5


def test_extract_fenced_python() -> None:
    text = "Sure.\n```python\nprint(23)\n```\n"
    assert extract_python_script(text) == "print(23)\n"


def test_extract_bare_script() -> None:
    assert "print(total)" in extract_python_script(REFERENCE_SOLUTION)


def test_extract_empty_raises() -> None:
    with pytest.raises(ValueError):
        extract_python_script("   ")


def test_problem_prompt_mentions_cases_and_stdlib() -> None:
    prompt = SUM_MULTIPLES_OF_3_OR_5.prompt()
    assert "multiples of 3 or 5" in prompt
    assert "23" in prompt
    assert "```python" in prompt
    assert "standard library" in prompt.lower()


def test_assert_stdlib_only_allows_math_sys() -> None:
    assert_stdlib_only("import math\nimport sys\nprint(math.sqrt(4))\n")


def test_assert_stdlib_only_rejects_numpy() -> None:
    with pytest.raises(ValueError, match="numpy"):
        assert_stdlib_only("import numpy as np\nprint(np.array([1]))\n")


def test_assert_stdlib_only_allows_local_package() -> None:
    assert_stdlib_only(
        "from wordstats.stats import tokenize\n",
        allowed_local_packages=["wordstats"],
    )


def test_extract_python_files_path_annotated() -> None:
    text = (
        "```python path=wordstats/__main__.py\n"
        "from wordstats.stats import tokenize\n"
        "print(tokenize('a'))\n"
        "```\n"
        "```python path=wordstats/stats.py\n"
        "def tokenize(text):\n"
        "    return text.split()\n"
        "```\n"
    )
    files = extract_python_files(text, allowed_local_packages=["wordstats"])
    assert set(files) == {"wordstats/__main__.py", "wordstats/stats.py"}


def test_extract_python_files_rejects_third_party() -> None:
    text = (
        "```python path=wordstats/__main__.py\n"
        "import requests\n"
        "```\n"
        "```python path=wordstats/stats.py\n"
        "x = 1\n"
        "```\n"
    )
    with pytest.raises(ValueError, match="requests"):
        extract_python_files(text)
