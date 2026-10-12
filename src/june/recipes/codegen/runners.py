"""Graph node runners for incubating ``june.codegen`` recipes."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from june.recipes.codegen.completers import CodegenCompleter
from june.recipes.codegen.extract import extract_python_files, extract_python_script
from june.recipes.codegen.problem import CodingProblem, problem_by_id


def make_codegen_runners(
    completer: CodegenCompleter,
    *,
    state: dict[str, Any] | None = None,
) -> list[Any]:
    """Return MechaHarness CallableGraphNodeRunners for all codegen node kinds."""
    from mechaharness.graph import NodeStatus
    from mechaharness.graph_executor import CallableGraphNodeRunner, NodeOutcome

    shared: dict[str, Any] = state if state is not None else {}

    async def prompt_node(node: Any, context: Any) -> Any:
        del context
        problem = _problem_from_payload(node.payload, shared)
        prompt = problem.prompt()
        shared["problem"] = problem
        shared["prompt"] = prompt
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"problem_id": problem.id, "prompt": prompt},
            cost_units=0.0,
        )

    async def generate_node(node: Any, context: Any) -> Any:
        del context
        problem = _problem_from_payload(node.payload, shared)
        prompt = str(shared.get("prompt") or problem.prompt())
        raw = completer.generate(prompt)
        shared["raw_response"] = raw
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"problem_id": problem.id, "raw_response": raw},
            cost_units=1.0,
        )

    async def extract_node(node: Any, context: Any) -> Any:
        del context, node
        raw = str(shared.get("raw_response") or "")
        try:
            script = extract_python_script(raw)
        except ValueError as exc:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                payload={"raw_response": raw},
                error=str(exc),
            )
        shared["script"] = script
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"script": script},
            cost_units=0.0,
        )

    async def execute_node(node: Any, context: Any) -> Any:
        del context, node
        return _execute_script(shared, NodeStatus, NodeOutcome, cost_units=0.5)

    async def diagnose_node(node: Any, context: Any) -> Any:
        """Always succeed; record whether the first pass would verify."""
        del context, node
        failures = _collect_failures(list(shared.get("run_results") or []))
        ok = not failures
        shared["first_pass_verified"] = ok
        shared["first_pass_failures"] = failures
        shared["failures"] = failures
        shared["verified"] = ok
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "first_pass_verified": ok,
                "failures": failures,
            },
            cost_units=0.0,
        )

    async def refine_prompt_node(node: Any, context: Any) -> Any:
        del context, node
        problem = shared.get("problem")
        if not isinstance(problem, CodingProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED,
                payload={},
                error="missing_problem",
            )
        if shared.get("first_pass_verified"):
            refine = ""
            shared["refine_prompt"] = refine
            shared["skip_repair"] = True
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"skipped": True, "refine_prompt": refine},
                cost_units=0.0,
            )
        failures = list(shared.get("first_pass_failures") or [])
        script = str(shared.get("script") or "")
        refine = (
            f"{problem.prompt()}\n"
            f"Your previous solution failed verification.\n"
            f"Failures (JSON):\n{json.dumps(failures, indent=2)}\n\n"
            f"Previous script:\n```python\n{script.rstrip()}\n```\n\n"
            f"Return a corrected complete Python script in a single ```python fence. "
            f"Stdlib only — no third-party imports.\n"
        )
        shared["refine_prompt"] = refine
        shared["skip_repair"] = False
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"skipped": False, "refine_prompt": refine},
            cost_units=0.0,
        )

    async def repair_generate_node(node: Any, context: Any) -> Any:
        del context, node
        if shared.get("skip_repair"):
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"skipped": True, "raw_response": shared.get("raw_response")},
                cost_units=0.0,
            )
        refine = str(shared.get("refine_prompt") or "")
        raw = completer.generate(refine)
        shared["raw_response"] = raw
        shared["repair_raw_response"] = raw
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"raw_response": raw},
            cost_units=1.0,
        )

    async def repair_extract_node(node: Any, context: Any) -> Any:
        del context, node
        if shared.get("skip_repair"):
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"skipped": True, "script": shared.get("script")},
                cost_units=0.0,
            )
        raw = str(shared.get("raw_response") or "")
        try:
            script = extract_python_script(raw)
        except ValueError as exc:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                payload={"raw_response": raw},
                error=str(exc),
            )
        shared["script"] = script
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"script": script},
            cost_units=0.0,
        )

    async def repair_execute_node(node: Any, context: Any) -> Any:
        del context, node
        if shared.get("skip_repair"):
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={
                    "skipped": True,
                    "run_results": shared.get("run_results"),
                },
                cost_units=0.0,
            )
        return _execute_script(shared, NodeStatus, NodeOutcome, cost_units=0.5)

    async def extract_files_node(node: Any, context: Any) -> Any:
        del context, node
        problem = shared.get("problem")
        if not isinstance(problem, CodingProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED,
                payload={},
                error="missing_problem",
            )
        raw = str(shared.get("raw_response") or "")
        local = [problem.package_name] if problem.package_name else None
        try:
            files = extract_python_files(
                raw,
                allowed_local_packages=local,
            )
        except ValueError as exc:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                payload={"raw_response": raw},
                error=str(exc),
            )
        shared["files"] = files
        # Convenience: primary script view for artifacts / assertions.
        main_path = next(
            (p for p in files if p.endswith("__main__.py")),
            next(iter(files)),
        )
        shared["script"] = files[main_path]
        shared["main_path"] = main_path
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"files": sorted(files), "main_path": main_path},
            cost_units=0.0,
        )

    async def execute_module_node(node: Any, context: Any) -> Any:
        del context, node
        problem = shared.get("problem")
        if not isinstance(problem, CodingProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED,
                payload={},
                error="missing_problem",
            )
        files = dict(shared.get("files") or {})
        if not files:
            return NodeOutcome(
                status=NodeStatus.FAILED,
                payload={},
                error="missing_files",
            )
        package_name = problem.package_name or _infer_package_name(files)
        run_results: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="june-codegen-pkg-") as tmp:
            root = Path(tmp)
            for rel, source in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            # Ensure package is importable even if model omitted __init__.py.
            pkg_init = root / package_name / "__init__.py"
            if not pkg_init.exists():
                pkg_init.parent.mkdir(parents=True, exist_ok=True)
                pkg_init.write_text("", encoding="utf-8")
            cmd = [sys.executable, "-m", package_name]
            shared["execute_command"] = cmd
            for case in problem.cases:
                completed = subprocess.run(
                    cmd,
                    input=case.stdin,
                    capture_output=True,
                    text=True,
                    timeout=problem.timeout_seconds,
                    check=False,
                    cwd=str(root),
                )
                run_results.append(
                    {
                        "name": case.name,
                        "stdin": case.stdin,
                        "expected_stdout": case.expected_stdout,
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                        "returncode": completed.returncode,
                        "command": cmd,
                    }
                )
        shared["run_results"] = run_results
        shared["package_name"] = package_name
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "run_results": run_results,
                "package_name": package_name,
                "command": cmd,
            },
            cost_units=0.5,
        )

    async def verify_node(node: Any, context: Any) -> Any:
        del context, node
        run_results = list(shared.get("run_results") or [])
        failures = _collect_failures(run_results)
        ok = not failures
        shared["verified"] = ok
        shared["failures"] = failures
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED if ok else NodeStatus.FAILED,
            payload={
                "verified": ok,
                "failures": failures,
                "script": shared.get("script"),
                "files": sorted(shared.get("files") or {}),
                "raw_response": shared.get("raw_response"),
                "run_results": run_results,
            },
            error=None if ok else f"{len(failures)} verification failure(s)",
            cost_units=0.0,
        )

    return [
        CallableGraphNodeRunner(["june.codegen.prompt"], prompt_node),
        CallableGraphNodeRunner(["june.codegen.generate"], generate_node),
        CallableGraphNodeRunner(["june.codegen.extract"], extract_node),
        CallableGraphNodeRunner(["june.codegen.execute"], execute_node),
        CallableGraphNodeRunner(["june.codegen.diagnose"], diagnose_node),
        CallableGraphNodeRunner(["june.codegen.refine_prompt"], refine_prompt_node),
        CallableGraphNodeRunner(["june.codegen.repair_generate"], repair_generate_node),
        CallableGraphNodeRunner(["june.codegen.repair_extract"], repair_extract_node),
        CallableGraphNodeRunner(["june.codegen.repair_execute"], repair_execute_node),
        CallableGraphNodeRunner(["june.codegen.extract_files"], extract_files_node),
        CallableGraphNodeRunner(["june.codegen.execute_module"], execute_module_node),
        CallableGraphNodeRunner(["june.codegen.verify"], verify_node),
    ]


def _execute_script(
    shared: dict[str, Any],
    NodeStatus: Any,
    NodeOutcome: Any,
    *,
    cost_units: float,
) -> Any:
    problem = shared.get("problem")
    if not isinstance(problem, CodingProblem):
        return NodeOutcome(
            status=NodeStatus.FAILED,
            payload={},
            error="missing_problem",
        )
    script = str(shared.get("script") or "")
    if not script.strip():
        return NodeOutcome(
            status=NodeStatus.FAILED,
            payload={},
            error="missing_script",
        )
    run_results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="june-codegen-") as tmp:
        script_path = Path(tmp) / "solution.py"
        script_path.write_text(script, encoding="utf-8")
        cmd = [sys.executable, str(script_path)]
        shared["execute_command"] = cmd
        for case in problem.cases:
            completed = subprocess.run(
                cmd,
                input=case.stdin,
                capture_output=True,
                text=True,
                timeout=problem.timeout_seconds,
                check=False,
            )
            run_results.append(
                {
                    "name": case.name,
                    "stdin": case.stdin,
                    "expected_stdout": case.expected_stdout,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "returncode": completed.returncode,
                    "command": cmd,
                }
            )
    shared["run_results"] = run_results
    return NodeOutcome(
        status=NodeStatus.SUCCEEDED,
        payload={"run_results": run_results, "script": script},
        cost_units=cost_units,
    )


def _collect_failures(run_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for result in run_results:
        if int(result.get("returncode") or 0) != 0:
            failures.append(
                {
                    "name": result.get("name"),
                    "reason": "nonzero_exit",
                    "returncode": result.get("returncode"),
                    "stderr": result.get("stderr"),
                }
            )
            continue
        actual = str(result.get("stdout") or "")
        expected = str(result.get("expected_stdout") or "")
        if actual != expected:
            failures.append(
                {
                    "name": result.get("name"),
                    "reason": "stdout_mismatch",
                    "expected": expected,
                    "actual": actual,
                }
            )
    return failures


def _infer_package_name(files: dict[str, str]) -> str:
    for path in files:
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[0]
    raise ValueError("cannot infer package name from extracted files")


def _problem_from_payload(payload: dict[str, Any], shared: dict[str, Any]) -> CodingProblem:
    problem = shared.get("problem") or payload.get("problem")
    if isinstance(problem, CodingProblem):
        return problem
    problem_id = str(payload.get("problem_id") or shared.get("problem_id") or "")
    return problem_by_id(problem_id)
