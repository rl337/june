"""Standalone ``june.imagegen.evaluate_criteria`` recipe + ImageEvaluator soft point.

Generation recipes bind this via soft point rather than inlining expand/score nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from june.async_util import run_coro_sync
from june.budget import SubgraphBudget
from june.harness import BoundRun
from june.recipes.imagegen.acceptance import (
    AcceptanceSpec,
    AcceptanceSpecCrafter,
    CriteriaScorer,
)
from june.recipes.imagegen.problem import ImageProblem


@dataclass
class EvaluateResult:
    passed: bool
    score: dict[str, Any] = field(default_factory=dict)
    acceptance_spec: dict[str, Any] = field(default_factory=dict)
    failed: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    turns: list[dict[str, Any]] = field(default_factory=list)

    def to_critique_dict(self) -> dict[str, Any]:
        """Shape compatible with PromptCrafter prior_critique."""
        missing = [
            f"{row.get('id')}: {row.get('text') or row.get('evidence')}"
            for row in self.failed
        ]
        notes = "\n".join(
            f"- [{row.get('id')}] {row.get('evidence')}" for row in self.failed
        )
        return {
            "passed": self.passed,
            "missing": missing,
            "forbidden_found": [],
            "notes": notes,
            "failed_criteria": list(self.failed),
            "score": dict(self.score),
            "acceptance_spec": dict(self.acceptance_spec),
        }


class ImageEvaluator(Protocol):
    """Soft point: run (or stub) the evaluate_criteria recipe against an image."""

    turns: list[dict[str, Any]]

    def evaluate(
        self,
        problem: ImageProblem,
        image: bytes,
        *,
        image_prompt: str,
        prior_spec: AcceptanceSpec | dict[str, Any] | None = None,
    ) -> EvaluateResult: ...


class FixedImageEvaluator:
    """Offline scripted evaluator (fail then pass, last repeats)."""

    def __init__(self, results: list[EvaluateResult] | None = None) -> None:
        if results is None:
            results = [
                EvaluateResult(
                    passed=False,
                    failed=[
                        {
                            "id": "structure_01",
                            "kind": "structure",
                            "text": "subject is well-formed",
                            "evidence": "scripted structural failure",
                            "passed": False,
                        }
                    ],
                    summary="scripted fail",
                    score={"passed_all": False},
                ),
                EvaluateResult(
                    passed=True,
                    failed=[],
                    summary="scripted pass",
                    score={"passed_all": True},
                ),
            ]
        if not results:
            raise ValueError("FixedImageEvaluator requires at least one result")
        self.results = list(results)
        self.turns: list[dict[str, Any]] = []
        self._index = 0

    def evaluate(
        self,
        problem: ImageProblem,
        image: bytes,
        *,
        image_prompt: str,
        prior_spec: AcceptanceSpec | dict[str, Any] | None = None,
    ) -> EvaluateResult:
        del problem, image, image_prompt, prior_spec
        idx = min(self._index, len(self.results) - 1)
        result = self.results[idx]
        self._index += 1
        self.turns.append(
            {
                "index": len(self.turns),
                "role": "image_evaluator",
                "kind": "fixed",
                "response": {
                    "passed": result.passed,
                    "failed": result.failed,
                    "summary": result.summary,
                },
            }
        )
        return result


class BoundEvaluateCriteria:
    """Binds AcceptanceSpecCrafter + CriteriaScorer into ImageEvaluator."""

    def __init__(
        self,
        crafter: AcceptanceSpecCrafter,
        scorer: CriteriaScorer,
        *,
        checkpoint_dir: str | None = None,
    ) -> None:
        self.crafter = crafter
        self.scorer = scorer
        self.checkpoint_dir = checkpoint_dir
        self.turns: list[dict[str, Any]] = []
        self._call_index = 0

    def evaluate(
        self,
        problem: ImageProblem,
        image: bytes,
        *,
        image_prompt: str,
        prior_spec: AcceptanceSpec | dict[str, Any] | None = None,
    ) -> EvaluateResult:
        # Unique checkpoint per call — reusing one sqlite across run_ids skips
        # nodes / drops evaluate_result on later refine attempts.
        checkpoint_path: str | None = None
        if self.checkpoint_dir:
            from pathlib import Path

            directory = Path(self.checkpoint_dir)
            directory.mkdir(parents=True, exist_ok=True)
            checkpoint_path = str(
                directory / f"eval_{self._call_index:02d}.sqlite"
            )
        self._call_index += 1
        result = run_evaluate_criteria_recipe(
            problem,
            image,
            image_prompt=image_prompt,
            crafter=self.crafter,
            scorer=self.scorer,
            prior_spec=prior_spec,
            checkpoint_path=checkpoint_path,
        )
        self.turns.extend(result.turns)
        return result


EVALUATE_CRITERIA_NODE_ORDER = (
    "expand_spec",
    "score_criteria",
    "summarize",
)


def bound_run_for_evaluate_criteria(problem_id: str) -> BoundRun:
    return BoundRun(
        run_id=f"imagegen-eval-{problem_id}-{uuid4().hex[:8]}",
        template_name="june.imagegen.evaluate_criteria",
        bindings={"problem_id": problem_id, "recipe": "evaluate_criteria"},
        budget=SubgraphBudget(),
        grants=[],
        node_kinds=[
            "june.imagegen.expand_spec",
            "june.imagegen.score_criteria",
            "june.imagegen.summarize_eval",
        ],
    )


def build_evaluate_criteria_graph(
    problem: ImageProblem, *, run_id: str | None = None
) -> Any:
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode

    rid = run_id or f"imagegen-eval-{problem.id}-{uuid4().hex[:8]}"
    graph = ExecutionGraph(id=rid, goal=f"imagegen-eval:{problem.id}")
    base = {
        "problem_id": problem.id,
        "problem_title": problem.title,
        "recipe": "june.imagegen.evaluate_criteria",
    }
    specs = [
        ("expand_spec", "june.imagegen.expand_spec", "expand acceptance criteria"),
        ("score_criteria", "june.imagegen.score_criteria", "VL score each criterion"),
        ("summarize", "june.imagegen.summarize_eval", "summarize pass/fail evidence"),
    ]
    nodes = [
        GraphNode(
            id=node_id,
            kind=kind,
            goal=goal,
            payload=dict(base),
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
                reason="june.imagegen.evaluate_criteria sequence",
            )
        )
    return graph


def make_evaluate_criteria_runners(
    crafter: AcceptanceSpecCrafter,
    scorer: CriteriaScorer,
    *,
    state: dict[str, Any] | None = None,
) -> list[Any]:
    from mechaharness.graph import NodeStatus
    from mechaharness.graph_executor import CallableGraphNodeRunner, NodeOutcome

    shared: dict[str, Any] = state if state is not None else {}

    async def expand_node(node: Any, context: Any) -> Any:
        del context, node
        problem = shared.get("problem")
        if not isinstance(problem, ImageProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED, payload={}, error="missing_problem"
            )
        prior = shared.get("prior_spec")
        if isinstance(prior, AcceptanceSpec):
            spec = prior
        elif isinstance(prior, dict) and prior.get("criteria"):
            from june.recipes.imagegen.acceptance import criteria_from_payload

            spec = AcceptanceSpec(
                criteria=criteria_from_payload(prior),
                source_prompt=str(
                    prior.get("source_prompt") or shared.get("image_prompt") or ""
                ),
                raw=dict(prior.get("raw") or prior),
            )
        else:
            spec = crafter.expand(
                problem, image_prompt=str(shared.get("image_prompt") or "")
            )
        shared["acceptance_spec"] = spec
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"criteria_count": len(spec.criteria)},
            cost_units=0.25,
        )

    async def score_node(node: Any, context: Any) -> Any:
        del context, node
        problem = shared.get("problem")
        spec = shared.get("acceptance_spec")
        data = shared.get("image_bytes") or b""
        if not isinstance(problem, ImageProblem) or not isinstance(spec, AcceptanceSpec):
            return NodeOutcome(
                status=NodeStatus.FAILED, payload={}, error="missing_spec_or_problem"
            )
        if not isinstance(data, (bytes, bytearray)) or not data:
            return NodeOutcome(
                status=NodeStatus.FAILED, payload={}, error="missing_image_bytes"
            )
        score = scorer.score(
            bytes(data),
            spec,
            image_prompt=str(shared.get("image_prompt") or ""),
        )
        shared["score"] = score
        shared["failed_criteria"] = list(score.get("failed") or [])
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "passed_all": bool(score.get("passed_all")),
                "failed_count": len(score.get("failed") or []),
            },
            cost_units=0.5,
        )

    async def summarize_node(node: Any, context: Any) -> Any:
        del context, node
        score = dict(shared.get("score") or {})
        failed = list(shared.get("failed_criteria") or [])
        passed = bool(score.get("passed_all")) and not failed
        spec = shared.get("acceptance_spec")
        spec_dict = spec.to_dict() if isinstance(spec, AcceptanceSpec) else {}
        summary = (
            "all criteria passed"
            if passed
            else f"{len(failed)} criterion failure(s): "
            + ", ".join(str(f.get("id")) for f in failed)
        )
        evaluate_result = EvaluateResult(
            passed=passed,
            score=score,
            acceptance_spec=spec_dict,
            failed=failed,
            summary=summary,
        )
        shared["evaluate_result"] = evaluate_result
        shared["verified"] = passed
        shared["failures"] = [] if passed else [{"reason": "criteria_failed", "failed": failed}]
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED if passed else NodeStatus.FAILED,
            payload={"passed": passed, "summary": summary, "failed": failed},
            error=None if passed else summary,
            cost_units=0.0,
        )

    return [
        CallableGraphNodeRunner(["june.imagegen.expand_spec"], expand_node),
        CallableGraphNodeRunner(["june.imagegen.score_criteria"], score_node),
        CallableGraphNodeRunner(["june.imagegen.summarize_eval"], summarize_node),
    ]


def run_evaluate_criteria_recipe(
    problem: ImageProblem,
    image: bytes,
    *,
    image_prompt: str,
    crafter: AcceptanceSpecCrafter,
    scorer: CriteriaScorer,
    prior_spec: AcceptanceSpec | dict[str, Any] | None = None,
    checkpoint_path: str | None = None,
    grants: list[object] | None = None,
) -> EvaluateResult:
    """Bind + run ``june.imagegen.evaluate_criteria`` (host_kit)."""
    from mechaharness.host_kit import host_graph_executor

    bound = bound_run_for_evaluate_criteria(problem.id)
    graph = build_evaluate_criteria_graph(problem, run_id=bound.run_id)
    state: dict[str, Any] = {
        "problem": problem,
        "problem_id": problem.id,
        "image_bytes": image,
        "image_prompt": image_prompt,
        "prior_spec": prior_spec,
    }
    runners = make_evaluate_criteria_runners(crafter, scorer, state=state)
    executor = host_graph_executor(
        runners=runners,
        checkpoint_path=checkpoint_path,
        agent_id="june-imagegen-eval",
        grants=grants,
    )
    exec_result = run_coro_sync(
        executor.run(
            graph,
            budget_policy=bound.budget.to_mechaharness(),
            run_id=bound.run_id,
            resume=False,
        )
    )
    result = state.get("evaluate_result")
    if isinstance(result, EvaluateResult):
        turns: list[dict[str, Any]] = []
        turns.extend(list(getattr(crafter, "turns", None) or []))
        turns.extend(list(getattr(scorer, "turns", None) or []))
        result.turns = turns
        return result
    error = getattr(exec_result, "error", None) or "missing evaluate_result"
    return EvaluateResult(
        passed=False,
        summary=f"evaluate_criteria produced no result: {error}",
        failed=[{"id": "internal", "evidence": str(error)}],
    )
