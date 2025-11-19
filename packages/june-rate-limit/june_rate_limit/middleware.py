"""
FastAPI middleware for rate limiting.
"""
import logging
from typing import Callable, Optional
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .rate_limiter import RateLimiter, RateLimitConfig, RateLimitResult

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(
        self,
        app,
        rate_limiter: Optional[RateLimiter] = None,
        config: Optional[RateLimitConfig] = None,
        identifier_extractor: Optional[Callable[[Request], str]] = None,
        skip_paths: Optional[list] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            rate_limiter: RateLimiter instance (creates new if None)
            config: RateLimitConfig (used if rate_limiter is None)
            identifier_extractor: Function to extract identifier from request
            skip_paths: List of paths to skip rate limiting (e.g., ['/health', '/metrics'])
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter(config or RateLimitConfig())
        self.identifier_extractor = (
            identifier_extractor or self._default_identifier_extractor
        )
        self.skip_paths = skip_paths or [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
        ]

    def _default_identifier_extractor(self, request: Request) -> str:
        """Extract identifier from request (user ID or IP address)."""
        # Try to get user ID from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"

        # Fallback to IP address
        client_ip = request.client.host if request.client else "unknown"
        # Handle forwarded IP from proxy
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        return f"ip:{client_ip}"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        # Skip rate limiting for certain paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        # Extract identifier
        identifier = self.identifier_extractor(request)
        identifier_type = "user" if identifier.startswith("user:") else "ip"
        identifier_value = (
            identifier.split(":", 1)[1] if ":" in identifier else identifier
        )

        # Check rate limit
        result = await self.rate_limiter.check_rate_limit(
            identifier=identifier_value,
            identifier_type=identifier_type,
            endpoint=request.url.path,
        )

        # Add rate limit headers to response
        response = await call_next(request)
        headers = result.to_headers()
        for key, value in headers.items():
            if value is not None:
                response.headers[key] = value

        # If rate limited, return 429
        if not result.allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": result.error_message,
                    "retry_after": result.retry_after,
                },
                headers=headers,
            )

        return response
