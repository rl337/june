"""Graph node runners for incubating ``june.chat``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from june.recipes.chat.engine import ChatEngine, ChatGraphState
from june.recipes.chat.graph import phase_key_for_kind


def make_chat_runners(
    engine: ChatEngine,
    *,
    state: ChatGraphState,
    on_phase: Callable[[str, ChatGraphState], None] | None = None,
) -> list[Any]:
    from mechaharness.graph import NodeStatus
    from mechaharness.graph_executor import CallableGraphNodeRunner, NodeOutcome

    def _notify(kind: str) -> None:
        if on_phase is None:
            return
        phase = phase_key_for_kind(kind)
        if phase is not None:
            on_phase(phase, state)

    async def refine_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("june.chat.refine_input")
        engine.refine_input(state)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"model": state.model, "parts": len(state.message.parts)},
            cost_units=0.1,
        )

    async def context_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("june.chat.context_optimize")
        engine.context_optimize(state)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "context_refs": len(state.context_refs),
                "messages": len(state.messages),
            },
            cost_units=0.1,
        )

    async def tools_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("june.chat.tool_loop")
        engine.tool_loop(state)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={
                "tool_calls": len(state.tool_trace),
                "assistant_chars": len(state.assistant_text or ""),
            },
            cost_units=1.0,
        )

    async def render_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("june.chat.render_reply")
        engine.render_reply(state)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"parts": len(state.reply_parts)},
            cost_units=0.0,
        )

    return [
        CallableGraphNodeRunner(["june.chat.refine_input"], refine_node),
        CallableGraphNodeRunner(["june.chat.context_optimize"], context_node),
        CallableGraphNodeRunner(["june.chat.tool_loop"], tools_node),
        CallableGraphNodeRunner(["june.chat.render_reply"], render_node),
    ]
