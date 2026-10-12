"""Build incubating ``june.imagegen`` execution graphs."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from june.budget import SubgraphBudget
from june.harness import BoundRun
from june.recipes.imagegen.problem import ImageProblem

RecipeKind = Literal[
    "oneshot", "critique_refine", "evaluate_criteria", "criteria_refine"
]

ONESHOT_NODE_ORDER = (
    "prompt",
    "generate",
    "persist",
    "verify",
)

CRITIQUE_REFINE_NODE_ORDER = (
    "goal",
    "craft_prompt",
    "generate",
    "persist",
    "critique",
    "diagnose",
    "refine_prompt",
    "repair_generate",
    "repair_persist",
    "verify_critique",
)

# Logical control pattern for host compose loop (not an unrolled MH graph).
# June owns the retry loop; each evaluate binds june.imagegen.evaluate_criteria.
CRITERIA_REFINE_NODE_ORDER = (
    "craft_prompt",
    "attempt_loop",  # generate → evaluate_criteria → refine? × max_retries
    "verify",
)


def build_imagegen_graph(problem: ImageProblem, *, run_id: str | None = None) -> Any:
    """prompt → generate → persist → verify."""
    return _linear(
        problem,
        run_id=run_id,
        recipe="june.imagegen",
        specs=[
            ("prompt", "june.imagegen.prompt", "assemble image prompt"),
            ("generate", "june.imagegen.generate", "generate image via Comfy soft-point"),
            ("persist", "june.imagegen.persist", "persist image bytes"),
            ("verify", "june.imagegen.verify", "verify image artifact"),
        ],
    )


def build_critique_refine_graph(
    problem: ImageProblem, *, run_id: str | None = None
) -> Any:
    """Craft → generate → VL *checklist* critique → optional refine → verify.

    Semantic completeness only. Artifact/geometry detect→retry is out of scope
    until ``anomaly_eval`` acceptance bar is green (see imagegen-integration.md).
    """
    return _linear(
        problem,
        run_id=run_id,
        recipe="june.imagegen.critique_refine",
        specs=[
            ("goal", "june.imagegen.goal", "assemble goal / acceptance spec"),
            ("craft_prompt", "june.imagegen.craft_prompt", "craft Comfy image prompt"),
            ("generate", "june.imagegen.generate", "generate image via Comfy"),
            ("persist", "june.imagegen.persist", "persist image bytes"),
            ("critique", "june.imagegen.critique", "VL critique against checklist"),
            ("diagnose", "june.imagegen.diagnose", "record first-pass critique"),
            ("refine_prompt", "june.imagegen.refine_prompt", "rewrite image prompt"),
            ("repair_generate", "june.imagegen.repair_generate", "regenerate image"),
            ("repair_persist", "june.imagegen.repair_persist", "persist repaired image"),
            ("verify_critique", "june.imagegen.verify_critique", "final critique gate"),
        ],
    )


def bound_run_for_imagegen(
    problem_id: str, *, recipe: RecipeKind = "oneshot"
) -> BoundRun:
    template = {
        "oneshot": "june.imagegen",
        "critique_refine": "june.imagegen.critique_refine",
        "evaluate_criteria": "june.imagegen.evaluate_criteria",
        "criteria_refine": "june.imagegen.criteria_refine",
    }[recipe]
    kinds = {
        "oneshot": [
            "june.imagegen.prompt",
            "june.imagegen.generate",
            "june.imagegen.persist",
            "june.imagegen.verify",
        ],
        "critique_refine": [
            "june.imagegen.goal",
            "june.imagegen.craft_prompt",
            "june.imagegen.generate",
            "june.imagegen.persist",
            "june.imagegen.critique",
            "june.imagegen.diagnose",
            "june.imagegen.refine_prompt",
            "june.imagegen.repair_generate",
            "june.imagegen.repair_persist",
            "june.imagegen.verify_critique",
        ],
        "evaluate_criteria": [
            "june.imagegen.expand_spec",
            "june.imagegen.score_criteria",
            "june.imagegen.summarize_eval",
        ],
        # Host compose loop — not an unrolled MH node list.
        "criteria_refine": [
            "june.imagegen.craft_prompt",
            "june.imagegen.generate",
            "june.imagegen.evaluate",  # binds evaluate_criteria
            "june.imagegen.refine_prompt",
            "june.imagegen.verify",
        ],
    }[recipe]
    return BoundRun(
        run_id=f"imagegen-{problem_id}-{uuid4().hex[:8]}",
        template_name=template,
        bindings={"problem_id": problem_id, "recipe": recipe},
        budget=SubgraphBudget(),
        grants=[],
        node_kinds=kinds,
    )


def expected_node_order(recipe: RecipeKind) -> tuple[str, ...]:
    return {
        "oneshot": ONESHOT_NODE_ORDER,
        "critique_refine": CRITIQUE_REFINE_NODE_ORDER,
        "evaluate_criteria": (
            "expand_spec",
            "score_criteria",
            "summarize",
        ),
        "criteria_refine": CRITERIA_REFINE_NODE_ORDER,
    }[recipe]


def _linear(
    problem: ImageProblem,
    *,
    run_id: str | None,
    recipe: str,
    specs: list[tuple[str, str, str]],
) -> Any:
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode

    rid = run_id or f"imagegen-{problem.id}-{uuid4().hex[:8]}"
    graph = ExecutionGraph(id=rid, goal=f"imagegen:{problem.id}")
    base_payload = {
        "problem_id": problem.id,
        "problem_title": problem.title,
        "backend": problem.backend,
        "recipe": recipe,
    }
    nodes = [
        GraphNode(
            id=node_id,
            kind=kind,
            goal=goal,
            payload=dict(base_payload),
            max_attempts=1,
        )
        for node_id, kind, goal in specs
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
