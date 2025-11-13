"""
June Rate Limit Module - Redis-based rate limiting with Prometheus metrics.

This module provides:
- Redis-based rate limiting with sliding window algorithm
- Per-user, per-IP, and per-endpoint rate limiting
- Configurable rate limits with different thresholds
- Rate limit headers in responses
- Prometheus metrics for monitoring
"""

from .rate_limiter import RateLimiter, RateLimitConfig, RateLimitResult
from .middleware import RateLimitMiddleware
from .grpc_interceptor import RateLimitInterceptor

__all__ = [
    'RateLimiter',
    'RateLimitConfig',
    'RateLimitResult',
    'RateLimitMiddleware',
    'RateLimitInterceptor',
]

__version__ = "0.1.0"
