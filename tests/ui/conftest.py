"""Fixtures for console browser UI tests (Playwright + uvicorn)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import pytest

fastapi = pytest.importorskip("fastapi")
del fastapi
pytest.importorskip("uvicorn")
playwright = pytest.importorskip("playwright")
del playwright

from playwright.sync_api import Browser, Page, sync_playwright  # noqa: E402

from june.console.hub import ConsoleHub  # noqa: E402
from june.console.server import create_app  # noqa: E402


class _Event:
    def __init__(
        self,
        *,
        type: str,
        run_id: str,
        payload: dict[str, Any],
        ts: datetime | None = None,
    ) -> None:
        self.type = type
        self.run_id = run_id
        self.payload = payload
        self.ts = ts or datetime.now(timezone.utc)
        self.agent_id = "june"


def sample_structure_checkpoint() -> dict[str, Any]:
    """Minimal layered graph (no MechaHarness) for UI smoke."""
    return {
        "id": "ui-demo",
        "goal": "ui regression graph",
        "nodes": {
            "cron": {
                "id": "cron",
                "kind": "june.cron",
                "goal": "cron root",
                "status": "running",
                "payload": {},
            },
            "minute": {
                "id": "minute",
                "kind": "june.bucket",
                "goal": "minute",
                "status": "pending",
                "payload": {},
            },
            "hourly": {
                "id": "hourly",
                "kind": "june.bucket",
                "goal": "hourly",
                "status": "occupied",
                "payload": {},
            },
            "chat": {
                "id": "chat",
                "kind": "conversational_tool_loop",
                "goal": "chat",
                "status": "pending",
                "payload": {},
            },
        },
        "edges": [
            {
                "from_node": "cron",
                "to_node": "minute",
                "types": ["control"],
                "reason": "schedule",
            },
            {
                "from_node": "cron",
                "to_node": "hourly",
                "types": ["control"],
                "reason": "schedule",
            },
            {
                "from_node": "cron",
                "to_node": "chat",
                "types": ["control"],
                "reason": "channel",
            },
        ],
    }


def sample_instance_pipeline(run_id: str) -> dict[str, Any]:
    steps = ("acquire window", "sample signals", "emit heartbeat")
    nodes: dict[str, Any] = {}
    edges: list[dict[str, Any]] = []
    prev = None
    for idx, goal in enumerate(steps):
        nid = f"{run_id}:step:{idx}"
        nodes[nid] = {
            "id": nid,
            "kind": "june.timed_log",
            "goal": goal,
            "status": "succeeded" if idx < 2 else "running",
            "payload": {"message": goal, "step_index": idx},
        }
        if prev is not None:
            edges.append(
                {
                    "from_node": prev,
                    "to_node": nid,
                    "types": ["control"],
                    "reason": "seq",
                }
            )
        prev = nid
    return {"id": run_id, "goal": "timed pipeline", "nodes": nodes, "edges": edges}


def seed_hub(hub: ConsoleHub) -> None:
    hub.set_structure_checkpoint(sample_structure_checkpoint())
    hub.begin_run("ui-demo")
    now = datetime.now(timezone.utc)
    for _i in range(6):
        hub.ingest_event(
            _Event(
                type="core:graph_node_start",
                run_id="ui-demo",
                payload={"node_id": "minute", "kind": "june.bucket"},
                ts=now,
            )
        )
    run_id = "june.console.cron:minute:uiwatch01"
    hub.begin_instance(
        run_id=run_id,
        bucket="minute",
        parent_node_id="minute",
        pipeline=sample_instance_pipeline(run_id),
    )
    hub.set_instance_progress(run_id, active_node_id=f"{run_id}:step:2", status="running")
    hub.set_orchestrator_status({"state": "running", "goals": 1})


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def console_hub() -> ConsoleHub:
    hub = ConsoleHub()
    seed_hub(hub)
    return hub


@pytest.fixture
def console_base_url(console_hub: ConsoleHub) -> Iterator[str]:
    import uvicorn

    port = _free_port()
    app = create_app(console_hub)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="june-ui-uvicorn", daemon=True)
    thread.start()
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:
        server.should_exit = True
        raise RuntimeError("uvicorn failed to start for UI tests")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5.0)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright_api:
        try:
            browser = playwright_api.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - env without browsers
            pytest.skip(f"Playwright Chromium unavailable: {exc}")
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser, console_base_url: str) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.goto(console_base_url, wait_until="domcontentloaded")
    page.wait_for_selector("#june-console")
    # Snapshot/WS paint can lag a tick after first connect.
    page.wait_for_function(
        """() => {
          const nodes = document.querySelectorAll('#canvas .graph-node');
          return nodes.length > 0;
        }""",
        timeout=10_000,
    )
    yield page
    context.close()
