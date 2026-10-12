"""Offline tests for june.chat recipe + generate_image tool media."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from june.channels import (
    Channel,
    ChannelMessage,
    ChannelReply,
    ContentPart,
    PartKind,
)
from june.channels.adapters import (
    DiscordAdapter,
    RestChatAdapter,
    TelegramAdapter,
    WebappAdapter,
)
from june.config import JuneSettings, JunesparkSettings
from june.documents import DocumentStore
from june.providers.junespark import JunesparkProvider
from june.recipes.chat import CHAT_NODE_ORDER, build_chat_graph, run_chat_recipe
from june.recipes.imagegen.generators import FixedImageGenerator
from june.tools import ToolRegistry, build_default_tools
from june.tools.imagegen import register_generate_image_tool


class _MockTransport(httpx.BaseTransport):
    def __init__(self, handler: Any) -> None:
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_build_chat_graph_order() -> None:
    message = ChannelMessage(
        channel=Channel.WEBAPP,
        session_id="s",
        parts=[ContentPart.text_part("hi")],
    )
    graph = build_chat_graph(message, run_id="chat-test")
    assert tuple(graph.nodes.keys()) == CHAT_NODE_ORDER


def test_run_chat_recipe_host_kit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200, json={"data": [{"id": "mock-model", "owned_by": "test"}]}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "recipe hello"}}
                ]
            },
        )

    client = httpx.Client(transport=_MockTransport(handler))
    provider = JunesparkProvider(
        JunesparkSettings(base_url="http://junespark.test/v1", api_key="x"),
        client=client,
    )
    tools = build_default_tools(image_generator=FixedImageGenerator())
    phases: list[str] = []
    result = run_chat_recipe(
        ChannelMessage(
            channel=Channel.WEBAPP,
            session_id="s1",
            parts=[ContentPart.text_part("hi")],
        ),
        provider=provider,
        tools=tools,
        settings=JuneSettings(
            junespark=JunesparkSettings(base_url="http://junespark.test/v1"),
        ),
        on_phase=lambda phase, _state: phases.append(phase),
    )
    assert result.ok
    assert result.reply.text() == "recipe hello"
    assert phases == ["refine", "context", "tools", "render"]
    assert "core:graph_node_start" in result.event_types
    client.close()


def test_generate_image_tool_media_round_trip() -> None:
    docs = DocumentStore()
    registry = ToolRegistry()
    register_generate_image_tool(
        registry,
        documents=docs,
        generator=FixedImageGenerator(),
    )
    raw = registry.call(
        "generate_image",
        {"prompt": "a red apple on a table", "recipe": "oneshot"},
    )
    payload = json.loads(raw)
    assert payload.get("ok") is True
    media = payload["media"]
    assert media["kind"] == "image"
    assert media.get("document_id")
    assert docs.load(media["document_id"]) is not None

    # Scripted tool_loop: provider returns a tool call then a final text.
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "mock-tools",
                            "owned_by": "test",
                        }
                    ]
                },
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
                                        "id": "call1",
                                        "type": "function",
                                        "function": {
                                            "name": "generate_image",
                                            "arguments": json.dumps(
                                                {
                                                    "prompt": "a red apple",
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
                    {
                        "message": {
                            "role": "assistant",
                            "content": "here is your image",
                        }
                    }
                ]
            },
        )

    client = httpx.Client(transport=_MockTransport(handler))
    provider = JunesparkProvider(
        JunesparkSettings(base_url="http://junespark.test/v1", api_key="x"),
        client=client,
    )
    # Force tools capability via model id heuristics if needed.
    from june.providers.junespark import ModelCapabilities

    provider.probe_capabilities = lambda _mid: ModelCapabilities(  # type: ignore[method-assign]
        tools=True, vision=False
    )
    provider.select_model = lambda _pref: type(  # type: ignore[method-assign]
        "M",
        (),
        {
            "id": "mock-tools",
            "capabilities": ModelCapabilities(tools=True, vision=False),
        },
    )()

    result = run_chat_recipe(
        ChannelMessage(
            channel=Channel.WEBAPP,
            session_id="img",
            parts=[ContentPart.text_part("draw an apple")],
        ),
        provider=provider,
        tools=registry,
        documents=docs,
        settings=JuneSettings(
            junespark=JunesparkSettings(base_url="http://junespark.test/v1"),
        ),
    )
    assert result.ok
    kinds = [p.kind for p in result.reply.parts]
    assert PartKind.TEXT in kinds
    assert PartKind.IMAGE in kinds
    client.close()


def test_webapp_and_rest_adapters() -> None:
    raw = {"text": "hello", "session_id": "abc"}
    msg = WebappAdapter().to_message(raw)
    assert msg.text() == "hello"
    assert RestChatAdapter().to_message(raw).session_id == "abc"
    with pytest.raises(NotImplementedError):
        TelegramAdapter().to_message(raw)
    with pytest.raises(NotImplementedError):
        DiscordAdapter().from_reply(ChannelReply(parts=[ContentPart.text_part("x")]))
