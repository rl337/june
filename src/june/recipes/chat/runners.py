"""Graph node runners for incubating ``june.chat``."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from june.recipes.chat.engine import ChatEngine, ChatGraphState
from june.recipes.chat.graph import phase_key_for_kind


def make_chat_runners(
    engine: ChatEngine,
    *,
    state: ChatGraphState,
    on_phase: Callable[[str, ChatGraphState], None] | None = None,
    recipe_checkpoints: dict[str, dict[str, Any]] | None = None,
) -> list[Any]:
    from mechaharness.conversational_tool_loop_runner import ConversationalToolLoopRunner
    from mechaharness.graph import NodeStatus
    from mechaharness.graph_executor import CallableGraphNodeRunner, NodeOutcome

    captured = recipe_checkpoints if recipe_checkpoints is not None else {}

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

    async def render_node(node: Any, context: Any) -> Any:
        del context, node
        _notify("june.chat.render_reply")
        engine.render_reply(state)
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"parts": len(state.reply_parts)},
            cost_units=0.0,
        )

    def complete(messages: list[dict[str, Any]], meta: Any) -> dict[str, Any]:
        del meta
        if not state.model:
            return {"role": "assistant", "content": "No model available.", "tool_calls": []}
        use_tools = state.capabilities.tools and bool(engine.tools.specs())
        tool_schemas = engine.tools.openai_tools() if use_tools else None
        response = engine.provider.complete(
            messages,
            model=state.model,
            tools=tool_schemas,
        )
        assistant = engine.provider.extract_assistant(response)
        if not isinstance(assistant, dict):
            return {"role": "assistant", "content": str(assistant), "tool_calls": []}
        if "role" not in assistant:
            assistant = {**assistant, "role": "assistant"}
        if not use_tools:
            assistant = {**assistant, "tool_calls": []}
        return assistant

    def dispatch_tool(name: str, args: Any) -> str:
        call_args = _parse_tool_args(args)
        raw = engine.tools.call(name, call_args)
        if name == "generate_image":
            from june.tools.imagegen import last_generate_image_graph

            ckpt = last_generate_image_graph()
            if ckpt is not None:
                captured[name] = ckpt
        return raw

    inner = ConversationalToolLoopRunner(
        kinds=["conversational_tool_loop", "june.chat.tool_loop"],
        complete=complete,
        dispatch_tool=dispatch_tool,
    )

    class _ToolsRunner:
        """Seed messages, run HF-07 loop, sync state + attach recipe subgraphs."""

        def kinds(self) -> list[str]:
            return list(inner.kinds())

        def required_grants(self) -> list[object]:
            return list(inner.required_grants())

        async def run(self, node: Any, *, context: Any) -> Any:
            _notify("conversational_tool_loop")
            max_turns = max(1, engine.chat.max_tool_turns)
            node.payload = {
                **dict(node.payload or {}),
                "messages": list(state.messages),
                "message_state_key": "messages",
                "max_iterations": max_turns,
                "inference_kind": "inference",
                "tool_call_kind": "tool_call",
            }
            from mechaharness.stop_contract import StopContract

            node.stop_contract = StopContract(
                version="1", max_iterations=max_turns
            ).model_dump(mode="json")
            outcome = await inner.run(node, context=context)
            state.messages = list(node.payload.get("messages") or state.messages)
            state.assistant_text = str(
                node.payload.get("final_text") or state.assistant_text or ""
            )
            subgraph = node.subgraph if isinstance(node.subgraph, dict) else {}
            if captured and isinstance(subgraph.get("nodes"), dict):
                _attach_recipe_checkpoints(subgraph, captured)
                node.subgraph = subgraph
            state.tool_trace = _tool_trace_from_subgraph(subgraph)
            return outcome

    return [
        CallableGraphNodeRunner(["june.chat.refine_input"], refine_node),
        CallableGraphNodeRunner(["june.chat.context_optimize"], context_node),
        _ToolsRunner(),
        CallableGraphNodeRunner(["june.chat.render_reply"], render_node),
    ]


def _parse_tool_args(args: Any) -> dict[str, Any]:
    if isinstance(args, dict):
        return dict(args)
    if isinstance(args, str):
        try:
            loaded = json.loads(args)
            return loaded if isinstance(loaded, dict) else {"prompt": args}
        except json.JSONDecodeError:
            return {"prompt": args}
    return {"prompt": str(args or "")}


def _attach_recipe_checkpoints(
    subgraph: dict[str, Any], captured: dict[str, dict[str, Any]]
) -> None:
    nodes = subgraph.get("nodes")
    if not isinstance(nodes, dict):
        return
    for raw in nodes.values():
        if not isinstance(raw, dict):
            continue
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        name = str(payload.get("tool_name") or "")
        if name in captured and not raw.get("subgraph"):
            raw["subgraph"] = captured[name]
            payload = dict(payload)
            payload["recipe_as_tool"] = True
            raw["payload"] = payload


def _tool_trace_from_subgraph(subgraph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = subgraph.get("nodes") if isinstance(subgraph, dict) else None
    if not isinstance(nodes, dict):
        return []
    trace: list[dict[str, Any]] = []
    for node_id, raw in nodes.items():
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "")
        if kind != "tool_call" and "/tool_call:" not in str(node_id):
            continue
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        if "result" not in payload:
            continue
        result = payload.get("result")
        trace.append(
            {
                "id": payload.get("tool_call_id"),
                "name": payload.get("tool_name"),
                "arguments": payload.get("arguments"),
                "result": result if isinstance(result, str) else json.dumps(result),
            }
        )
    return trace
