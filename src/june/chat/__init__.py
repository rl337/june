"""Façade for incubating interactive ``june.chat`` (see ``june.recipes.chat``)."""

from __future__ import annotations

from collections.abc import Callable

from june.channels import ChannelMessage, ChannelReply
from june.config import JuneSettings
from june.documents import DocumentStore
from june.knowledge import KnowledgeGraph
from june.providers.junespark import JunesparkProvider
from june.recipes.chat import (
    CHAT_NODE_KINDS,
    CHAT_TEMPLATE,
    ChatEngine,
    ChatGraphState,
    run_chat_recipe,
)
from june.tools import ToolRegistry

__all__ = [
    "CHAT_NODE_KINDS",
    "CHAT_TEMPLATE",
    "ChatEngine",
    "ChatGraphRunner",
    "ChatGraphState",
    "execute_chat_graph",
]


class ChatGraphRunner:
    """Bind soft points and run ``june.chat`` via host_kit (recipe façade)."""

    def __init__(
        self,
        *,
        provider: JunesparkProvider,
        tools: ToolRegistry,
        settings: JuneSettings | None = None,
        documents: DocumentStore | None = None,
        knowledge: KnowledgeGraph | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.settings = settings or JuneSettings()
        self.documents = documents
        self.knowledge = knowledge

    def run(
        self,
        message: ChannelMessage,
        *,
        on_phase: Callable[[str, ChatGraphState], None] | None = None,
        checkpoint_path: str | None = None,
        run_id: str | None = None,
    ) -> ChannelReply:
        result = run_chat_recipe(
            message,
            provider=self.provider,
            tools=self.tools,
            settings=self.settings,
            documents=self.documents,
            knowledge=self.knowledge,
            checkpoint_path=checkpoint_path,
            on_phase=on_phase,
            run_id=run_id,
        )
        return result.reply


def execute_chat_graph(
    message: ChannelMessage,
    *,
    provider: JunesparkProvider,
    tools: ToolRegistry,
    settings: JuneSettings | None = None,
    documents: DocumentStore | None = None,
    knowledge: KnowledgeGraph | None = None,
) -> ChannelReply:
    return ChatGraphRunner(
        provider=provider,
        tools=tools,
        settings=settings,
        documents=documents,
        knowledge=knowledge,
    ).run(message)
