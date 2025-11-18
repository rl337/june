"""
Shared HTTP middleware utilities for FastAPI services.

Provides common middleware for tracing and metrics that can be used
across all services (telegram, discord, etc.).
"""
import logging
import time
from typing import Callable, Optional

from fastapi import Request
from opentelemetry import trace

from essence.services.shared_metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
)

logger = logging.getLogger(__name__)


def create_tracing_and_metrics_middleware(
    tracer: Optional[object] = None,
    trace_module: Optional[object] = None
) -> Callable:
    """
    Create a FastAPI middleware function for tracing and metrics.
    
    This middleware:
    - Adds OpenTelemetry tracing spans for HTTP requests
    - Records Prometheus metrics (request count, duration)
    - Handles errors and records them in traces
    
    Args:
        tracer: OpenTelemetry tracer instance (from get_tracer())
        trace_module: OpenTelemetry trace module (for Status, get_current_span)
    
    Returns:
        FastAPI middleware function that can be used with @app.middleware("http")
    
    Example:
        from essence.chat.utils.tracing import get_tracer
        from opentelemetry import trace
        
        tracer = get_tracer(__name__)
        middleware = create_tracing_and_metrics_middleware(tracer, trace)
        
        @app.middleware("http")
        async def tracing_and_metrics_middleware(request: Request, call_next):
            return await middleware(request, call_next)
    """
    async def tracing_and_metrics_middleware(request: Request, call_next):
        """Add tracing spans and metrics to HTTP requests."""
        # Start timing for metrics
        start_time = time.time()
        
        # Extract endpoint path (normalize to remove query params and trailing slashes)
        endpoint = request.url.path.rstrip('/') or '/'
        method = request.method.upper()
        
        status_code = 500  # Default to error if exception occurs
        try:
            # Setup tracing span if available
            if tracer is not None:
                span_name = f"http.{method.lower()} {endpoint}"
                with tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("http.method", method)
                    span.set_attribute("http.url", str(request.url))
                    span.set_attribute("http.path", endpoint)
                    span.set_attribute("http.query_string", str(request.url.query) if request.url.query else "")
                    span.set_attribute("http.scheme", request.url.scheme)
                    
                    response = await call_next(request)
                    status_code = response.status_code
                    
                    span.set_attribute("http.status_code", status_code)
                    span.set_attribute("http.status_text", status_code)
                    
                    # Mark as error for 4xx and 5xx status codes
                    if status_code >= 400 and trace_module is not None:
                        span.set_status(trace_module.Status(trace_module.StatusCode.ERROR, f"HTTP {status_code}"))
                    
                    return response
            else:
                # No tracing, just call next
                response = await call_next(request)
                status_code = response.status_code
                return response
        except Exception as e:
            status_code = 500
            # Record exception in tracing if available
            if tracer is not None and trace_module is not None:
                try:
                    current_span = trace_module.get_current_span()
                    if current_span:
                        current_span.record_exception(e)
                        current_span.set_status(trace_module.Status(trace_module.StatusCode.ERROR, str(e)))
                except Exception:
                    pass  # Ignore tracing errors
            raise
        finally:
            # Record metrics
            duration = time.time() - start_time
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint, status_code=status_code).observe(duration)
    
    return tracing_and_metrics_middleware
