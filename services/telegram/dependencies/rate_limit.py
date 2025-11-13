"""Rate limiting per user to prevent abuse."""
import asyncio
import logging
import os
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# Try to use Redis-based rate limiting, fallback to in-memory
try:
    from june_rate_limit import RateLimiter as RedisRateLimiter, RateLimitConfig
    REDIS_RATE_LIMIT_AVAILABLE = True
except ImportError:
    REDIS_RATE_LIMIT_AVAILABLE = False
    RedisRateLimiter = None
    RateLimitConfig = None

# Fallback to in-memory rate limiter if Redis not available
if not REDIS_RATE_LIMIT_AVAILABLE:
    import time
    from collections import defaultdict
    
    class InMemoryRateLimiter:
        """In-memory rate limiter with sliding window per user (fallback)."""
        
        def __init__(
            self,
            max_requests_per_minute: int = 10,
            max_requests_per_hour: int = 100,
            max_requests_per_day: int = 500
        ):
            self.max_per_minute = max_requests_per_minute
            self.max_per_hour = max_requests_per_hour
            self.max_per_day = max_requests_per_day
            self._user_requests: Dict[str, list] = defaultdict(list)
            self._lock = asyncio.Lock()
        
        async def check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[str]]:
            async with self._lock:
                now = time.time()
                user_requests = self._user_requests[user_id]
                
                cutoff_24h = now - 86400
                user_requests = [ts for ts in user_requests if ts > cutoff_24h]
                self._user_requests[user_id] = user_requests
                
                cutoff_1m = now - 60
                requests_1m = [ts for ts in user_requests if ts > cutoff_1m]
                if len(requests_1m) >= self.max_per_minute:
                    return False, (
                        f"Rate limit exceeded: {len(requests_1m)} requests in the last minute. "
                        f"Maximum allowed: {self.max_per_minute} requests/minute."
                    )
                
                cutoff_1h = now - 3600
                requests_1h = [ts for ts in user_requests if ts > cutoff_1h]
                if len(requests_1h) >= self.max_per_hour:
                    return False, (
                        f"Rate limit exceeded: {len(requests_1h)} requests in the last hour. "
                        f"Maximum allowed: {self.max_per_hour} requests/hour."
                    )
                
                if len(user_requests) >= self.max_per_day:
                    return False, (
                        f"Rate limit exceeded: {len(user_requests)} requests in the last 24 hours. "
                        f"Maximum allowed: {self.max_per_day} requests/day."
                    )
                
                user_requests.append(now)
                self._user_requests[user_id] = user_requests
                return True, None
        
        async def get_user_stats(self, user_id: str) -> Dict[str, int]:
            async with self._lock:
                now = time.time()
                user_requests = self._user_requests.get(user_id, [])
                cutoff_24h = now - 86400
                user_requests = [ts for ts in user_requests if ts > cutoff_24h]
                cutoff_1m = now - 60
                cutoff_1h = now - 3600
                return {
                    'requests_1m': len([ts for ts in user_requests if ts > cutoff_1m]),
                    'requests_1h': len([ts for ts in user_requests if ts > cutoff_1h]),
                    'requests_24h': len(user_requests),
                    'max_per_minute': self.max_per_minute,
                    'max_per_hour': self.max_per_hour,
                    'max_per_day': self.max_per_day
                }
        
        def clear_user(self, user_id: str):
            if user_id in self._user_requests:
                del self._user_requests[user_id]


class RateLimiter:
    """Rate limiter wrapper that uses Redis if available, falls back to in-memory."""
    
    def __init__(
        self,
        max_requests_per_minute: int = 10,
        max_requests_per_hour: int = 100,
        max_requests_per_day: int = 500
    ):
        self.max_per_minute = max_requests_per_minute
        self.max_per_hour = max_requests_per_hour
        self.max_per_day = max_requests_per_day
        
        if REDIS_RATE_LIMIT_AVAILABLE:
            # Use Redis-based rate limiting
            config = RateLimitConfig(
                default_per_minute=max_requests_per_minute,
                default_per_hour=max_requests_per_hour,
                default_per_day=max_requests_per_day,
            )
            self._limiter = RedisRateLimiter(config)
            self._use_redis = True
        else:
            # Fallback to in-memory
            self._limiter = InMemoryRateLimiter(
                max_requests_per_minute=max_requests_per_minute,
                max_requests_per_hour=max_requests_per_hour,
                max_requests_per_day=max_requests_per_day
            )
            self._use_redis = False
    
    async def check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """Check if user has exceeded rate limits."""
        if self._use_redis:
            # Connect if not already connected
            if not self._limiter._is_connected:
                await self._limiter.connect()
            
            result = await self._limiter.check_rate_limit(
                identifier=user_id,
                identifier_type="user",
            )
            return result.allowed, result.error_message
        else:
            return await self._limiter.check_rate_limit(user_id)
    
    async def get_user_stats(self, user_id: str) -> Dict[str, int]:
        """Get rate limit statistics for a user."""
        if self._use_redis:
            if not self._limiter._is_connected:
                await self._limiter.connect()
            return await self._limiter.get_stats(user_id, "user")
        else:
            return await self._limiter.get_user_stats(user_id)
    
    def clear_user(self, user_id: str):
        """Clear rate limit history for a user (for testing/admin)."""
        if self._use_redis:
            if self._limiter._is_connected:
                asyncio.create_task(self._limiter.reset_limit(user_id, "user"))
        else:
            self._limiter.clear_user(user_id)


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        max_per_minute = int(os.getenv("TELEGRAM_RATE_LIMIT_PER_MINUTE", "10"))
        max_per_hour = int(os.getenv("TELEGRAM_RATE_LIMIT_PER_HOUR", "100"))
        max_per_day = int(os.getenv("TELEGRAM_RATE_LIMIT_PER_DAY", "500"))
        
        _rate_limiter = RateLimiter(
            max_requests_per_minute=max_per_minute,
            max_requests_per_hour=max_per_hour,
            max_requests_per_day=max_per_day
        )
    return _rate_limiter
