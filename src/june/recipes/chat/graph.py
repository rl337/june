"""Build incubating ``june.chat`` execution graphs."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from june.budget import SubgraphBudget
from june.channels import ChannelMessage
from june.harness import BoundRun

CHAT_TEMPLATE = "june.chat"
CHAT_NODE_KINDS = [
    "june.chat.refine_input",
    "june.chat.context_optimize",
    "conversational_tool_loop",
    "june.chat.render_reply",
]

CHAT_NODE_ORDER = (
    "refine",
    "context",
    "tools",
    "render",
)

# tools uses MH HF-07 ConversationalToolLoopRunner (kind conversational_tool_loop).
_PHASE_SPECS = (
    ("refine", "june.chat.refine_input", "refine input"),
    ("context", "june.chat.context_optimize", "context optimize"),
    ("tools", "conversational_tool_loop", "tool loop"),
    ("render", "june.chat.render_reply", "render reply"),
)


def bound_run_for_chat(session_id: str) -> BoundRun:
    return BoundRun(
        run_id=f"chat-{session_id}-{uuid4().hex[:8]}",
        template_name=CHAT_TEMPLATE,
        bindings={"session_id": session_id, "recipe": "chat"},
        budget=SubgraphBudget(),
        grants=[],
        node_kinds=list(CHAT_NODE_KINDS),
    )


def build_chat_graph(
    message: ChannelMessage, *, run_id: str | None = None
) -> Any:
    """refine → context → tools → render."""
    from mechaharness.graph import DependencyEdge, ExecutionGraph, GraphNode
    from mechaharness.stop_contract import StopContract

    rid = run_id or f"chat-{message.session_id}-{uuid4().hex[:8]}"
    graph = ExecutionGraph(id=rid, goal=f"chat:{message.session_id}")
    base = {
        "session_id": message.session_id,
        "channel": message.channel.value,
        "recipe": CHAT_TEMPLATE,
    }
    for node_id, kind, goal in _PHASE_SPECS:
        payload = dict(base)
        kwargs: dict[str, Any] = {
            "id": node_id,
            "kind": kind,
            "goal": goal,
            "payload": payload,
            "max_attempts": 1,
        }
        if node_id == "tools":
            # HF-07: runtime expands round_i → {inference, tool_call*} under subgraph.
            kwargs["repeating"] = True
            kwargs["stop_contract"] = StopContract(
                version="1", max_iterations=8
            ).model_dump(mode="json")
            payload.update(
                {
                    "phase": "tools",
                    "inference_kind": "inference",
                    "tool_call_kind": "tool_call",
                    "message_state_key": "messages",
                    "max_iterations": 8,
                }
            )
        graph.add_node(GraphNode(**kwargs))
    order = [node_id for node_id, _kind, _goal in _PHASE_SPECS]
    for left, right in zip(order, order[1:]):
        graph.add_dependency(
            DependencyEdge(
                from_node=left,
                to_node=right,
                types=["control"],
                reason="june.chat sequence",
            )
        )
    return graph


def phase_key_for_kind(kind: str) -> str | None:
    for node_id, node_kind, _goal in _PHASE_SPECS:
        if node_kind == kind:
            return node_id
    if kind in {"june.chat.tool_loop", "conversational_tool_loop"}:
        return "tools"
    return None
