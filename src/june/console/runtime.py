"""Wire the orchestrator control loop to the console hub."""

from __future__ import annotations

import threading
from typing import Any

from june.console.cron_scheduler import ConsoleCronScheduler
from june.console.hub import ConsoleHub
from june.harness.visualization import GRAPH_NODE_EVENT
from june.orchestrator import Orchestrator


class ConsoleRuntime:
    """Runs June and streams MechaHarness graph events to the console hub."""

    def __init__(self, orchestrator: Orchestrator, hub: ConsoleHub) -> None:
        self.orchestrator = orchestrator
        self.hub = hub
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cron: ConsoleCronScheduler | None = None
        self._attach_client()

    def _attach_client(self) -> None:
        client = self.orchestrator.client

        def on_event(event: Any) -> None:
            self.hub.ingest_event(event)
            if str(getattr(event, "type", "")) == GRAPH_NODE_EVENT:
                return

        client._on_graph_event = on_event
        original_execute = client.execute

        def execute_with_hub(run: Any, **kwargs: Any) -> Any:
            driver = kwargs.get("driver", "plan")
            if driver == "run":
                self.hub.begin_run(run.run_id)
            result = original_execute(run, **kwargs)
            if driver == "run":
                self.hub.complete_run(
                    run_id=run.run_id,
                    status=result.status,
                    checkpoint=result.graph_checkpoint,
                )
            return result

        client.execute = execute_with_hub  # type: ignore[method-assign]

    def refresh_status(self) -> None:
        self.hub.set_orchestrator_status(self.orchestrator.status())

    def start_cron_graph(self) -> None:
        if not self.orchestrator.client.connect():
            return
        if self._cron is not None:
            return
        self._cron = ConsoleCronScheduler(self.hub, self.orchestrator.client)
        self._cron.start()

    def start_control_loop(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                self.refresh_status()
                self.orchestrator.run(max_steps=1, should_stop=self._stop.is_set)
                if self._stop.wait(timeout=0.05):
                    break

        self._thread = threading.Thread(target=loop, name="june-control", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._cron is not None:
            self._cron.stop()
            self._cron = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
