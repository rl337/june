"""
Caching for Agentic Reasoning Components

Caches common reasoning patterns, plans, and reflections to improve latency.
"""
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for reasoning results."""

    result: Any
    timestamp: float
    access_count: int = 0
    last_accessed: float = 0.0


class ReasoningCache:
    """
    LRU cache for reasoning patterns, plans, and reflections.

    Caches:
    - Think phase results (analysis)
    - Plan phase results (execution plans)
    - Reflection phase results (evaluations)
    """

    def __init__(
        self,
        max_size: int = 500,
        ttl_seconds: Optional[float] = 3600,  # 1 hour default
        enable_cache: bool = True,
    ):
        """
        Initialize reasoning cache.

        Args:
            max_size: Maximum number of entries in cache
            ttl_seconds: Time-to-live for cache entries (None = no expiration)
            enable_cache: Whether caching is enabled
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.enable_cache = enable_cache
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _generate_key(
        self,
        cache_type: str,
        input_data: Any,
        context_hash: Optional[str] = None,
    ) -> str:
        """
        Generate cache key from input data.

        Args:
            cache_type: Type of cache entry ("think", "plan", "reflect")
            input_data: Input data (user message, plan, etc.)
            context_hash: Optional context hash for additional specificity

        Returns:
            Cache key as hex string
        """
        # Create a hashable representation of the input
        if isinstance(input_data, str):
            data_str = input_data
        elif isinstance(input_data, (dict, list)):
            data_str = json.dumps(input_data, sort_keys=True)
        else:
            data_str = str(input_data)

        # Include context hash if provided
        if context_hash:
            data_str = f"{context_hash}:{data_str}"

        # Generate hash
        key_data = f"{cache_type}:{data_str}"
        key_hash = hashlib.sha256(key_data.encode()).hexdigest()

        return key_hash

    def get(
        self,
        cache_type: str,
        input_data: Any,
        context_hash: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Get cached result if available.

        Args:
            cache_type: Type of cache entry ("think", "plan", "reflect")
            input_data: Input data to look up
            context_hash: Optional context hash

        Returns:
            Cached result or None if not found/expired
        """
        if not self.enable_cache:
            return None

        key = self._generate_key(cache_type, input_data, context_hash)

        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]
        current_time = time.time()

        # Check TTL
        if self.ttl_seconds and (current_time - entry.timestamp) > self.ttl_seconds:
            # Entry expired, remove it
            del self._cache[key]
            self._misses += 1
            return None

        # Update access info and move to end (LRU)
        entry.access_count += 1
        entry.last_accessed = current_time
        self._cache.move_to_end(key)
        self._hits += 1

        logger.debug(f"Cache hit for {cache_type}: {key[:16]}...")
        return entry.result

    def put(
        self,
        cache_type: str,
        input_data: Any,
        result: Any,
        context_hash: Optional[str] = None,
    ) -> None:
        """
        Store result in cache.

        Args:
            cache_type: Type of cache entry ("think", "plan", "reflect")
            input_data: Input data
            result: Result to cache
            context_hash: Optional context hash
        """
        if not self.enable_cache:
            return

        key = self._generate_key(cache_type, input_data, context_hash)
        current_time = time.time()

        # Create new entry
        entry = CacheEntry(
            result=result,
            timestamp=current_time,
            access_count=1,
            last_accessed=current_time,
        )

        # Remove oldest entry if cache is full
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)  # Remove oldest (first) item

        # Add new entry
        self._cache[key] = entry
        logger.debug(f"Cached {cache_type} result: {key[:16]}...")

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Reasoning cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "enabled": self.enable_cache,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": hit_rate,
            "ttl_seconds": self.ttl_seconds,
        }

    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        if not self.ttl_seconds:
            return 0

        current_time = time.time()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if (current_time - entry.timestamp) > self.ttl_seconds
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def _generate_context_hash(self, context: Any) -> Optional[str]:
        """
        Generate a hash from conversation context.

        Args:
            context: ConversationContext or similar object

        Returns:
            Context hash string or None
        """
        try:
            # Extract relevant context fields
            context_data = {}
            if hasattr(context, "user_id"):
                context_data["user_id"] = context.user_id
            if hasattr(context, "chat_id"):
                context_data["chat_id"] = context.chat_id
            if hasattr(context, "message_history") and context.message_history:
                # Use last few messages for context
                recent_messages = context.message_history[-3:]
                context_data["recent_messages"] = [
                    {"role": msg.get("role"), "content": msg.get("content", "")[:50]}
                    for msg in recent_messages
                ]

            if context_data:
                context_str = json.dumps(context_data, sort_keys=True)
                return hashlib.sha256(context_str.encode()).hexdigest()[:16]
        except Exception as e:
            logger.debug(f"Error generating context hash: {e}")

        return None


# Global cache instance (can be shared across reasoning components)
_reasoning_cache: Optional[ReasoningCache] = None


def get_reasoning_cache(
    max_size: int = 500,
    ttl_seconds: Optional[float] = 3600,
) -> ReasoningCache:
    """
    Get or create global reasoning cache.

    Args:
        max_size: Maximum cache size
        ttl_seconds: Time-to-live in seconds (default: 1 hour)

    Returns:
        Global reasoning cache instance
    """
    global _reasoning_cache
    if _reasoning_cache is None:
        _reasoning_cache = ReasoningCache(
            max_size=max_size,
            ttl_seconds=ttl_seconds,
        )
    return _reasoning_cache
