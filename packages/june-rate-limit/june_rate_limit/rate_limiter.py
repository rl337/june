"""
Redis-based rate limiter with sliding window algorithm.
"""
import asyncio
import logging
import os
import time
from typing import Dict, Optional, Tuple
from datetime import timedelta
import redis.asyncio as aioredis
from redis.exceptions import RedisError, ConnectionError
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# Prometheus metrics
RATE_LIMIT_CHECKS = Counter(
    "rate_limit_checks_total", "Total rate limit checks", ["identifier_type", "result"]
)
RATE_LIMIT_VIOLATIONS = Counter(
    "rate_limit_violations_total",
    "Total rate limit violations",
    ["identifier_type", "limit_type"],
)
RATE_LIMIT_WAIT_TIME = Histogram(
    "rate_limit_wait_time_seconds", "Time until rate limit resets", ["identifier_type"]
)
ACTIVE_RATE_LIMITS = Gauge(
    "rate_limit_active_limits",
    "Number of active rate limits",
    ["identifier_type", "limit_type"],
)


class RateLimitResult:
    """Result of a rate limit check."""

    def __init__(
        self,
        allowed: bool,
        limit: int,
        remaining: int,
        reset_time: float,
        retry_after: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        self.allowed = allowed
        self.limit = limit
        self.remaining = remaining
        self.reset_time = reset_time
        self.retry_after = retry_after or int(max(0, reset_time - time.time()))
        self.error_message = error_message

    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP rate limit headers."""
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_time)),
            "Retry-After": str(self.retry_after) if not self.allowed else None,
        }


class RateLimitConfig:
    """Configuration for rate limiting."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_per_minute: int = 60,
        default_per_hour: int = 1000,
        default_per_day: int = 10000,
        endpoint_limits: Optional[Dict[str, Dict[str, int]]] = None,
        use_redis: bool = True,
        fallback_to_memory: bool = True,
    ):
        """
        Initialize rate limit configuration.

        Args:
            redis_url: Redis connection URL
            default_per_minute: Default requests per minute
            default_per_hour: Default requests per hour
            default_per_day: Default requests per day
            endpoint_limits: Per-endpoint limits (e.g., {'/api/v1/llm/generate': {'per_minute': 10}})
            use_redis: Whether to use Redis (True) or in-memory (False)
            fallback_to_memory: Fallback to in-memory if Redis unavailable
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.default_per_minute = default_per_minute
        self.default_per_hour = default_per_hour
        self.default_per_day = default_per_day
        self.endpoint_limits = endpoint_limits or {}
        self.use_redis = use_redis
        self.fallback_to_memory = fallback_to_memory

        # In-memory fallback storage
        self._memory_storage: Dict[str, list] = {}
        self._memory_lock = asyncio.Lock()


class RateLimiter:
    """Redis-based rate limiter with sliding window algorithm."""

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self.redis: Optional[aioredis.Redis] = None
        self._connection_pool: Optional[aioredis.ConnectionPool] = None
        self._is_connected = False
        self._use_redis = self.config.use_redis

    async def connect(self) -> bool:
        """Connect to Redis."""
        if not self.config.use_redis:
            logger.info("Rate limiting using in-memory storage (Redis disabled)")
            return True

        try:
            self._connection_pool = aioredis.ConnectionPool.from_url(
                self.config.redis_url,
                max_connections=50,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            self.redis = aioredis.Redis(connection_pool=self._connection_pool)

            # Test connection
            await self.redis.ping()
            self._is_connected = True
            logger.info(
                f"Connected to Redis for rate limiting at {self.config.redis_url}"
            )
            return True
        except (RedisError, ConnectionError) as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            if self.config.fallback_to_memory:
                logger.info("Falling back to in-memory rate limiting")
                self._use_redis = False
                return True
            self._is_connected = False
            return False

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()
        self._is_connected = False
        logger.info("Disconnected from Redis")

    def _make_key(self, identifier_type: str, identifier: str, limit_type: str) -> str:
        """Create a Redis key for rate limiting."""
        return f"june:rate_limit:{identifier_type}:{identifier}:{limit_type}"

    async def check_rate_limit(
        self,
        identifier: str,
        identifier_type: str = "user",
        endpoint: Optional[str] = None,
        per_minute: Optional[int] = None,
        per_hour: Optional[int] = None,
        per_day: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Check rate limit for an identifier.

        Args:
            identifier: User ID, IP address, or other identifier
            identifier_type: Type of identifier ('user', 'ip', 'endpoint')
            endpoint: Optional endpoint path for per-endpoint limits
            per_minute: Override per-minute limit
            per_hour: Override per-hour limit
            per_day: Override per-day limit

        Returns:
            RateLimitResult with allowed status and metadata
        """
        # Get limits for this endpoint if specified
        if endpoint and endpoint in self.config.endpoint_limits:
            endpoint_config = self.config.endpoint_limits[endpoint]
            per_minute = per_minute or endpoint_config.get(
                "per_minute", self.config.default_per_minute
            )
            per_hour = per_hour or endpoint_config.get(
                "per_hour", self.config.default_per_hour
            )
            per_day = per_day or endpoint_config.get(
                "per_day", self.config.default_per_day
            )
        else:
            per_minute = per_minute or self.config.default_per_minute
            per_hour = per_hour or self.config.default_per_hour
            per_day = per_day or self.config.default_per_day

        # Check all limits (most restrictive wins)
        results = []
        for limit_type, limit_value, window_seconds in [
            ("per_minute", per_minute, 60),
            ("per_hour", per_hour, 3600),
            ("per_day", per_day, 86400),
        ]:
            result = await self._check_limit(
                identifier, identifier_type, limit_type, limit_value, window_seconds
            )
            results.append(result)

            # Record metrics
            RATE_LIMIT_CHECKS.labels(
                identifier_type=identifier_type,
                result="allowed" if result.allowed else "denied",
            ).inc()

            if not result.allowed:
                RATE_LIMIT_VIOLATIONS.labels(
                    identifier_type=identifier_type, limit_type=limit_type
                ).inc()
                RATE_LIMIT_WAIT_TIME.labels(identifier_type=identifier_type).observe(
                    result.retry_after
                )

        # Return the most restrictive result (first denied, or least remaining)
        denied_results = [r for r in results if not r.allowed]
        if denied_results:
            # Return the one with longest retry_after
            return max(denied_results, key=lambda r: r.retry_after)

        # All allowed - return the one with least remaining
        return min(results, key=lambda r: r.remaining)

    async def _check_limit(
        self,
        identifier: str,
        identifier_type: str,
        limit_type: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check a single rate limit."""
        if self._use_redis and self._is_connected:
            return await self._check_limit_redis(
                identifier, identifier_type, limit_type, limit, window_seconds
            )
        else:
            return await self._check_limit_memory(
                identifier, identifier_type, limit_type, limit, window_seconds
            )

    async def _check_limit_redis(
        self,
        identifier: str,
        identifier_type: str,
        limit_type: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check rate limit using Redis sliding window."""
        try:
            key = self._make_key(identifier_type, identifier, limit_type)
            now = time.time()
            window_start = now - window_seconds

            # Use Redis sorted set for sliding window
            pipe = self.redis.pipeline()

            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current requests in window
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(now): now})

            # Set expiration
            pipe.expire(key, window_seconds + 1)

            # Execute pipeline
            results = await pipe.execute()
            current_count = results[1]  # Count before adding current request

            # Check if limit exceeded
            allowed = current_count < limit
            remaining = max(0, limit - current_count - 1) if allowed else 0
            reset_time = now + window_seconds

            if not allowed:
                # Calculate retry after (time until oldest request expires)
                oldest = await self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = oldest[0][1]
                    retry_after = int(max(0, oldest_time + window_seconds - now))
                else:
                    retry_after = window_seconds
            else:
                retry_after = None

            return RateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_time=reset_time,
                retry_after=retry_after,
                error_message=None
                if allowed
                else f"Rate limit exceeded: {limit} requests per {window_seconds}s",
            )

        except (RedisError, ConnectionError) as e:
            logger.warning(f"Redis error in rate limit check: {e}")
            # Fallback to memory if configured
            if self.config.fallback_to_memory:
                self._use_redis = False
                return await self._check_limit_memory(
                    identifier, identifier_type, limit_type, limit, window_seconds
                )
            # If no fallback, allow the request (fail open)
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit - 1,
                reset_time=time.time() + window_seconds,
                error_message=None,
            )

    async def _check_limit_memory(
        self,
        identifier: str,
        identifier_type: str,
        limit_type: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check rate limit using in-memory storage."""
        async with self._memory_lock:
            key = f"{identifier_type}:{identifier}:{limit_type}"
            now = time.time()
            window_start = now - window_seconds

            # Get or create request list
            if key not in self.config._memory_storage:
                self.config._memory_storage[key] = []

            requests = self.config._memory_storage[key]

            # Remove old requests outside the window
            requests = [ts for ts in requests if ts > window_start]
            self.config._memory_storage[key] = requests

            # Check limit
            current_count = len(requests)
            allowed = current_count < limit
            remaining = max(0, limit - current_count - 1) if allowed else 0
            reset_time = now + window_seconds

            if not allowed:
                # Calculate retry after
                oldest = min(requests) if requests else now
                retry_after = int(max(0, oldest + window_seconds - now))
            else:
                retry_after = None
                # Add current request
                requests.append(now)
                self.config._memory_storage[key] = requests

            return RateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_time=reset_time,
                retry_after=retry_after,
                error_message=None
                if allowed
                else f"Rate limit exceeded: {limit} requests per {window_seconds}s",
            )

    async def get_stats(
        self, identifier: str, identifier_type: str = "user"
    ) -> Dict[str, int]:
        """Get rate limit statistics for an identifier."""
        stats = {}
        for limit_type, window_seconds in [
            ("per_minute", 60),
            ("per_hour", 3600),
            ("per_day", 86400),
        ]:
            key = self._make_key(identifier_type, identifier, limit_type)
            if self._use_redis and self._is_connected:
                try:
                    now = time.time()
                    window_start = now - window_seconds
                    count = await self.redis.zcount(key, window_start, now)
                    stats[limit_type] = count
                except (RedisError, ConnectionError):
                    stats[limit_type] = 0
            else:
                async with self._memory_lock:
                    memory_key = f"{identifier_type}:{identifier}:{limit_type}"
                    if memory_key in self.config._memory_storage:
                        now = time.time()
                        window_start = now - window_seconds
                        requests = self.config._memory_storage[memory_key]
                        stats[limit_type] = len(
                            [ts for ts in requests if ts > window_start]
                        )
                    else:
                        stats[limit_type] = 0

        return stats

    async def reset_limit(self, identifier: str, identifier_type: str = "user"):
        """Reset rate limit for an identifier (admin/testing)."""
        for limit_type in ["per_minute", "per_hour", "per_day"]:
            key = self._make_key(identifier_type, identifier, limit_type)
            if self._use_redis and self._is_connected:
                try:
                    await self.redis.delete(key)
                except (RedisError, ConnectionError):
                    pass
            else:
                async with self._memory_lock:
                    memory_key = f"{identifier_type}:{identifier}:{limit_type}"
                    if memory_key in self.config._memory_storage:
                        del self.config._memory_storage[memory_key]
