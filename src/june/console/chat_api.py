"""Chat HTTP routes mounted on the June web console."""

from __future__ import annotations

import base64
import mimetypes
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from june.async_util import run_sync_in_thread
from june.channels import ChannelMessage, ChatService, PartKind
from june.channels.adapters import RestChatAdapter, WebappAdapter
from june.config import JuneSettings
from june.documents import DocumentRef
from june.orchestrator import Orchestrator
from june.providers.junespark import JunesparkProvider

try:
    from fastapi import File, HTTPException, UploadFile
    from fastapi.responses import FileResponse, JSONResponse
except ImportError:  # pragma: no cover
    File = None  # type: ignore[misc, assignment]
    HTTPException = Exception  # type: ignore[misc, assignment]
    UploadFile = Any  # type: ignore[misc, assignment]
    FileResponse = None  # type: ignore[misc, assignment]
    JSONResponse = None  # type: ignore[misc, assignment]


def mount_chat_routes(
    app: Any,
    *,
    settings: JuneSettings,
    orchestrator: Orchestrator,
    provider: JunesparkProvider,
    chat_service: ChatService,
    hub: Any | None = None,
) -> None:
    """Attach /api/health, /api/models, /api/chat, upload routes to an existing app."""
    if JSONResponse is None:
        raise RuntimeError("Chat API requires the console extra: pip install 'june[console]'")

    @app.get("/api/health")
    async def api_health() -> Any:
        return JSONResponse(
            {
                "status": "ok",
                "junespark_configured": bool(settings.junespark.base_url),
                "base_url": settings.junespark.base_url,
                "model": settings.junespark.model,
                "console": settings.console.model_dump(),
                "templates": [t.name for t in orchestrator.templates.list()],
            }
        )

    @app.get("/api/models")
    async def api_models() -> Any:
        if not settings.junespark.base_url:
            return JSONResponse(
                {"error": "junespark.base_url not configured", "models": [], "active": None},
                status_code=503,
            )
        try:
            listed = provider.list_models()
            active = provider.select_model(settings.junespark.model)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"junespark models failed: {exc}") from exc
        return JSONResponse(
            {
                "models": [m.to_dict() for m in listed],
                "active": None if active is None else active.to_dict(),
            }
        )

    webapp = WebappAdapter()
    rest = RestChatAdapter()

    @app.post("/api/chat")
    async def api_chat(body: dict[str, Any]) -> Any:
        if not settings.junespark.base_url:
            raise HTTPException(status_code=503, detail="junespark.base_url not configured")
        try:
            message = webapp.to_message(body)
            # Host_kit + tools (Comfy) are blocking; keep the event loop free so
            # snapshot/WS observability keeps updating during long runs.
            reply = await run_sync_in_thread(
                lambda: _handle_chat_with_console(
                    hub, orchestrator, chat_service, message
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(webapp.from_reply(reply))

    @app.post("/v1/chat")
    async def api_v1_chat(body: dict[str, Any]) -> Any:
        """Channel-agnostic REST front (same DTO as console; no hub mirroring)."""
        if not settings.junespark.base_url:
            raise HTTPException(status_code=503, detail="junespark.base_url not configured")
        try:
            message = rest.to_message(body)
            reply = await run_sync_in_thread(lambda: chat_service.handle(message))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(rest.from_reply(reply))

    @app.post("/api/upload")
    async def api_upload(file: Annotated[UploadFile, File()]) -> Any:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty upload")
        max_bytes = settings.chat.max_part_bytes
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail=f"file exceeds {max_bytes} bytes")
        guessed = mimetypes.guess_type(file.filename or "")[0]
        media_type = file.content_type or guessed or "application/octet-stream"
        encoded = base64.b64encode(data).decode("ascii")
        data_url = f"data:{media_type};base64,{encoded}"
        ref = orchestrator.documents.put(
            DocumentRef(
                title=file.filename or f"upload-{uuid4()}",
                media_type=media_type,
                summary=f"uploaded via web console ({len(data)} bytes)",
                provenance={"source": "web_console_upload"},
            ),
            payload=data_url,
        )
        kind = PartKind.FILE
        if media_type.startswith("image/"):
            kind = PartKind.IMAGE
        elif media_type.startswith("audio/"):
            kind = PartKind.AUDIO
        elif media_type.startswith("video/"):
            kind = PartKind.VIDEO
        return JSONResponse(
            {
                "document_id": ref.id,
                "name": ref.title,
                "media_type": media_type,
                "kind": kind.value,
                "url": f"/api/documents/{ref.id}",
                "part": {
                    "kind": kind.value,
                    "document_id": ref.id,
                    "media_type": media_type,
                    "name": ref.title,
                    "url": data_url if kind is PartKind.IMAGE else f"/api/documents/{ref.id}",
                },
            }
        )

    @app.get("/api/documents/{doc_id}", response_model=None)
    async def api_document(doc_id: str) -> Any:
        loaded = orchestrator.documents.load(doc_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail="document not found")
        ref, payload = loaded
        if payload.startswith("data:") and FileResponse is not None:
            header, _, b64 = payload.partition(",")
            media = ref.media_type
            if ";base64" in header and ":" in header:
                media = header.split(":", 1)[1].split(";", 1)[0] or media
            raw = base64.b64decode(b64)
            root = (
                Path(orchestrator.store.root)
                if orchestrator.store is not None
                else Path(tempfile.gettempdir()) / "june-uploads"
            )
            tmp = root / "uploads"
            tmp.mkdir(parents=True, exist_ok=True)
            path = tmp / f"{doc_id}.bin"
            path.write_bytes(raw)
            return FileResponse(path, media_type=media, filename=ref.title)
        return JSONResponse(
            {"id": ref.id, "title": ref.title, "media_type": ref.media_type, "text": payload}
        )


def _handle_chat_with_console(
    hub: Any | None,
    orchestrator: Orchestrator,
    chat_service: ChatService,
    message: ChannelMessage,
) -> Any:
    """Run chat via ChatService; console observes live MH graph + events."""
    del orchestrator
    if hub is None:
        return chat_service.handle(message)

    from june.harness.cron_graph import CHAT_PARENT_NODE_ID, new_chat_run_id
    from june.recipes.chat.graph import build_chat_graph

    run_id = new_chat_run_id()
    # Instance pipeline is the real recipe graph (HF-07 expands tools.subgraph).
    pipeline = build_chat_graph(message, run_id=run_id).checkpoint()
    hub.begin_instance(
        run_id=run_id,
        bucket="chat",
        parent_node_id=CHAT_PARENT_NODE_ID,
        pipeline=pipeline,
    )
    hub.mark_bucket_running(CHAT_PARENT_NODE_ID)
    hub.ingest_journal(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "june.console.log",
            "run_id": run_id,
            "message": "chat turn started",
            "summary": f"▶ chat {run_id[-8:]}",
            "bucket": "chat",
            "instance_id": run_id,
        }
    )

    def on_event(event: Any) -> None:
        hub.ingest_event(event)
        hub.touch_instance(run_id, event=event)

    def on_phase(phase: str, _state: Any) -> None:
        hub.ingest_journal(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "june.console.log",
                "run_id": run_id,
                "message": f"chat phase {phase}",
                "summary": f"● chat:{phase}",
                "bucket": "chat",
                "instance_id": run_id,
                "phase": phase,
            }
        )
        node_id = phase if phase in {"refine", "context", "tools", "render"} else None
        if node_id:
            hub.set_instance_progress(run_id, active_node_id=node_id)

    try:
        result = chat_service.handle_detailed(
            message,
            on_phase=on_phase,
            on_event=on_event,
            run_id=run_id,
        )
        reply = result.reply
        reply.run_id = run_id
        if isinstance(result.graph, dict) and result.graph:
            final_pipeline = result.graph
        else:
            final_pipeline = pipeline
        status = "ok" if result.ok else "failed"
        hub.complete_instance(run_id=run_id, status=status, pipeline=final_pipeline)
        if status == "ok":
            hub.mark_bucket_succeeded(CHAT_PARENT_NODE_ID)
        else:
            hub.mark_bucket_failed(
                CHAT_PARENT_NODE_ID, error=result.error or "chat turn failed"
            )
        hub.ingest_journal(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "june.console.log",
                "run_id": run_id,
                "message": f"chat turn finished ({status})",
                "summary": f"{'■' if status == 'ok' else '✕'} chat {run_id[-8:]} {status}",
                "bucket": "chat",
                "instance_id": run_id,
                "status": status,
            }
        )
        return reply
    except Exception as exc:
        hub.complete_instance(run_id=run_id, status="failed", pipeline=pipeline)
        hub.mark_bucket_failed(CHAT_PARENT_NODE_ID, error="chat turn failed")
        hub.ingest_journal(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "june.console.log",
                "run_id": run_id,
                "message": str(exc),
                "summary": f"✕ chat {run_id[-8:]} failed",
                "bucket": "chat",
                "instance_id": run_id,
                "status": "failed",
            }
        )
        raise
