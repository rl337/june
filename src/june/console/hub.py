"""In-process execution state for the web console."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from june.console.event_format import serialize_event, serialize_journal_entry
from june.console.event_rate import build_event_rate
from june.console.scene import ROOT_SCENE_ID, SceneFrame, build_scene_frame
from june.console.world import build_instance_world, build_world_graph

_EVENT_LOG_LIMIT = 800


@dataclass
class ConsoleSnapshot:
    """Serializable console state pushed to browsers."""

    updated_at: str
    run_id: str | None
    status: str
    selected_node_id: str | None
    scene: dict[str, Any]
    world: dict[str, Any] = field(default_factory=dict)
    event_log: list[dict[str, Any]] = field(default_factory=list)
    event_rate: dict[str, Any] = field(default_factory=dict)
    instances: list[dict[str, Any]] = field(default_factory=list)
    orchestrator: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "run_id": self.run_id,
            "status": self.status,
            "selected_node_id": self.selected_node_id,
            "scene": self.scene,
            "world": self.world,
            "event_log": self.event_log,
            "event_rate": self.event_rate,
            "instances": self.instances,
            "orchestrator": self.orchestrator,
        }


class ConsoleHub:
    """Thread-safe store of the latest graph scene and event stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[Any] = []
        self._journal: list[dict[str, Any]] = []
        self._structure_checkpoint: dict[str, Any] = {}
        self._checkpoint: dict[str, Any] = {}
        self._run_id: str | None = None
        self._run_status: str = "idle"
        self._selected_node_id: str | None = ROOT_SCENE_ID
        self._orchestrator_status: dict[str, Any] = {}
        self._instances: dict[str, dict[str, Any]] = {}
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

    def set_structure_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        with self._lock:
            self._structure_checkpoint = dict(checkpoint)
            self._checkpoint = dict(checkpoint)
            self._run_id = str(checkpoint.get("id") or self._run_id)
            self._run_status = "scheduled"
            # Keep the console on the full graph overview by default.
            self._selected_node_id = ROOT_SCENE_ID
            self._publish()

    def begin_run(self, run_id: str, *, reset_journal: bool = False) -> None:
        with self._lock:
            self._run_id = run_id
            self._run_status = "running"
            if reset_journal:
                self._events = []
                self._journal = []
            self._publish()

    def ingest_journal(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._journal.append(dict(entry))
            if len(self._journal) > _EVENT_LOG_LIMIT:
                self._journal = self._journal[-_EVENT_LOG_LIMIT:]
            self._publish()

    def ingest_event(self, event: Any) -> None:
        with self._lock:
            self._events.append(event)
            if len(self._events) > _EVENT_LOG_LIMIT:
                self._events = self._events[-_EVENT_LOG_LIMIT:]
            # Instance pipeline checkpoints are tracked via touch_instance /
            # complete_instance so overlapping runs do not clobber the master graph.
            if not self._structure_checkpoint:
                payload = getattr(event, "payload", None)
                if isinstance(payload, dict):
                    graph = payload.get("graph")
                    if isinstance(graph, dict):
                        self._checkpoint = graph
            self._publish()

    def merge_execution_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Merge a child subgraph checkpoint back into the structure graph."""
        with self._lock:
            if self._structure_checkpoint:
                self._checkpoint = dict(self._structure_checkpoint)
            if checkpoint:
                merged = _deep_merge_graph(self._checkpoint, checkpoint)
                self._checkpoint = merged
            self._publish()

    def begin_instance(
        self,
        *,
        run_id: str,
        bucket: str,
        parent_node_id: str,
        pipeline: dict[str, Any],
    ) -> None:
        with self._lock:
            self._instances[run_id] = {
                "run_id": run_id,
                "bucket": bucket,
                "parent_node_id": parent_node_id,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "pipeline": pipeline,
                "active_node_id": None,
            }
            self._publish()

    def touch_instance(self, run_id: str, *, event: Any | None = None) -> None:
        with self._lock:
            inst = self._instances.get(run_id)
            if inst is None:
                return
            if event is not None:
                payload = getattr(event, "payload", None)
                etype = str(getattr(event, "type", ""))
                if isinstance(payload, dict):
                    if etype.endswith("graph_node_start") and isinstance(payload.get("node_id"), str):
                        inst["active_node_id"] = payload["node_id"]
                    graph = payload.get("graph")
                    if isinstance(graph, dict):
                        inst["pipeline"] = graph
            self._publish()

    def complete_instance(
        self,
        *,
        run_id: str,
        status: str,
        pipeline: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            inst = self._instances.get(run_id)
            if inst is None:
                return
            inst["status"] = status
            inst["finished_at"] = datetime.now(timezone.utc).isoformat()
            if pipeline is not None:
                inst["pipeline"] = pipeline
            # Keep a short trail of finished instances, drop older ones.
            finished = [
                i
                for i in self._instances.values()
                if i.get("status") not in {"running", "pending"}
            ]
            finished.sort(key=lambda i: str(i.get("finished_at", "")))
            # Keep finished trail short; UI stacks only the latest two visible.
            while len(finished) > 6:
                old = finished.pop(0)
                self._instances.pop(str(old.get("run_id")), None)
            self._publish()

    def bucket_has_active_instances(self, bucket: str) -> bool:
        with self._lock:
            return any(
                i.get("bucket") == bucket and i.get("status") == "running"
                for i in self._instances.values()
            )

    def mark_bucket_running(self, node_id: str) -> None:
        self._set_node_status(node_id, "running")

    def mark_bucket_succeeded(self, node_id: str) -> None:
        self._set_node_status(node_id, "succeeded")

    def mark_bucket_failed(self, node_id: str, *, error: str) -> None:
        self._set_node_status(node_id, "failed", error=error)

    def _set_node_status(self, node_id: str, status: str, *, error: str | None = None) -> None:
        with self._lock:
            nodes = self._checkpoint.get("nodes")
            if isinstance(nodes, dict) and node_id in nodes:
                raw = nodes[node_id]
                if isinstance(raw, dict):
                    raw["status"] = status
                    if error:
                        raw["error"] = error
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

    def instance_world(self, run_id: str) -> dict[str, Any] | None:
        """Return a zoomable world graph for one stacked instance, or None."""
        with self._lock:
            inst = self._instances.get(run_id)
            if not isinstance(inst, dict):
                return None
            return build_instance_world(dict(inst)).to_dict()

    def instance_node_detail(self, run_id: str, node_id: str) -> dict[str, Any] | None:
        """Return raw node (or instance summary) for a watch-dialog selection."""
        with self._lock:
            inst = self._instances.get(run_id)
            if not isinstance(inst, dict):
                return None
            # Selecting the instance root shows the run summary + pipeline meta.
            if node_id in ("", "root", run_id):
                pipeline = inst.get("pipeline") if isinstance(inst.get("pipeline"), dict) else {}
                return {
                    "run_id": run_id,
                    "node_id": run_id,
                    "kind": "instance",
                    "status": inst.get("status"),
                    "bucket": inst.get("bucket"),
                    "parent_node_id": inst.get("parent_node_id"),
                    "started_at": inst.get("started_at"),
                    "finished_at": inst.get("finished_at"),
                    "active_node_id": inst.get("active_node_id"),
                    "pipeline_goal": pipeline.get("goal"),
                    "pipeline_id": pipeline.get("id"),
                    "node_count": len(pipeline.get("nodes") or {}),
                }
            raw = _find_pipeline_node(inst.get("pipeline"), node_id)
            if raw is None:
                return None
            return {
                "run_id": run_id,
                "node_id": node_id,
                "node": dict(raw),
            }

    def _event_log_entries(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for event in self._events:
            rows.append(serialize_event(event))
        for entry in self._journal:
            rows.append(serialize_journal_entry(entry))
        rows.sort(key=lambda r: r.get("ts", ""))
        if len(rows) > _EVENT_LOG_LIMIT:
            rows = rows[-_EVENT_LOG_LIMIT:]
        return rows

    def _build_snapshot(self) -> ConsoleSnapshot:
        run_id = self._run_id or str(self._checkpoint.get("id") or "pending")
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
        instances = [dict(v) for v in self._instances.values()]
        # Compact payloads for the client (omit full pipelines in the list).
        instance_summaries = [
            {
                "run_id": i.get("run_id"),
                "bucket": i.get("bucket"),
                "parent_node_id": i.get("parent_node_id"),
                "status": i.get("status"),
                "started_at": i.get("started_at"),
                "finished_at": i.get("finished_at"),
                "active_node_id": i.get("active_node_id"),
            }
            for i in instances
        ]
        world = (
            build_world_graph(
                self._checkpoint,
                self._events,
                run_id=run_id,
                instances=instances,
            ).to_dict()
            if self._checkpoint
            else {
                "root_id": run_id,
                "goal": "waiting for execution",
                "width": 400,
                "height": 240,
                "nodes": [],
                "edges": [],
                "active_node_id": None,
            }
        )
        event_log = self._event_log_entries()
        return ConsoleSnapshot(
            updated_at=datetime.now(timezone.utc).isoformat(),
            run_id=self._run_id,
            status=self._run_status,
            selected_node_id=self._selected_node_id,
            scene=scene.to_dict(),
            world=world,
            event_log=event_log,
            event_rate=build_event_rate(event_log),
            instances=instance_summaries,
            orchestrator=dict(self._orchestrator_status),
        )

    def _publish(self) -> None:
        snap = self._build_snapshot()
        for listener in list(self._listeners):
            listener(snap)

    def snapshot_json(self) -> str:
        return json.dumps(self.snapshot().to_dict())


def _find_pipeline_node(pipeline: Any, node_id: str) -> dict[str, Any] | None:
    """Locate a node by id in a pipeline checkpoint (recursive into subgraphs)."""
    if not isinstance(pipeline, dict) or not node_id:
        return None
    nodes = pipeline.get("nodes")
    if isinstance(nodes, dict):
        raw = nodes.get(node_id)
        if isinstance(raw, dict):
            return raw
        for child in nodes.values():
            if not isinstance(child, dict):
                continue
            nested = child.get("subgraph")
            if isinstance(nested, dict):
                found = _find_pipeline_node(nested, node_id)
                if found is not None:
                    return found
            payload = child.get("payload")
            if isinstance(payload, dict):
                nested = payload.get("subgraph")
                if isinstance(nested, dict):
                    found = _find_pipeline_node(nested, node_id)
                    if found is not None:
                        return found
    return None


def _deep_merge_graph(base: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Update node statuses in base from a child subgraph checkpoint."""
    merged = dict(base)
    base_nodes = merged.get("nodes")
    child_nodes = child.get("nodes")
    if not isinstance(base_nodes, dict) or not isinstance(child_nodes, dict):
        return merged
    for node_id, child_raw in child_nodes.items():
        if not isinstance(child_raw, dict):
            continue
        for parent_raw in base_nodes.values():
            if not isinstance(parent_raw, dict):
                continue
            sub = parent_raw.get("subgraph")
            if not isinstance(sub, dict):
                continue
            sub_nodes = sub.get("nodes")
            if isinstance(sub_nodes, dict) and node_id in sub_nodes:
                sub_nodes[node_id] = {**sub_nodes[node_id], **child_raw}
    return merged
