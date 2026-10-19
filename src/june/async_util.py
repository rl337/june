"""Sync entry helpers for host_kit recipes that may nest under a running loop."""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Callable, Coroutine
from contextvars import copy_context
from typing import Any, TypeVar

T = TypeVar("T")


def run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion even when already inside an event loop.

    ``asyncio.run`` raises if a loop is running (FastAPI TestClient, nested
    recipe tools). Fall back to a worker thread with its own loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def run_sync_in_thread(fn: Callable[[], T]) -> T:
    """Run blocking ``fn`` off the event loop, preserving ContextVars.

    Console chat must not call host_kit / Comfy on the uvicorn thread: that
    freezes ``/api/snapshot`` and WebSocket pushes for the whole hang.
    """
    ctx = copy_context()
    return await asyncio.to_thread(ctx.run, fn)
