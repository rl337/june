"""
Inference result caching for LLM, STT, and TTS services.
Reduces redundant computations by caching identical inputs.
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
    """Cache entry for inference results."""

    result: Any
    timestamp: float
    access_count: int = 0
    last_accessed: float = 0.0


class InferenceCache:
    """LRU cache for inference results."""

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: Optional[float] = None,
        enable_cache: bool = True,
    ):
        """Initialize inference cache.

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

    def _generate_key(self, input_data: Any, model_name: Optional[str] = None) -> str:
        """Generate cache key from input data.

        Args:
            input_data: Input data (prompt, audio, etc.)
            model_name: Optional model name to include in key

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

        # Include model name if provided
        if model_name:
            data_str = f"{model_name}:{data_str}"

        # Generate hash
        return hashlib.sha256(data_str.encode()).hexdigest()

    def get(self, input_data: Any, model_name: Optional[str] = None) -> Optional[Any]:
        """Get cached result if available.

        Args:
            input_data: Input data to look up
            model_name: Optional model name

        Returns:
            Cached result or None if not found/expired
        """
        if not self.enable_cache:
            return None

        key = self._generate_key(input_data, model_name)

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

        return entry.result

    def put(
        self, input_data: Any, result: Any, model_name: Optional[str] = None
    ) -> None:
        """Store result in cache.

        Args:
            input_data: Input data
            result: Result to cache
            model_name: Optional model name
        """
        if not self.enable_cache:
            return

        key = self._generate_key(input_data, model_name)
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

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

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
        """Remove expired entries from cache.

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

        return len(expired_keys)


# Global cache instances (can be shared across services)
_llm_cache: Optional[InferenceCache] = None
_stt_cache: Optional[InferenceCache] = None
_tts_cache: Optional[InferenceCache] = None


def get_llm_cache(
    max_size: int = 1000, ttl_seconds: Optional[float] = 3600
) -> InferenceCache:
    """Get or create global LLM cache.

    Args:
        max_size: Maximum cache size
        ttl_seconds: Time-to-live in seconds (default: 1 hour)

    Returns:
        Global LLM cache instance
    """
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = InferenceCache(max_size=max_size, ttl_seconds=ttl_seconds)
    return _llm_cache


def get_stt_cache(
    max_size: int = 500, ttl_seconds: Optional[float] = 7200
) -> InferenceCache:
    """Get or create global STT cache.

    Args:
        max_size: Maximum cache size
        ttl_seconds: Time-to-live in seconds (default: 2 hours)

    Returns:
        Global STT cache instance
    """
    global _stt_cache
    if _stt_cache is None:
        _stt_cache = InferenceCache(max_size=max_size, ttl_seconds=ttl_seconds)
    return _stt_cache


def get_tts_cache(
    max_size: int = 500, ttl_seconds: Optional[float] = 7200
) -> InferenceCache:
    """Get or create global TTS cache.

    Args:
        max_size: Maximum cache size
        ttl_seconds: Time-to-live in seconds (default: 2 hours)

    Returns:
        Global TTS cache instance
    """
    global _tts_cache
    if _tts_cache is None:
        _tts_cache = InferenceCache(max_size=max_size, ttl_seconds=ttl_seconds)
    return _tts_cache
