"""Drive 10s / 60s bucket subgraph runs for the console cron graph."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from june.budget import SubgraphBudget
from june.console.hub import ConsoleHub
from june.harness import BoundRun, MechaHarnessClient
from june.harness.cron_graph import (
    CONSOLE_CRON_RUN_ID,
    build_console_cron_graph,
    clone_pipeline_for_instance,
    new_bucket_run_id,
)


class ConsoleCronScheduler:
    """Periodically executes bucket subgraphs and streams events to the hub.

    The 10s bucket pipeline takes longer than 10s, so ticks are launched on
    daemon threads and may overlap.
    """

    def __init__(
        self,
        hub: ConsoleHub,
        client: MechaHarnessClient,
        *,
        on_event: Callable[[Any], None] | None = None,
    ) -> None:
        self.hub = hub
        self.client = client
        self._on_event = on_event
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._workers: list[threading.Thread] = []
        self._master = build_console_cron_graph(CONSOLE_CRON_RUN_ID)
        self._last_10s = 0.0
        self._last_60s = 0.0
        self.hub.set_structure_checkpoint(self._master.checkpoint())

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="june-console-cron", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        for worker in list(self._workers):
            worker.join(timeout=0.1)
        self._workers.clear()

    def _loop(self) -> None:
        self._spawn_bucket("10s", f"{CONSOLE_CRON_RUN_ID}:bucket:10s", blocking=False)
        self._spawn_bucket("60s", f"{CONSOLE_CRON_RUN_ID}:bucket:60s", blocking=True)
        self._last_10s = time.monotonic()
        self._last_60s = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            if now - self._last_10s >= 10.0:
                self._last_10s = now
                self._spawn_bucket("10s", f"{CONSOLE_CRON_RUN_ID}:bucket:10s", blocking=False)
            if now - self._last_60s >= 60.0:
                self._last_60s = now
                self._spawn_bucket("60s", f"{CONSOLE_CRON_RUN_ID}:bucket:60s", blocking=False)
            self._reap_workers()
            if self._stop.wait(timeout=0.25):
                break

    def _reap_workers(self) -> None:
        self._workers = [t for t in self._workers if t.is_alive()]

    def _spawn_bucket(self, bucket_key: str, node_id: str, *, blocking: bool) -> None:
        if blocking:
            self._run_bucket(bucket_key, node_id)
            return
        worker = threading.Thread(
            target=self._run_bucket,
            args=(bucket_key, node_id),
            name=f"june-bucket-{bucket_key}",
            daemon=True,
        )
        self._workers.append(worker)
        worker.start()

    def _run_bucket(self, bucket_key: str, node_id: str) -> None:
        if not self.client.connect() or self._stop.is_set():
            return
        node = self._master.nodes.get(node_id)
        if node is None or not node.subgraph:
            return

        from mechaharness.graph import ExecutionGraph

        run_id = new_bucket_run_id(bucket_key)
        pipeline = clone_pipeline_for_instance(node.subgraph, run_id)
        child = ExecutionGraph.resume(pipeline)
        bound = BoundRun(
            template_name="console.cron.bucket",
            bindings={"bucket": bucket_key, "instance_id": run_id},
            node_kinds=["june.timed_log", "june.event_log"],
            budget=SubgraphBudget(soft_limit=64.0, hard_limit=128.0),
            run_id=run_id,
        )
        self.hub.begin_instance(
            run_id=run_id,
            bucket=bucket_key,
            parent_node_id=node_id,
            pipeline=pipeline,
        )
        self.hub.mark_bucket_running(node_id)
        self.hub.ingest_journal(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "june.console.log",
                "run_id": run_id,
                "message": f"bucket {bucket_key} instance started",
                "summary": f"▶ {bucket_key} {run_id[-8:]}",
                "bucket": bucket_key,
                "instance_id": run_id,
            }
        )

        from june.harness.execution import run_graph

        def forward(event: Any) -> None:
            self.hub.ingest_event(event)
            self.hub.touch_instance(run_id, event=event)
            if self._on_event is not None:
                self._on_event(event)

        try:
            result = run_graph(
                child,
                bound,
                on_event=forward,
                on_console_log=self.hub.ingest_journal,
            )
            self.hub.complete_instance(
                run_id=run_id,
                status=result.status,
                pipeline=result.graph.checkpoint(),
            )
            # Bucket node stays "running" while any instance is active.
            if not self.hub.bucket_has_active_instances(bucket_key):
                self.hub.mark_bucket_succeeded(node_id)
            self.hub.ingest_journal(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "june.console.log",
                    "run_id": run_id,
                    "message": f"bucket {bucket_key} instance finished ({result.status})",
                    "summary": f"■ {bucket_key} {run_id[-8:]} {result.status}",
                    "bucket": bucket_key,
                    "instance_id": run_id,
                    "status": result.status,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.hub.complete_instance(run_id=run_id, status="failed", pipeline=pipeline)
            if not self.hub.bucket_has_active_instances(bucket_key):
                self.hub.mark_bucket_failed(node_id, error=str(exc))
            self.hub.ingest_journal(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "june.console.log",
                    "run_id": run_id,
                    "message": str(exc),
                    "summary": f"✕ {bucket_key} {run_id[-8:]} failed",
                    "bucket": bucket_key,
                    "instance_id": run_id,
                    "status": "failed",
                }
            )
