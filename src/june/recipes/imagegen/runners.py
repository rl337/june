"""Graph node runners for incubating ``june.imagegen`` recipes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from june.recipes.imagegen.critics import PromptCrafter, VisionCritic
from june.recipes.imagegen.generators import ImageGenerator
from june.recipes.imagegen.problem import ImageProblem, problem_by_id
from june.recipes.imagegen.verify import verify_image_bytes


def make_imagegen_runners(
    generator: ImageGenerator,
    *,
    state: dict[str, Any] | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> list[Any]:
    from mechaharness.graph import NodeStatus
    from mechaharness.graph_executor import CallableGraphNodeRunner, NodeOutcome

    shared: dict[str, Any] = state if state is not None else {}

    def _notify(phase: str) -> None:
        if on_phase is not None:
            on_phase(phase)

    async def prompt_node(node: Any, context: Any) -> Any:
        del context
        _notify("prompt")
        problem = _problem_from_payload(node.payload, shared)
        text = problem.prompt_text()
        shared["problem"] = problem
        shared["prompt"] = text
        shared["image_prompt"] = problem.prompt
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"problem_id": problem.id, "prompt": text},
            cost_units=0.0,
        )

    async def generate_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("generate")
        return _generate(shared, generator, NodeStatus, NodeOutcome, cost_units=1.0)

    async def persist_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("persist")
        return _persist(shared, NodeStatus, NodeOutcome)

    async def verify_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("verify")
        problem = shared.get("problem")
        data = shared.get("image_bytes") or b""
        if not isinstance(problem, ImageProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED, payload={}, error="missing_problem"
            )
        failures = verify_image_bytes(
            bytes(data),
            min_bytes=problem.min_bytes,
            require_png=problem.require_png,
        )
        ok = not failures
        shared["verified"] = ok
        shared["failures"] = failures
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED if ok else NodeStatus.FAILED,
            payload={"verified": ok, "failures": failures, "bytes": len(data)},
            error=None if ok else f"{len(failures)} verification failure(s)",
            cost_units=0.0,
        )

    return [
        CallableGraphNodeRunner(["june.imagegen.prompt"], prompt_node),
        CallableGraphNodeRunner(["june.imagegen.generate"], generate_node),
        CallableGraphNodeRunner(["june.imagegen.persist"], persist_node),
        CallableGraphNodeRunner(["june.imagegen.verify"], verify_node),
    ]


def make_critique_refine_runners(
    generator: ImageGenerator,
    crafter: PromptCrafter,
    critic: VisionCritic,
    *,
    state: dict[str, Any] | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> list[Any]:
    from mechaharness.graph import NodeStatus
    from mechaharness.graph_executor import CallableGraphNodeRunner, NodeOutcome

    shared: dict[str, Any] = state if state is not None else {}

    def _notify(phase: str) -> None:
        if on_phase is not None:
            on_phase(phase)

    async def goal_node(node: Any, context: Any) -> Any:
        del context
        _notify("goal")
        problem = _problem_from_payload(node.payload, shared)
        text = problem.prompt_text()
        shared["problem"] = problem
        shared["prompt"] = text
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"problem_id": problem.id, "prompt": text},
            cost_units=0.0,
        )

    async def craft_prompt_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("craft_prompt")
        problem = shared.get("problem")
        if not isinstance(problem, ImageProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED, payload={}, error="missing_problem"
            )
        image_prompt = crafter.craft(problem, prior_critique=None)
        shared["image_prompt"] = image_prompt
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"image_prompt": image_prompt},
            cost_units=0.25,
        )

    async def generate_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("generate")
        return _generate(shared, generator, NodeStatus, NodeOutcome, cost_units=1.0)

    async def persist_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("persist")
        return _persist(shared, NodeStatus, NodeOutcome)

    async def critique_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("critique")
        problem = shared.get("problem")
        data = shared.get("image_bytes") or b""
        image_prompt = str(shared.get("image_prompt") or "")
        if not isinstance(problem, ImageProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED, payload={}, error="missing_problem"
            )
        critique = critic.critique(
            problem, bytes(data), image_prompt=image_prompt
        )
        shared["critique"] = critique
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"critique": critique},
            cost_units=0.5,
        )

    async def diagnose_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("diagnose")
        critique = dict(shared.get("critique") or {})
        passed = bool(critique.get("passed"))
        shared["first_pass_passed"] = passed
        shared["skip_repair"] = passed
        # Keep first-pass artifacts even if repair overwrites image_bytes later.
        shared["first_critique"] = critique
        shared["first_image_prompt"] = shared.get("image_prompt")
        data = shared.get("image_bytes")
        if isinstance(data, (bytes, bytearray)) and data:
            shared["first_image_bytes"] = bytes(data)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"first_pass_passed": passed, "critique": critique},
            cost_units=0.0,
        )

    async def refine_prompt_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("refine_prompt")
        problem = shared.get("problem")
        if not isinstance(problem, ImageProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED, payload={}, error="missing_problem"
            )
        if shared.get("skip_repair"):
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"skipped": True, "image_prompt": shared.get("image_prompt")},
                cost_units=0.0,
            )
        image_prompt = crafter.craft(
            problem, prior_critique=dict(shared.get("critique") or {})
        )
        shared["image_prompt"] = image_prompt
        shared["refined_image_prompt"] = image_prompt
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"image_prompt": image_prompt},
            cost_units=0.25,
        )

    async def repair_generate_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("repair_generate")
        if shared.get("skip_repair"):
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"skipped": True, "bytes": len(shared.get("image_bytes") or b"")},
                cost_units=0.0,
            )
        return _generate(shared, generator, NodeStatus, NodeOutcome, cost_units=1.0)

    async def repair_persist_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("repair_persist")
        if shared.get("skip_repair"):
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={"skipped": True, "image_path": shared.get("image_path")},
                cost_units=0.0,
            )
        return _persist(shared, NodeStatus, NodeOutcome)

    async def verify_critique_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("verify_critique")
        problem = shared.get("problem")
        data = shared.get("image_bytes") or b""
        image_prompt = str(shared.get("image_prompt") or "")
        if not isinstance(problem, ImageProblem):
            return NodeOutcome(
                status=NodeStatus.FAILED, payload={}, error="missing_problem"
            )
        byte_failures = verify_image_bytes(
            bytes(data),
            min_bytes=problem.min_bytes,
            require_png=problem.require_png,
        )
        if shared.get("skip_repair"):
            critique = dict(shared.get("critique") or {})
        else:
            critique = critic.critique(
                problem, bytes(data), image_prompt=image_prompt
            )
            shared["final_critique"] = critique
        ok = (not byte_failures) and bool(critique.get("passed"))
        failures = list(byte_failures)
        if not critique.get("passed"):
            failures.append(
                {
                    "reason": "critique_failed",
                    "missing": critique.get("missing"),
                    "forbidden_found": critique.get("forbidden_found"),
                    "notes": critique.get("notes"),
                }
            )
        shared["verified"] = ok
        shared["failures"] = failures
        shared["critique"] = critique
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED if ok else NodeStatus.FAILED,
            payload={"verified": ok, "failures": failures, "critique": critique},
            error=None if ok else f"{len(failures)} verification failure(s)",
            cost_units=0.0 if shared.get("skip_repair") else 0.5,
        )

    return [
        CallableGraphNodeRunner(["june.imagegen.goal"], goal_node),
        CallableGraphNodeRunner(["june.imagegen.craft_prompt"], craft_prompt_node),
        CallableGraphNodeRunner(["june.imagegen.generate"], generate_node),
        CallableGraphNodeRunner(["june.imagegen.persist"], persist_node),
        CallableGraphNodeRunner(["june.imagegen.critique"], critique_node),
        CallableGraphNodeRunner(["june.imagegen.diagnose"], diagnose_node),
        CallableGraphNodeRunner(["june.imagegen.refine_prompt"], refine_prompt_node),
        CallableGraphNodeRunner(["june.imagegen.repair_generate"], repair_generate_node),
        CallableGraphNodeRunner(["june.imagegen.repair_persist"], repair_persist_node),
        CallableGraphNodeRunner(["june.imagegen.verify_critique"], verify_critique_node),
    ]



def _generate(
    shared: dict[str, Any],
    generator: ImageGenerator,
    NodeStatus: Any,
    NodeOutcome: Any,
    *,
    cost_units: float,
) -> Any:
    problem = shared.get("problem")
    if not isinstance(problem, ImageProblem):
        return NodeOutcome(
            status=NodeStatus.FAILED, payload={}, error="missing_problem"
        )
    image_prompt = str(shared.get("image_prompt") or problem.prompt)
    seed = shared.get("repair_seed")
    if seed is None:
        seed = problem.seed
    data = generator.generate(
        prompt=image_prompt,
        negative_prompt=problem.negative_prompt,
        backend=problem.backend,
        width=problem.width,
        height=problem.height,
        seed=int(seed),
        steps=problem.steps,
    )
    shared["image_bytes"] = data
    shared["image_prompt"] = image_prompt
    return NodeOutcome(
        status=NodeStatus.SUCCEEDED,
        payload={
            "bytes": len(data),
            "backend": problem.backend,
            "image_prompt": image_prompt,
        },
        cost_units=cost_units,
    )


def _persist(shared: dict[str, Any], NodeStatus: Any, NodeOutcome: Any) -> Any:
    data = shared.get("image_bytes")
    if not isinstance(data, (bytes, bytearray)) or not data:
        return NodeOutcome(
            status=NodeStatus.FAILED, payload={}, error="missing_image_bytes"
        )
    shared["image_path"] = "image.png"
    return NodeOutcome(
        status=NodeStatus.SUCCEEDED,
        payload={"image_path": "image.png", "bytes": len(data)},
        cost_units=0.0,
    )


def _problem_from_payload(payload: dict[str, Any], shared: dict[str, Any]) -> ImageProblem:
    problem = shared.get("problem") or payload.get("problem")
    if isinstance(problem, ImageProblem):
        return problem
    return problem_by_id(str(payload.get("problem_id") or shared.get("problem_id") or ""))
