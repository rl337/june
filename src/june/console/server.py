"""HTTP + WebSocket console for live graph execution."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from importlib import resources
from pathlib import Path
from typing import Any

from june.console.hub import ConsoleHub, ConsoleSnapshot

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover - optional extra
    FastAPI = None  # type: ignore[misc, assignment]
    WebSocket = None  # type: ignore[misc, assignment]
    WebSocketDisconnect = Exception  # type: ignore[misc, assignment]
    FileResponse = None  # type: ignore[misc, assignment]
    JSONResponse = None  # type: ignore[misc, assignment]
    StaticFiles = None  # type: ignore[misc, assignment]


def create_app(hub: ConsoleHub) -> Any:
    if FastAPI is None or WebSocket is None:
        raise RuntimeError(
            "Web console requires the console extra: pip install 'june[console]'"
        )

    app = FastAPI(title="June Console", version="0.1.0")
    static_root = _static_directory()
    if static_root.is_dir() and StaticFiles is not None:
        app.mount("/static", StaticFiles(directory=str(static_root)), name="static")

    @app.get("/")
    async def index() -> Any:
        return FileResponse(static_root / "index.html")

    @app.get("/api/snapshot")
    async def api_snapshot() -> Any:
        return JSONResponse(hub.snapshot().to_dict())

    @app.get("/api/status")
    async def api_status() -> Any:
        snap = hub.snapshot()
        return JSONResponse(
            {
                "status": snap.status,
                "run_id": snap.run_id,
                "orchestrator": snap.orchestrator,
            }
        )

    @app.post("/api/scene")
    async def api_select_scene(body: dict[str, Any]) -> Any:
        from june.console.scene import ROOT_SCENE_ID

        node_id = body.get("node_id")
        if node_id in (None, "", "root", ROOT_SCENE_ID):
            hub.select_node(ROOT_SCENE_ID)
        else:
            hub.select_node(str(node_id))
        return JSONResponse(hub.snapshot().to_dict())

    @app.get("/api/instance/{run_id}/world")
    async def api_instance_world(run_id: str) -> Any:
        world = hub.instance_world(run_id)
        if world is None:
            return JSONResponse({"error": "instance not found", "run_id": run_id}, status_code=404)
        return JSONResponse({"run_id": run_id, "world": world})

    @app.get("/api/instance/{run_id}/node/{node_id:path}")
    async def api_instance_node(run_id: str, node_id: str) -> Any:
        detail = hub.instance_node_detail(run_id, node_id)
        if detail is None:
            return JSONResponse(
                {"error": "node not found", "run_id": run_id, "node_id": node_id},
                status_code=404,
            )
        return JSONResponse(detail)

    @app.websocket("/ws")
    async def ws_console(websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[ConsoleSnapshot] = asyncio.Queue(maxsize=32)

        def push(snap: ConsoleSnapshot) -> None:
            try:
                queue.put_nowait(snap)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(snap)
                except asyncio.QueueFull:
                    pass

        hub.subscribe(push)
        try:
            await websocket.send_json(hub.snapshot().to_dict())
            while True:
                snap = await queue.get()
                await websocket.send_json(snap.to_dict())
        except WebSocketDisconnect:
            return

    return app


def _static_directory() -> Path:
    try:
        ref = resources.files("june.console") / "static"
        with resources.as_file(ref) as path:
            return Path(path)
    except (ModuleNotFoundError, FileNotFoundError):
        return Path(__file__).resolve().parent / "static"


async def serve_console(
    hub: ConsoleHub,
    *,
    host: str = "0.0.0.0",
    port: int = 8080,
) -> None:
    import uvicorn

    app = create_app(hub)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def snapshot_stream(hub: ConsoleHub) -> AsyncIterator[ConsoleSnapshot]:
    """Async iterator over hub updates (for tests)."""
    queue: asyncio.Queue[ConsoleSnapshot] = asyncio.Queue()

    def push(snap: ConsoleSnapshot) -> None:
        queue.put_nowait(snap)

    hub.subscribe(push)
    yield hub.snapshot()
    while True:
        yield await queue.get()
