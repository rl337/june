"""
Cache Metrics - Prometheus metrics for cache performance.
"""
from typing import Optional
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

class CacheMetrics:
    """Prometheus metrics for cache operations."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry
        
        # Cache hit/miss counters by type
        self.cache_hits = Counter(
            'cache_hits_total',
            'Total cache hits',
            ['cache_type'],
            registry=registry
        )
        
        self.cache_misses = Counter(
            'cache_misses_total',
            'Total cache misses',
            ['cache_type'],
            registry=registry
        )
        
        # Cache operation duration
        self.cache_operation_duration = Histogram(
            'cache_operation_duration_seconds',
            'Cache operation duration',
            ['operation', 'cache_type'],
            registry=registry
        )
        
        # Cache size (number of keys) by type
        self.cache_size = Gauge(
            'cache_size_keys',
            'Number of keys in cache',
            ['cache_type'],
            registry=registry
        )
        
        # Cache hit rate (calculated metric)
        self.cache_hit_rate = Gauge(
            'cache_hit_rate',
            'Cache hit rate (0-1)',
            ['cache_type'],
            registry=registry
        )
    
    def record_hit(self, cache_type: str):
        """Record a cache hit."""
        self.cache_hits.labels(cache_type=cache_type).inc()
        self._update_hit_rate(cache_type)
    
    def record_miss(self, cache_type: str):
        """Record a cache miss."""
        self.cache_misses.labels(cache_type=cache_type).inc()
        self._update_hit_rate(cache_type)
    
    def _update_hit_rate(self, cache_type: str):
        """Update cache hit rate metric."""
        hits = self.cache_hits.labels(cache_type=cache_type)._value.get()
        misses = self.cache_misses.labels(cache_type=cache_type)._value.get()
        total = hits + misses
        
        if total > 0:
            hit_rate = hits / total
            self.cache_hit_rate.labels(cache_type=cache_type).set(hit_rate)
        else:
            self.cache_hit_rate.labels(cache_type=cache_type).set(0.0)
    
    def observe_operation(self, operation: str, cache_type: str, duration: float):
        """Observe cache operation duration."""
        self.cache_operation_duration.labels(
            operation=operation,
            cache_type=cache_type
        ).observe(duration)
    
    def set_cache_size(self, cache_type: str, size: int):
        """Set cache size metric."""
        self.cache_size.labels(cache_type=cache_type).set(size)
