"""
June Cache Module - Redis-based caching with Prometheus metrics.

This module provides:
- Redis-based caching with TTL support
- Cache invalidation strategies
- Cache warming capabilities
- Prometheus metrics for cache hit/miss rates
- Support for different cache types (LLM responses, STT/TTS results, sessions, DB queries)
"""

from .cache import CacheManager, CacheConfig, CacheType
from .metrics import CacheMetrics

__all__ = [
    'CacheManager',
    'CacheConfig',
    'CacheType',
    'CacheMetrics',
]

__version__ = "0.1.0"
