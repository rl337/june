"""
gRPC interceptor for rate limiting.
"""
import logging
from typing import Callable, Optional
import grpc

from .rate_limiter import RateLimiter, RateLimitConfig, RateLimitResult

logger = logging.getLogger(__name__)


class RateLimitInterceptor(grpc.aio.ServerInterceptor):
    """gRPC interceptor for rate limiting."""

    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        config: Optional[RateLimitConfig] = None,
    ):
        """
        Initialize rate limit interceptor.

        Args:
            rate_limiter: RateLimiter instance (creates new if None)
            config: RateLimitConfig (used if rate_limiter is None)
        """
        self.rate_limiter = rate_limiter or RateLimiter(config or RateLimitConfig())
        # Note: Redis connection will be established on first use

    def _extract_identifier_from_metadata(self, metadata: tuple) -> tuple[str, str]:
        """Extract identifier from gRPC metadata.

        Returns:
            Tuple of (identifier_value, identifier_type)
        """
        # Try to get user ID from metadata (set by auth interceptor)
        metadata_dict = dict(metadata) if metadata else {}
        user_id = metadata_dict.get("user_id") or metadata_dict.get("x-user-id")
        if user_id:
            return (user_id, "user")

        # Fallback to service name or default
        service_name = metadata_dict.get("service_name")
        if service_name:
            return (f"service:{service_name}", "ip")

        # Default fallback
        return ("unknown", "ip")

    async def intercept_service(
        self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails
    ) -> grpc.RpcMethodHandler:
        """
        Intercept gRPC service calls to check rate limits.

        Args:
            continuation: Continuation function
            handler_call_details: Handler call details with metadata

        Returns:
            RPC method handler

        Raises:
            grpc.RpcError: If rate limit is exceeded
        """
        # Extract metadata
        # In newer gRPC versions, metadata is accessed via invocation_metadata
        if hasattr(handler_call_details, "invocation_metadata"):
            metadata = handler_call_details.invocation_metadata or tuple()
        elif hasattr(handler_call_details, "metadata"):
            metadata = handler_call_details.metadata or tuple()
        else:
            metadata = tuple()

        # Extract identifier
        identifier_value, identifier_type = self._extract_identifier_from_metadata(
            metadata
        )

        # Connect to Redis if needed (lazy connection)
        if not self.rate_limiter._is_connected:
            await self.rate_limiter.connect()

        # Check rate limit
        result = await self.rate_limiter.check_rate_limit(
            identifier=identifier_value,
            identifier_type=identifier_type,
            endpoint=handler_call_details.method,
        )

        # If rate limited, raise error
        if not result.allowed:
            raise grpc.RpcError(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                f"Rate limit exceeded: {result.error_message}. Retry after {result.retry_after}s",
            )

        # Rate limit passed, continue
        return await continuation(handler_call_details)
