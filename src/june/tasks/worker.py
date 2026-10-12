"""Background worker for MechaHarness remote-task dispatch (off the control tick)."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable


class BackgroundGraphWorker:
    """Small thread pool so control-tick handlers never block on graph/backend I/O."""

    def __init__(self, *, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="june-remote")
        self._lock = threading.Lock()
        self._inflight: dict[str, Future[Any]] = {}

    def submit(self, key: str, fn: Callable[[], Any]) -> bool:
        """Submit work if ``key`` is not already running. Returns False if skipped."""
        with self._lock:
            existing = self._inflight.get(key)
            if existing is not None and not existing.done():
                return False

            def _wrap() -> Any:
                try:
                    return fn()
                finally:
                    with self._lock:
                        self._inflight.pop(key, None)

            self._inflight[key] = self._pool.submit(_wrap)
            return True

    def wait(self, key: str, *, timeout: float | None = None) -> Any:
        with self._lock:
            fut = self._inflight.get(key)
        if fut is None:
            return None
        return fut.result(timeout=timeout)

    def shutdown(self, *, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=True)
