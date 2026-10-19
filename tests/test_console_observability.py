"""Console observability: event loop stays live; nested tool graphs zoom."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("mechaharness")

from june.bootstrap import build_app
from june.channels import Channel, ChannelMessage, ChatService, ContentPart
from june.chat import ChatGraphRunner
from june.config import JuneSettings, JunesparkSettings
from june.console.hub import ConsoleHub
from june.console.server import create_app
from june.harness.cron_graph import CHAT_PARENT_NODE_ID, build_console_cron_graph
from june.orchestrator import Orchestrator
from june.providers.junespark import JunesparkProvider
from june.recipes.chat import run_chat_recipe
from june.recipes.imagegen.generators import FixedImageGenerator
from june.tools import build_default_tools


class _MockTransport(httpx.BaseTransport):
    def __init__(self, handler: Any) -> None:
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_tool_loop_expands_nested_rounds_in_checkpoint() -> None:
    """HF-07: tools.subgraph contains inference / tool_call nodes after a tool turn."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200, json={"data": [{"id": "tool-model", "owned_by": "test"}]}
            )
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "type": "function",
                                        "function": {
                                            "name": "generate_image",
                                            "arguments": json.dumps(
                                                {
                                                    "prompt": "a blue square",
                                                    "recipe": "oneshot",
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "here is the image"}}
                ]
            },
        )

    client = httpx.Client(transport=_MockTransport(handler))
    provider = JunesparkProvider(
        JunesparkSettings(base_url="http://junespark.test/v1", api_key="x"),
        client=client,
    )
    tools = build_default_tools(image_generator=FixedImageGenerator())
    tapped: list[str] = []
    result = run_chat_recipe(
        ChannelMessage(
            channel=Channel.WEBAPP,
            session_id="nest1",
            parts=[ContentPart.text_part("make an image")],
        ),
        provider=provider,
        tools=tools,
        settings=JuneSettings(
            junespark=JunesparkSettings(base_url="http://junespark.test/v1"),
        ),
        on_event=lambda e: tapped.append(str(getattr(e, "type", e))),
    )
    assert result.ok
    tools_node = result.graph.get("nodes", {}).get("tools")
    assert isinstance(tools_node, dict)
    subgraph = tools_node.get("subgraph") or {}
    sub_nodes = subgraph.get("nodes") or {}
    assert sub_nodes, "expected HF-07 expanded tools.subgraph"
    kinds = {raw.get("kind") for raw in sub_nodes.values() if isinstance(raw, dict)}
    assert "inference" in kinds
    assert "tool_call" in kinds
    tool_nodes = [
        raw
        for raw in sub_nodes.values()
        if isinstance(raw, dict) and raw.get("kind") == "tool_call"
    ]
    assert tool_nodes
    nested = tool_nodes[0].get("subgraph") or {}
    nested_nodes = nested.get("nodes") or {}
    assert nested_nodes, "expected HF-08 imagegen child under tool_call"
    nested_kinds = {
        raw.get("kind") for raw in nested_nodes.values() if isinstance(raw, dict)
    }
    assert "june.imagegen.generate" in nested_kinds or any(
        "generate" in str(k) for k in nested_kinds
    )
    assert tapped, "expected HF-05 tapped events"
    client.close()


@pytest.mark.asyncio
async def test_chat_api_does_not_block_snapshot() -> None:
    """Blocking chat work must not freeze /api/snapshot (event-loop hang)."""
    from httpx import ASGITransport, AsyncClient

    gate = threading.Event()
    started = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "slow-model"}]})
        started.set()
        assert gate.wait(timeout=5.0), "snapshot did not release chat gate"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "done"}}]},
        )

    settings = JuneSettings(
        junespark=JunesparkSettings(base_url="http://junespark.test/v1", model="slow-model"),
    )
    built = build_app(settings)
    provider: JunesparkProvider = built[JunesparkProvider]
    provider.close()
    provider._client = httpx.Client(transport=_MockTransport(handler))  # noqa: SLF001
    provider._owns_client = True  # noqa: SLF001
    hub = ConsoleHub()
    hub.set_structure_checkpoint(build_console_cron_graph().checkpoint())
    app = create_app(
        hub,
        settings=settings,
        orchestrator=built[Orchestrator],
        provider=provider,
        chat_service=built[ChatService],
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        chat_task = asyncio.create_task(
            client.post("/api/chat", json={"text": "hold please", "session_id": "obs1"})
        )
        deadline = time.monotonic() + 5.0
        while not started.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        assert started.is_set(), "chat never reached the provider"

        t0 = time.monotonic()
        snap = await client.get("/api/snapshot")
        elapsed = time.monotonic() - t0
        assert snap.status_code == 200
        assert elapsed < 1.0, f"snapshot blocked for {elapsed:.2f}s (event loop hung)"
        body = snap.json()
        running_chat = [
            i
            for i in body.get("instances") or []
            if i.get("bucket") == "chat" and i.get("status") == "running"
        ]
        assert running_chat, "chat instance missing from snapshot during turn"
        world_ids = {n["id"] for n in body.get("world", {}).get("nodes") or []}
        assert CHAT_PARENT_NODE_ID in world_ids

        gate.set()
        chat = await chat_task
        assert chat.status_code == 200
        assert chat.json()["text"] == "done"


@pytest.mark.asyncio
async def test_chat_with_generate_image_nests_under_tools() -> None:
    from httpx import ASGITransport, AsyncClient

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": "tool-model", "owned_by": "test"}]},
            )
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "type": "function",
                                        "function": {
                                            "name": "generate_image",
                                            "arguments": json.dumps(
                                                {
                                                    "prompt": "a blue square",
                                                    "recipe": "oneshot",
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "here is the image"}}
                ]
            },
        )

    settings = JuneSettings(
        junespark=JunesparkSettings(base_url="http://junespark.test/v1", model="tool-model"),
    )
    built = build_app(settings)
    orch: Orchestrator = built[Orchestrator]
    provider: JunesparkProvider = built[JunesparkProvider]
    provider.close()
    provider._client = httpx.Client(transport=_MockTransport(handler))  # noqa: SLF001
    provider._owns_client = True  # noqa: SLF001
    tools = build_default_tools(
        documents=orch.documents,
        knowledge=orch.knowledge,
        settings=settings,
        image_generator=FixedImageGenerator(),
    )
    runner = ChatGraphRunner(
        provider=provider,
        tools=tools,
        settings=settings,
        documents=orch.documents,
        knowledge=orch.knowledge,
    )
    orch.attach_chat(provider=provider, tools=tools, chat_runner=runner)
    chat_service = ChatService(orch)

    hub = ConsoleHub()
    hub.set_structure_checkpoint(build_console_cron_graph().checkpoint())
    app = create_app(
        hub,
        settings=settings,
        orchestrator=orch,
        provider=provider,
        chat_service=chat_service,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        chat = await client.post(
            "/api/chat",
            json={"text": "make an image of a blue square", "session_id": "img1"},
        )
        assert chat.status_code == 200, chat.text
        snap = await client.get("/api/snapshot")
        assert snap.status_code == 200
        body = snap.json()
        finished = [i for i in body.get("instances") or [] if i.get("bucket") == "chat"]
        assert finished
        assert finished[0].get("status") in {"ok", "succeeded"}
        # No parallel imagegen soft lane on the structure graph.
        world_ids = {n["id"] for n in body.get("world", {}).get("nodes") or []}
        assert "june.console.cron:imagegen" not in world_ids
        assert CHAT_PARENT_NODE_ID in world_ids
