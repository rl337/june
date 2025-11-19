"""
Helper utilities for instrumenting gRPC calls with metrics.
"""
import time
from contextlib import asynccontextmanager
from typing import Optional, AsyncIterator, Any
import grpc

from essence.services.shared_metrics import (
    GRPC_REQUESTS_TOTAL,
    GRPC_REQUEST_DURATION_SECONDS,
)


@asynccontextmanager
async def instrument_grpc_call(
    service: str, method: str, *args, **kwargs
) -> AsyncIterator[Any]:
    """
    Context manager to instrument a gRPC call with metrics.

    Args:
        service: Service name (e.g., "stt", "tts", "llm")
        method: Method name (e.g., "recognize_stream", "synthesize", "chat_stream")
        *args, **kwargs: Passed to the actual gRPC call

    Usage:
        async with instrument_grpc_call("stt", "recognize_stream") as call:
            result = await stt_client.recognize_stream(...)
            return result
    """
    start_time = time.time()
    status_code = "ok"  # Default to success

    try:
        # Yield control to the caller to make the actual gRPC call
        # The caller should perform the gRPC operation and return the result
        yield
        status_code = "ok"
    except grpc.RpcError as e:
        # Map gRPC error codes to status strings
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            status_code = "timeout"
        elif e.code() == grpc.StatusCode.UNAVAILABLE:
            status_code = "unavailable"
        elif e.code() == grpc.StatusCode.INTERNAL:
            status_code = "internal_error"
        elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            status_code = "invalid_argument"
        else:
            status_code = f"error_{e.code().name.lower()}"
        raise
    except Exception as e:
        status_code = "unknown_error"
        raise
    finally:
        # Record metrics
        duration = time.time() - start_time
        GRPC_REQUESTS_TOTAL.labels(
            service=service, method=method, status_code=status_code
        ).inc()
        GRPC_REQUEST_DURATION_SECONDS.labels(
            service=service, method=method, status_code=status_code
        ).observe(duration)


def record_grpc_call(
    service: str, method: str, duration: float, status_code: str = "ok"
) -> None:
    """
    Record a gRPC call metric manually.

    Use this when you need to instrument a gRPC call that doesn't fit
    the context manager pattern.

    Args:
        service: Service name (e.g., "stt", "tts", "llm")
        method: Method name (e.g., "recognize_stream", "synthesize", "chat_stream")
        duration: Call duration in seconds
        status_code: Status code string (e.g., "ok", "timeout", "unavailable")
    """
    GRPC_REQUESTS_TOTAL.labels(
        service=service, method=method, status_code=status_code
    ).inc()
    GRPC_REQUEST_DURATION_SECONDS.labels(
        service=service, method=method, status_code=status_code
    ).observe(duration)
