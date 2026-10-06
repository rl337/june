"""Tests for settings, june.chat subgraph, and console chat API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from june.bootstrap import build_app
from june.channels import Channel, ChannelMessage, ChatService, ContentPart, PartKind
from june.chat import CHAT_TEMPLATE, ChatGraphRunner, execute_chat_graph
from june.config import JuneSettings, JunesparkSettings, load_settings
from june.console.hub import ConsoleHub
from june.console.server import create_app
from june.orchestrator import Orchestrator
from june.providers.junespark import JunesparkProvider, infer_capabilities
from june.templates import TemplateRegistry


class _MockTransport(httpx.BaseTransport):
    def __init__(self, handler: Any) -> None:
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_load_settings_yaml_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "junespark:\n  base_url: http://yaml.example/v1\n  api_key: from-yaml\n"
        "console:\n  port: 9001\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JUNESPARK_BASE_URL", "http://env.example/v1")
    settings = load_settings(cfg, env_file=tmp_path / "missing.env")
    assert settings.junespark.base_url == "http://env.example/v1"
    assert settings.junespark.api_key == "from-yaml"
    assert settings.console.port == 9001
    assert settings.require_junespark_base_url().endswith("/v1")


def test_infer_capabilities() -> None:
    assert infer_capabilities("nemotron-35-lightning").tools is True
    assert infer_capabilities("qwen2.5-vl-7b").vision is True
    assert infer_capabilities("text-embedding-3").tools is False


def test_june_chat_template_registered() -> None:
    registry = TemplateRegistry()
    spec = registry.get(CHAT_TEMPLATE)
    assert spec is not None
    assert "june.chat.tool_loop" in spec.node_kinds


def test_chat_graph_with_mock_provider() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": "mock-model", "owned_by": "test"}]},
            )
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content.decode("utf-8"))
            assert body["model"] == "mock-model"
            assert body["messages"][-1]["role"] == "user"
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "hello from mock",
                            }
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": "missing"})

    client = httpx.Client(transport=_MockTransport(handler))
    provider = JunesparkProvider(
        JunesparkSettings(base_url="http://junespark.test/v1", api_key="x"),
        client=client,
    )
    from june.tools import build_default_tools

    tools = build_default_tools()
    reply = execute_chat_graph(
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
    )
    assert reply.text() == "hello from mock"
    assert reply.model == "mock-model"
    client.close()


def test_refine_strips_vision_when_unsupported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "text-only"}]})
        body = json.loads(request.content.decode("utf-8"))
        assert isinstance(body["messages"][-1]["content"], str)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    client = httpx.Client(transport=_MockTransport(handler))
    provider = JunesparkProvider(
        JunesparkSettings(base_url="http://junespark.test/v1"),
        client=client,
    )
    from june.tools import ToolRegistry

    runner = ChatGraphRunner(
        provider=provider,
        tools=ToolRegistry(),
        settings=JuneSettings(
            junespark=JunesparkSettings(base_url="http://junespark.test/v1"),
        ),
    )
    reply = runner.run(
        ChannelMessage(
            channel=Channel.WEBAPP,
            session_id="s1",
            parts=[
                ContentPart.text_part("what is this?"),
                ContentPart(kind=PartKind.IMAGE, url="data:image/png;base64,aaa", name="x.png"),
            ],
        )
    )
    assert reply.text() == "ok"
    assert any("vision" in n for n in reply.notes)
    client.close()


def test_web_console_chat_api(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "api-model"}]})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "pong"}}]},
        )

    settings = JuneSettings(
        data_dir=str(tmp_path),
        junespark=JunesparkSettings(base_url="http://junespark.test/v1", model="api-model"),
    )
    built = build_app(settings)
    provider: JunesparkProvider = built[JunesparkProvider]
    provider.close()
    provider._client = httpx.Client(transport=_MockTransport(handler))  # noqa: SLF001
    provider._owns_client = True  # noqa: SLF001
    app = create_app(
        ConsoleHub(),
        settings=settings,
        orchestrator=built[Orchestrator],
        provider=provider,
        chat_service=built[ChatService],
    )
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["junespark_configured"] is True
    models = client.get("/api/models")
    assert models.status_code == 200
    assert models.json()["active"]["id"] == "api-model"
    chat = client.post("/api/chat", json={"text": "ping", "session_id": "t1"})
    assert chat.status_code == 200
    body = chat.json()
    assert body["text"] == "pong"
    assert body["model"] == "api-model"
    html = client.get("/")
    assert html.status_code == 200
    assert "June Console" in html.text
