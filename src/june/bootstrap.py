"""Assemble the June application graph from settings (used by JuneConfig)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from june.channels import ChatService
from june.chat import ChatGraphRunner
from june.config import JuneSettings
from june.orchestrator import Orchestrator
from june.providers.junespark import JunesparkProvider
from june.tools import ToolRegistry, build_default_tools


def build_app(settings: JuneSettings) -> dict[type, Any]:
    """Return type→instance map for pyiv ``register_instance``."""
    data_dir = Path(settings.data_dir) if settings.data_dir else None
    orch = Orchestrator(data_dir, settings=settings)
    provider = JunesparkProvider(settings)
    tools = build_default_tools(documents=orch.documents, knowledge=orch.knowledge)
    chat_runner = ChatGraphRunner(
        provider=provider,
        tools=tools,
        settings=settings,
        documents=orch.documents,
        knowledge=orch.knowledge,
    )
    orch.attach_chat(provider=provider, tools=tools, chat_runner=chat_runner)
    chat_service = ChatService(orch)
    return {
        JuneSettings: settings,
        Orchestrator: orch,
        JunesparkProvider: provider,
        ToolRegistry: tools,
        ChatGraphRunner: chat_runner,
        ChatService: chat_service,
    }
