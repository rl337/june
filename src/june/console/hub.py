"""In-process execution state for the web console."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from june.console.scene import ROOT_SCENE_ID, SceneFrame, build_scene_frame


@dataclass
class ConsoleSnapshot:
    """Serializable console state pushed to browsers."""

    updated_at: str
    run_id: str | None
    status: str
    selected_node_id: str | None
    scene: dict[str, Any]
    orchestrator: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "run_id": self.run_id,
            "status": self.status,
            "selected_node_id": self.selected_node_id,
            "scene": self.scene,
            "orchestrator": self.orchestrator,
        }


class ConsoleHub:
    """Thread-safe store of the latest graph scene and event stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[Any] = []
        self._checkpoint: dict[str, Any] = {}
        self._run_id: str | None = None
        self._run_status: str = "idle"
        self._selected_node_id: str | None = ROOT_SCENE_ID
        self._orchestrator_status: dict[str, Any] = {}
        self._listeners: list[Callable[[ConsoleSnapshot], None]] = []

    def subscribe(self, listener: Callable[[ConsoleSnapshot], None]) -> None:
        self._listeners.append(listener)

    def set_orchestrator_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            self._orchestrator_status = dict(status)
            self._publish()

    def select_node(self, node_id: str) -> None:
        with self._lock:
            self._selected_node_id = node_id or ROOT_SCENE_ID
            self._publish()

    def begin_run(self, run_id: str) -> None:
        with self._lock:
            self._run_id = run_id
            self._run_status = "running"
            self._events = []
            self._checkpoint = {}
            self._publish()

    def ingest_event(self, event: Any) -> None:
        with self._lock:
            self._events.append(event)
            payload = getattr(event, "payload", None)
            if isinstance(payload, dict):
                graph = payload.get("graph")
                if isinstance(graph, dict) and self._run_id is not None:
                    self._checkpoint = graph
            self._publish()

    def complete_run(
        self,
        *,
        run_id: str,
        status: str,
        checkpoint: dict[str, Any],
    ) -> None:
        with self._lock:
            self._run_id = run_id
            self._run_status = status
            if checkpoint:
                self._checkpoint = checkpoint
            self._publish()

    def snapshot(self) -> ConsoleSnapshot:
        with self._lock:
            return self._build_snapshot()

    def _build_snapshot(self) -> ConsoleSnapshot:
        run_id = self._run_id or "pending"
        scene: SceneFrame
        if self._checkpoint:
            scene = build_scene_frame(
                self._checkpoint,
                self._events,
                run_id=run_id,
                selected_node_id=self._selected_node_id,
            )
        else:
            scene = SceneFrame(
                run_id=run_id,
                scene_node_id=ROOT_SCENE_ID,
                scene_title="waiting for execution",
                scene_kind="idle",
                active_node_id=None,
            )
        return ConsoleSnapshot(
            updated_at=datetime.now(timezone.utc).isoformat(),
            run_id=self._run_id,
            status=self._run_status,
            selected_node_id=self._selected_node_id,
            scene=scene.to_dict(),
            orchestrator=dict(self._orchestrator_status),
        )

    def _publish(self) -> None:
        snap = self._build_snapshot()
        for listener in list(self._listeners):
            listener(snap)

    def snapshot_json(self) -> str:
        return json.dumps(self.snapshot().to_dict())
