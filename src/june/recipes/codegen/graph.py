"""Build incubating ``june.codegen`` execution graphs."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from june.budget import SubgraphBudget
from june.harness import BoundRun
from june.recipes.codegen.problem import CodingProblem

RecipeKind = Literal["oneshot", "refine", "package"]

ONESHOT_NODE_ORDER = (
    "prompt",
    "generate",
    "extract",
    "execute",
    "verify",
)

REFINE_NODE_ORDER = (
    "prompt",
    "generate",
    "extract",
    "execute",
    "diagnose",
    "refine_prompt",
    "repair_generate",
    "repair_extract",
    "repair_execute",
    "verify",
)

PACKAGE_NODE_ORDER = (
    "prompt",
    "generate",
    "extract_files",
    "execute_module",
    "verify",
)


def build_codegen_graph(problem: CodingProblem, *, run_id: str | None = None) -> Any:
    """prompt → generate → extract → execute → verify."""
    return _build_linear_graph(
        problem,
        run_id=run_id,
        recipe="june.codegen",
        node_specs=[
            ("prompt", "june.codegen.prompt", "assemble coding prompt"),
            ("generate", "june.codegen.generate", "generate python solution"),
            ("extract", "june.codegen.extract", "extract python script"),
            ("execute", "june.codegen.execute", "execute generated script on fixtures"),
            ("verify", "june.codegen.verify", "verify stdout against expected cases"),
        ],
    )


def build_refine_graph(problem: CodingProblem, *, run_id: str | None = None) -> Any:
    """One-shot attempt + diagnose/refine repair pass + final verify."""
    return _build_linear_graph(
        problem,
        run_id=run_id,
        recipe="june.codegen.refine",
        node_specs=[
            ("prompt", "june.codegen.prompt", "assemble coding prompt"),
            ("generate", "june.codegen.generate", "generate python solution"),
            ("extract", "june.codegen.extract", "extract python script"),
            ("execute", "june.codegen.execute", "execute generated script on fixtures"),
            ("diagnose", "june.codegen.diagnose", "record verification failures"),
            ("refine_prompt", "june.codegen.refine_prompt", "build repair prompt"),
            ("repair_generate", "june.codegen.repair_generate", "generate repaired script"),
            ("repair_extract", "june.codegen.repair_extract", "extract repaired script"),
            (
                "repair_execute",
                "june.codegen.repair_execute",
                "re-execute repaired script",
            ),
            ("verify", "june.codegen.verify", "verify stdout against expected cases"),
        ],
    )


def build_package_graph(problem: CodingProblem, *, run_id: str | None = None) -> Any:
    """prompt → generate → extract_files → execute_module → verify."""
    return _build_linear_graph(
        problem,
        run_id=run_id,
        recipe="june.codegen.package",
        node_specs=[
            ("prompt", "june.codegen.prompt", "assemble coding prompt"),
            ("generate", "june.codegen.generate", "generate multi-file package"),
            (
                "extract_files",
                "june.codegen.extract_files",
                "extract path-annotated python files",
            ),
            (
                "execute_module",
                "june.codegen.execute_module",
                "run package as python -m",
            ),
            ("verify", "june.codegen.verify", "verify stdout against expected cases"),
        ],
    )


def bound_run_for_codegen(problem_id: str, *, recipe: RecipeKind = "oneshot") -> BoundRun:
    template = {
        "oneshot": "june.codegen",
        "refine": "june.codegen.refine",
        "package": "june.codegen.package",
    }[recipe]
    kinds = {
        "oneshot": [
            "june.codegen.prompt",
            "june.codegen.generate",
            "june.codegen.extract",
            "june.codegen.execute",
            "june.codegen.verify",
        ],
        "refine": [
            "june.codegen.prompt",
            "june.codegen.generate",
            "june.codegen.extract",
            "june.codegen.execute",
            "june.codegen.diagnose",
            "june.codegen.refine_prompt",
            "june.codegen.repair_generate",
            "june.codegen.repair_extract",
            "june.codegen.repair_execute",
            "june.codegen.verify",
        ],
        "package": [
            "june.codegen.prompt",
            "june.codegen.generate",
            "june.codegen.extract_files",
            "june.codegen.execute_module",
            "june.codegen.verify",
        ],
    }[recipe]
    return BoundRun(
        run_id=f"codegen-{problem_id}-{uuid4().hex[:8]}",
        template_name=template,
        bindings={"problem_id": problem_id, "recipe": recipe},
        budget=SubgraphBudget(),
        grants=[],
        node_kinds=kinds,
    )


def _build_linear_graph(
    problem: CodingProblem,
    *,
    run_id: str | None,
    recipe: str,
    node_specs: list[tuple[str, str, str]],
) -> Any:
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode

    rid = run_id or f"codegen-{problem.id}-{uuid4().hex[:8]}"
    graph = ExecutionGraph(id=rid, goal=f"codegen:{problem.id}")
    base_payload = {
        "problem_id": problem.id,
        "problem_title": problem.title,
        "language": problem.language,
        "recipe": recipe,
        "output_kind": problem.output_kind,
        "package_name": problem.package_name,
    }
    # Deterministic extract/execute/verify must not silently retry the same
    # artifact (MH default max_attempts=3). Repair belongs in the refine graph.
    nodes = [
        GraphNode(
            id=node_id,
            kind=kind,
            goal=goal,
            payload=dict(base_payload),
            max_attempts=1,
        )
        for node_id, kind, goal in node_specs
    ]
    for node in nodes:
        graph.add_node(node)
    order = [n.id for n in nodes]
    for left, right in zip(order, order[1:]):
        graph.add_dependency(
            DependencyEdge(
                from_node=left,
                to_node=right,
                types=["control"],
                reason=f"{recipe} sequence",
            )
        )
    return graph
