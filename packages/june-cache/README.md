# June Cache

Redis-based caching layer for June services with Prometheus metrics.

## Features

- Redis-based distributed caching
- TTL support per cache type
- Cache invalidation strategies
- Cache warming capabilities
- Prometheus metrics for cache hit/miss rates
- Support for multiple cache types:
  - LLM responses
  - STT transcriptions
  - TTS synthesis results
  - User sessions
  - Database queries

## Installation

```bash
cd packages/june-cache
pip install -e .
```

## Usage

```python
from june_cache import CacheManager, CacheConfig, CacheType, CacheMetrics
from prometheus_client import CollectorRegistry

# Setup metrics
registry = CollectorRegistry()
metrics = CacheMetrics(registry=registry)

# Configure cache
config = CacheConfig(
    redis_url="redis://redis:6379/0",
    default_ttl=3600
)

# Create cache manager
cache = CacheManager(config=config, metrics=metrics)

# Connect to Redis
await cache.connect()

# Cache a value
await cache.set(CacheType.LLM_RESPONSE, "query_hash", {"response": "..."})

# Get from cache
value = await cache.get(CacheType.LLM_RESPONSE, "query_hash")

# Get or compute
value = await cache.get_or_set(
    CacheType.LLM_RESPONSE,
    "query_hash",
    compute_function,
    args...
)

# Invalidate
await cache.delete(CacheType.LLM_RESPONSE, "query_hash")
await cache.invalidate_type(CacheType.LLM_RESPONSE)

# Disconnect
await cache.disconnect()
```

## Environment Variables

- `REDIS_URL`: Redis connection URL (default: `redis://redis:6379/0`)
- `CACHE_TTL_LLM`: TTL for LLM responses in seconds (default: 7200)
- `CACHE_TTL_STT`: TTL for STT transcriptions in seconds (default: 86400)
- `CACHE_TTL_TTS`: TTL for TTS synthesis results in seconds (default: 86400)
- `CACHE_TTL_SESSION`: TTL for user sessions in seconds (default: 1800)
- `CACHE_TTL_DB`: TTL for database queries in seconds (default: 300)

## Metrics

The module exports Prometheus metrics:

- `cache_hits_total`: Total cache hits by cache type
- `cache_misses_total`: Total cache misses by cache type
- `cache_operation_duration_seconds`: Cache operation duration
- `cache_size_keys`: Number of keys in cache by type
- `cache_hit_rate`: Cache hit rate (0-1) by cache type
