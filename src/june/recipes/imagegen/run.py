"""Run incubating imagegen recipes through MechaHarness host_kit / compose loops."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from june.async_util import run_coro_sync
from june.recipes.imagegen.critics import PromptCrafter, VisionCritic
from june.recipes.imagegen.evaluate import EvaluateResult, ImageEvaluator
from june.recipes.imagegen.generators import ImageGenerator
from june.recipes.imagegen.graph import (
    ONESHOT_NODE_ORDER,
    RecipeKind,
    bound_run_for_imagegen,
    build_critique_refine_graph,
    build_imagegen_graph,
    expected_node_order,
)
from june.recipes.imagegen.problem import ImageProblem
from june.recipes.imagegen.runners import (
    make_critique_refine_runners,
    make_imagegen_runners,
)
from june.recipes.imagegen.verify import verify_image_bytes

EXPECTED_NODE_ORDER = ONESHOT_NODE_ORDER
EXPECTED_OFFLINE_BUDGET_SPENT = 1.0
DEFAULT_CRITERIA_MAX_RETRIES = 2


@dataclass
class ImagegenRecipeResult:
    status: str
    problem_id: str
    run_id: str
    recipe: str = "oneshot"
    backend: str | None = None
    verified: bool = False
    prompt: str | None = None
    image_prompt: str | None = None
    image_bytes: bytes | None = None
    critique: dict[str, Any] = field(default_factory=dict)
    first_pass_passed: bool | None = None
    first_image_prompt: str | None = None
    first_image_bytes: bytes | None = None
    first_critique: dict[str, Any] = field(default_factory=dict)
    acceptance_spec: dict[str, Any] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    max_retries: int | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)
    turns: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    graph_status: str | None = None
    budget_spent: float = 0.0
    budget_level: str | None = None
    event_types: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    access_checks: list[dict[str, Any]] = field(default_factory=list)
    node_statuses: dict[str, str] = field(default_factory=dict)
    graph: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    checkpoint_durability: str | None = None
    checkpoint_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.verified


def run_imagegen_recipe(
    problem: ImageProblem,
    generator: ImageGenerator,
    *,
    recipe: RecipeKind = "oneshot",
    crafter: PromptCrafter | None = None,
    critic: VisionCritic | None = None,
    evaluator: ImageEvaluator | None = None,
    max_retries: int = DEFAULT_CRITERIA_MAX_RETRIES,
    checkpoint_path: str | None = None,
    grants: list[object] | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> ImagegenRecipeResult:
    if recipe == "criteria_refine":
        if crafter is None or evaluator is None:
            raise ValueError("criteria_refine requires crafter and evaluator")
        return run_criteria_refine_loop(
            problem,
            generator,
            crafter=crafter,
            evaluator=evaluator,
            max_retries=max_retries,
            checkpoint_path=checkpoint_path,
            on_phase=on_phase,
        )

    from mechaharness.host_kit import host_graph_executor

    bound = bound_run_for_imagegen(problem.id, recipe=recipe)
    if recipe == "critique_refine":
        if crafter is None or critic is None:
            raise ValueError("critique_refine requires crafter and critic")
        graph = build_critique_refine_graph(problem, run_id=bound.run_id)
        state: dict[str, Any] = {"problem": problem, "problem_id": problem.id}
        runners = make_critique_refine_runners(
            generator, crafter, critic, state=state, on_phase=on_phase
        )
        turn_sources = [generator, crafter, critic]
    else:
        graph = build_imagegen_graph(problem, run_id=bound.run_id)
        state = {"problem": problem, "problem_id": problem.id}
        runners = make_imagegen_runners(
            generator, state=state, on_phase=on_phase
        )
        turn_sources = [generator]

    executor = host_graph_executor(
        runners=runners,
        checkpoint_path=checkpoint_path,
        agent_id="june-imagegen",
        grants=grants,
    )
    result = run_coro_sync(
        executor.run(
            graph,
            budget_policy=bound.budget.to_mechaharness(),
            run_id=bound.run_id,
            resume=False,
        )
    )
    verified = bool(state.get("verified"))
    failures = list(state.get("failures") or [])
    status = "ok" if result.status == "ok" and verified else "failed"
    raw_events = list(getattr(result, "events", None) or [])
    events = [_serialize_event(event) for event in raw_events]
    event_types = [str(event.get("type") or "") for event in events]
    access_checks = [
        dict(event.get("payload") or {})
        for event in events
        if event.get("type") == "core:access_check"
    ]
    node_statuses = {
        node_id: str(getattr(node.status, "value", node.status))
        for node_id, node in result.graph.nodes.items()
    }
    diagnostics = dict(getattr(result, "diagnostics", None) or {})
    image_bytes = state.get("image_bytes")
    first_image_bytes = state.get("first_image_bytes")
    turns: list[dict[str, Any]] = []
    for source in turn_sources:
        turns.extend(list(getattr(source, "turns", None) or []))
    return ImagegenRecipeResult(
        status=status,
        problem_id=problem.id,
        run_id=bound.run_id,
        recipe=recipe,
        backend=problem.backend,
        verified=verified,
        prompt=state.get("prompt"),
        image_prompt=state.get("image_prompt"),
        image_bytes=image_bytes if isinstance(image_bytes, (bytes, bytearray)) else None,
        critique=dict(state.get("critique") or {}),
        first_pass_passed=state.get("first_pass_passed"),
        first_image_prompt=(
            str(state["first_image_prompt"])
            if state.get("first_image_prompt") is not None
            else None
        ),
        first_image_bytes=(
            bytes(first_image_bytes)
            if isinstance(first_image_bytes, (bytes, bytearray))
            else None
        ),
        first_critique=dict(state.get("first_critique") or {}),
        failures=failures,
        turns=turns,
        error=getattr(result, "error", None)
        or (None if verified else "verification_failed"),
        graph_status=getattr(result, "status", None),
        budget_spent=float(getattr(result, "budget_spent", 0.0) or 0.0),
        budget_level=str(getattr(result, "budget_level", "") or "") or None,
        event_types=event_types,
        events=events,
        access_checks=access_checks,
        node_statuses=node_statuses,
        graph=_serialize_graph(result.graph),
        diagnostics=diagnostics,
        checkpoint_durability=str(diagnostics.get("checkpoint_durability") or "")
        or None,
        checkpoint_path=checkpoint_path,
    )


def run_criteria_refine_loop(
    problem: ImageProblem,
    generator: ImageGenerator,
    *,
    crafter: PromptCrafter,
    evaluator: ImageEvaluator,
    max_retries: int = DEFAULT_CRITERIA_MAX_RETRIES,
    checkpoint_path: str | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> ImagegenRecipeResult:
    """Host compose loop: craft → (generate → evaluate_criteria → refine?)×N.

    ``max_retries`` is the number of *repair* attempts after the first generate.
    Total generate/evaluate rounds = ``max_retries + 1``.
    """
    del checkpoint_path  # evaluate soft-point may use its own checkpoints later
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")

    def _notify(phase: str) -> None:
        if on_phase is not None:
            on_phase(phase)

    run_id = f"imagegen-criteria-{problem.id}-{uuid4().hex[:8]}"
    prompt_text = problem.prompt_text()
    _notify("craft_prompt")
    image_prompt = crafter.craft(problem, prior_critique=None)
    prior_spec: Any = None
    attempts: list[dict[str, Any]] = []
    first_image_bytes: bytes | None = None
    first_image_prompt: str | None = None
    first_critique: dict[str, Any] = {}
    first_pass_passed: bool | None = None
    acceptance_spec: dict[str, Any] = {}
    last_result: EvaluateResult | None = None
    image_bytes: bytes | None = None

    total_rounds = max_retries + 1
    _notify("attempt_loop")
    for attempt in range(total_rounds):
        seed = int(problem.seed) + attempt
        data = generator.generate(
            prompt=image_prompt,
            negative_prompt=problem.negative_prompt,
            backend=problem.backend,
            width=problem.width,
            height=problem.height,
            seed=seed,
            steps=problem.steps,
        )
        eval_result = evaluator.evaluate(
            problem,
            data,
            image_prompt=image_prompt,
            prior_spec=prior_spec,
        )
        last_result = eval_result
        image_bytes = data
        if eval_result.acceptance_spec:
            acceptance_spec = dict(eval_result.acceptance_spec)
            prior_spec = acceptance_spec
        critique = eval_result.to_critique_dict()
        attempts.append(
            {
                "attempt": attempt,
                "seed": seed,
                "image_prompt": image_prompt,
                "image_bytes": len(data),
                "passed": eval_result.passed,
                "summary": eval_result.summary,
                "failed": list(eval_result.failed),
                "score": dict(eval_result.score),
            }
        )
        if attempt == 0:
            first_image_bytes = data
            first_image_prompt = image_prompt
            first_critique = critique
            first_pass_passed = bool(eval_result.passed)

        if eval_result.passed:
            break
        if attempt < max_retries:
            image_prompt = crafter.craft(problem, prior_critique=critique)

    _notify("verify")
    byte_failures = verify_image_bytes(
        bytes(image_bytes or b""),
        min_bytes=problem.min_bytes,
        require_png=problem.require_png,
    )
    passed_eval = bool(last_result.passed) if last_result else False
    ok = (not byte_failures) and passed_eval
    failures = list(byte_failures)
    if not passed_eval:
        failures.append(
            {
                "reason": "criteria_failed",
                "failed": list(last_result.failed) if last_result else [],
                "notes": last_result.summary if last_result else None,
                "attempts": len(attempts),
                "max_retries": max_retries,
            }
        )

    turns: list[dict[str, Any]] = []
    turns.extend(list(getattr(generator, "turns", None) or []))
    turns.extend(list(getattr(crafter, "turns", None) or []))
    turns.extend(list(getattr(evaluator, "turns", None) or []))

    # Lightweight attempt turns for observability (omit raw image bytes).
    for row in attempts:
        turns.append(
            {
                "index": len(turns),
                "role": "criteria_refine_attempt",
                "kind": "host_loop",
                "response": {k: v for k, v in row.items()},
            }
        )

    return ImagegenRecipeResult(
        status="ok" if ok else "failed",
        problem_id=problem.id,
        run_id=run_id,
        recipe="criteria_refine",
        backend=problem.backend,
        verified=ok,
        prompt=prompt_text,
        image_prompt=image_prompt,
        image_bytes=image_bytes,
        critique=last_result.to_critique_dict() if last_result else {},
        first_pass_passed=first_pass_passed,
        first_image_prompt=first_image_prompt,
        first_image_bytes=first_image_bytes,
        first_critique=first_critique,
        acceptance_spec=acceptance_spec,
        attempts=attempts,
        max_retries=max_retries,
        failures=failures,
        turns=turns,
        error=None if ok else "verification_failed",
        budget_spent=float(0.25 + len(attempts) * 1.75),
        event_types=["june:criteria_refine_loop"],
        diagnostics={
            "compose": "host_loop",
            "evaluate_recipe": "june.imagegen.evaluate_criteria",
            "max_retries": max_retries,
            "attempt_count": len(attempts),
            "hf": "HF-03 nested recipe bind via soft-point call (no MH tile yet)",
        },
    )


def expected_nodes(recipe: RecipeKind) -> tuple[str, ...]:
    return expected_node_order(recipe)


def _serialize_event(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        dumped = event.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(event, dict):
        return dict(event)
    return {
        "type": str(getattr(event, "type", "") or ""),
        "payload": getattr(event, "payload", None),
    }


def _serialize_graph(graph: Any) -> dict[str, Any]:
    if hasattr(graph, "model_dump"):
        dumped = graph.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    return {}
