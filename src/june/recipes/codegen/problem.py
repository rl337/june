"""Fixed coding problems for the codegen integration suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CodingCase:
    """One stdin → expected stdout case."""

    stdin: str
    expected_stdout: str
    name: str = ""


@dataclass(frozen=True)
class CodingProblem:
    """A self-contained coding task with deterministic verification cases."""

    id: str
    title: str
    statement: str
    cases: tuple[CodingCase, ...]
    language: str = "python"
    timeout_seconds: float = 5.0
    output_kind: Literal["script", "package"] = "script"
    package_name: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def prompt(self) -> str:
        case_lines = []
        for index, case in enumerate(self.cases, start=1):
            label = case.name or f"case_{index}"
            case_lines.append(
                f"- {label}: stdin={case.stdin!r} → stdout={case.expected_stdout!r}"
            )
        stdlib_rule = (
            "Use the Python standard library only — do not import any third-party "
            "packages (no numpy, requests, etc.).\n"
        )
        if self.output_kind == "package":
            pkg = self.package_name or "package"
            return (
                f"You are a careful Python programmer.\n"
                f"{stdlib_rule}"
                f"Produce a runnable multi-file Python package named `{pkg}` with at "
                f"least `{pkg}/__main__.py` and one helper submodule (e.g. "
                f"`{pkg}/stats.py`). Intra-package imports are allowed.\n"
                f"Respond with ONLY fenced ```python blocks, each tagged with a path, "
                f"for example: ```python path={pkg}/__main__.py\n"
                f"No prose outside the fences.\n\n"
                f"# {self.title}\n\n"
                f"{self.statement.strip()}\n\n"
                f"Verification examples (your package will be run as "
                f"`python -m {pkg}` against these):\n"
                + "\n".join(case_lines)
                + "\n"
            )
        return (
            f"You are a careful Python programmer.\n"
            f"{stdlib_rule}"
            f"Write a complete, self-contained Python script that solves this problem.\n"
            f"Respond with ONLY a single ```python fenced code block and no prose.\n\n"
            f"# {self.title}\n\n"
            f"{self.statement.strip()}\n\n"
            f"Verification examples (your script will be executed against these):\n"
            + "\n".join(case_lines)
            + "\n"
        )


# Classic Project Euler #1 style — small, unambiguous I/O, good for reason models.
SUM_MULTIPLES_OF_3_OR_5 = CodingProblem(
    id="sum_multiples_3_or_5",
    title="Sum of multiples of 3 or 5",
    statement=(
        "Read a single integer N from standard input (possibly surrounded by whitespace).\n"
        "Print a single integer: the sum of all natural numbers strictly below N that are\n"
        "multiples of 3 or 5. Print nothing else — no prompts, no labels, just the number\n"
        "followed by a newline.\n\n"
        "Constraints: 1 <= N <= 1_000_000. Prefer an O(1) or O(N) solution; do not hard-code\n"
        "answers for the sample cases."
    ),
    cases=(
        CodingCase(stdin="10\n", expected_stdout="23\n", name="n10"),
        CodingCase(stdin="100\n", expected_stdout="2318\n", name="n100"),
        CodingCase(stdin="1000\n", expected_stdout="233168\n", name="n1000"),
    ),
    metadata={"source": "project_euler_1_style", "difficulty": "easy"},
)


REFERENCE_SOLUTION = '''\
#!/usr/bin/env python3
"""Sum of multiples of 3 or 5 below N (stdin)."""

def main() -> None:
    n = int(input().strip())
    total = sum(i for i in range(n) if i % 3 == 0 or i % 5 == 0)
    print(total)

if __name__ == "__main__":
    main()
'''


# RPN — easy to get binary-op operand order / truncating division wrong on first try.
RPN_EVAL = CodingProblem(
    id="rpn_eval",
    title="Reverse Polish notation evaluator",
    statement=(
        "Read one line of space-separated tokens from standard input representing an\n"
        "expression in reverse Polish notation. Tokens are integers (possibly negative)\n"
        "or the operators +, -, *, /. Division truncates toward zero (like C-style\n"
        "integer division / truncating toward zero, not Python floor division).\n"
        "Print a single integer result followed by a newline. Assume the expression is\n"
        "well-formed and fits in 64-bit signed integers after each operation."
    ),
    cases=(
        CodingCase(stdin="3 4 +\n", expected_stdout="7\n", name="add"),
        CodingCase(
            stdin="15 7 1 1 + - / 3 * 2 1 1 + + -\n",
            expected_stdout="5\n",
            name="leetcode_style",
        ),
        CodingCase(stdin="7 3 /\n", expected_stdout="2\n", name="trunc_div"),
        CodingCase(stdin="1 2 - 3 /\n", expected_stdout="0\n", name="neg_trunc"),
        CodingCase(stdin="-7 3 /\n", expected_stdout="-2\n", name="neg_div"),
    ),
    metadata={"source": "leetcode_150_style", "difficulty": "medium"},
)


REFERENCE_RPN_SOLUTION = '''\
#!/usr/bin/env python3
"""Evaluate reverse Polish notation (truncating division toward zero)."""

import sys


def trunc_div(a: int, b: int) -> int:
    # Truncate toward zero (not Python //).
    return int(a / b)


def eval_rpn(tokens: list[str]) -> int:
    stack: list[int] = []
    for tok in tokens:
        if tok in {"+", "-", "*", "/"}:
            b = stack.pop()
            a = stack.pop()
            if tok == "+":
                stack.append(a + b)
            elif tok == "-":
                stack.append(a - b)
            elif tok == "*":
                stack.append(a * b)
            else:
                stack.append(trunc_div(a, b))
        else:
            stack.append(int(tok))
    return stack[-1]


def main() -> None:
    line = sys.stdin.readline()
    tokens = line.split()
    print(eval_rpn(tokens))


if __name__ == "__main__":
    main()
'''


# Known-bad first-shot: uses Python floor division and swapped operands on - and /.
BAD_RPN_SOLUTION = '''\
#!/usr/bin/env python3
"""Buggy RPN: floor division and swapped binary operands."""

import sys


def eval_rpn(tokens: list[str]) -> int:
    stack: list[int] = []
    for tok in tokens:
        if tok in {"+", "-", "*", "/"}:
            b = stack.pop()
            a = stack.pop()
            if tok == "+":
                stack.append(a + b)
            elif tok == "-":
                # Bug: operands swapped.
                stack.append(b - a)
            elif tok == "*":
                stack.append(a * b)
            else:
                # Bug: floor division + swapped.
                stack.append(b // a)
        else:
            stack.append(int(tok))
    return stack[-1]


def main() -> None:
    tokens = sys.stdin.readline().split()
    print(eval_rpn(tokens))


if __name__ == "__main__":
    main()
'''


WORD_STATS_PKG = CodingProblem(
    id="word_stats_pkg",
    title="Word statistics package",
    statement=(
        "Build a package that reads all of stdin as text, tokenizes into words by\n"
        "splitting on whitespace, lowercases each token, and strips leading/trailing\n"
        "ASCII punctuation from each token (characters in string.punctuation). Drop\n"
        "empty tokens after stripping. Print exactly two lines:\n"
        "  words=<total_token_count>\n"
        "  unique=<number_of_distinct_tokens>\n"
        "Put CLI I/O in wordstats/__main__.py and tokenization/counting helpers in\n"
        "wordstats/stats.py. Running `python -m wordstats` must work."
    ),
    cases=(
        CodingCase(
            stdin="Hello, hello WORLD!\n",
            expected_stdout="words=3\nunique=2\n",
            name="case_fold_punct",
        ),
        CodingCase(
            stdin="one two two three\n",
            expected_stdout="words=4\nunique=3\n",
            name="dupes",
        ),
        CodingCase(
            stdin="  alpha...\nbeta\n",
            expected_stdout="words=2\nunique=2\n",
            name="multiline",
        ),
    ),
    output_kind="package",
    package_name="wordstats",
    metadata={"source": "june_integration", "difficulty": "easy_package"},
)


REFERENCE_WORDSTATS_FILES: dict[str, str] = {
    "wordstats/__init__.py": '"""Word statistics package."""\n',
    "wordstats/stats.py": '''\
"""Tokenization and counting helpers."""

from __future__ import annotations

import string
from collections import Counter


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in text.split():
        tok = raw.lower().strip(string.punctuation)
        if tok:
            tokens.append(tok)
    return tokens


def count_words(tokens: list[str]) -> int:
    return len(tokens)


def count_unique(tokens: list[str]) -> int:
    return len(Counter(tokens))
''',
    "wordstats/__main__.py": '''\
"""CLI entry: python -m wordstats."""

from __future__ import annotations

import sys

from wordstats.stats import count_unique, count_words, tokenize


def main() -> None:
    text = sys.stdin.read()
    tokens = tokenize(text)
    print(f"words={count_words(tokens)}")
    print(f"unique={count_unique(tokens)}")


if __name__ == "__main__":
    main()
''',
}


def problem_by_id(problem_id: str) -> CodingProblem:
    catalog = {
        SUM_MULTIPLES_OF_3_OR_5.id: SUM_MULTIPLES_OF_3_OR_5,
        RPN_EVAL.id: RPN_EVAL,
        WORD_STATS_PKG.id: WORD_STATS_PKG,
    }
    try:
        return catalog[problem_id]
    except KeyError as exc:
        raise ValueError(f"unknown coding problem id: {problem_id!r}") from exc
