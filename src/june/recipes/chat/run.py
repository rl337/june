"""Run incubating ``june.chat`` through MechaHarness host_kit."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from june.async_util import run_coro_sync
from june.channels import ChannelMessage, ChannelReply
from june.config import JuneSettings
from june.documents import DocumentStore
from june.knowledge import KnowledgeGraph
from june.providers.junespark import JunesparkProvider
from june.recipes.chat.engine import ChatEngine, ChatGraphState
from june.recipes.chat.graph import (
    CHAT_NODE_ORDER,
    CHAT_TEMPLATE,
    bound_run_for_chat,
    build_chat_graph,
)
from june.recipes.chat.runners import make_chat_runners
from june.tools import ToolRegistry

EXPECTED_NODE_ORDER = CHAT_NODE_ORDER


@dataclass
class ChatRecipeResult:
    status: str
    reply: ChannelReply
    run_id: str
    event_types: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    node_statuses: dict[str, str] = field(default_factory=dict)
    budget_spent: float = 0.0
    graph_status: str | None = None
    error: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok" and bool(self.reply.text() or self.reply.parts)


def run_chat_recipe(
    message: ChannelMessage,
    *,
    provider: JunesparkProvider,
    tools: ToolRegistry,
    settings: JuneSettings | None = None,
    documents: DocumentStore | None = None,
    knowledge: KnowledgeGraph | None = None,
    checkpoint_path: str | None = None,
    grants: list[object] | None = None,
    on_phase: Callable[[str, ChatGraphState], None] | None = None,
    run_id: str | None = None,
) -> ChatRecipeResult:
    """Bind + run ``june.chat`` (host_kit)."""
    from mechaharness.host_kit import host_graph_executor

    engine = ChatEngine(
        provider=provider,
        tools=tools,
        settings=settings,
        documents=documents,
        knowledge=knowledge,
    )
    state = ChatGraphState(message=message)
    if run_id:
        state.run_id = run_id
    bound = bound_run_for_chat(message.session_id)
    if run_id:
        # Keep console hub instance id aligned with the MH graph id.
        bound.run_id = run_id
    graph = build_chat_graph(message, run_id=bound.run_id)
    runners = make_chat_runners(engine, state=state, on_phase=on_phase)
    executor = host_graph_executor(
        runners=runners,
        checkpoint_path=checkpoint_path,
        agent_id="june-chat",
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
    reply = engine.to_reply(state)
    reply.run_id = bound.run_id
    raw_events = list(getattr(result, "events", None) or [])
    events = [_serialize_event(event) for event in raw_events]
    event_types = [str(event.get("type") or "") for event in events]
    node_statuses = {
        node_id: str(getattr(node.status, "value", node.status))
        for node_id, node in result.graph.nodes.items()
    }
    ok = result.status == "ok" and bool(reply.text() or reply.parts)
    return ChatRecipeResult(
        status="ok" if ok else "failed",
        reply=reply,
        run_id=bound.run_id,
        event_types=event_types,
        events=events,
        node_statuses=node_statuses,
        budget_spent=float(getattr(result, "budget_spent", 0.0) or 0.0),
        graph_status=getattr(result, "status", None),
        error=None if ok else (getattr(result, "error", None) or "chat_failed"),
        diagnostics={
            "template": CHAT_TEMPLATE,
            "compose": "host_kit",
            **dict(getattr(result, "diagnostics", None) or {}),
        },
    )


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
