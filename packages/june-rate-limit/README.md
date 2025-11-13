# June Rate Limit

Redis-based rate limiting for June services with Prometheus metrics.

## Features

- Redis-based rate limiting with sliding window algorithm
- Per-user, per-IP, and per-endpoint rate limiting
- Configurable rate limits with different thresholds
- Rate limit headers in HTTP responses
- Prometheus metrics for monitoring
- FastAPI middleware integration
- gRPC interceptor integration
- In-memory fallback when Redis is unavailable

## Installation

```bash
cd packages/june-rate-limit
pip install -e .
```

## Usage

### FastAPI Middleware

```python
from fastapi import FastAPI
from june_rate_limit import RateLimitMiddleware, RateLimitConfig

app = FastAPI()

# Configure rate limits
config = RateLimitConfig(
    default_per_minute=60,
    default_per_hour=1000,
    endpoint_limits={
        '/api/v1/llm/generate': {
            'per_minute': 10,  # Stricter for expensive operations
            'per_hour': 100,
        }
    }
)

# Add middleware
app.add_middleware(RateLimitMiddleware, config=config)
```

### gRPC Interceptor

```python
from grpc import aio
from june_rate_limit import RateLimitInterceptor, RateLimitConfig

config = RateLimitConfig(
    default_per_minute=60,
    default_per_hour=1000,
)

interceptor = RateLimitInterceptor(config=config)
server = aio.server(interceptors=[interceptor])
```

### Direct Usage

```python
from june_rate_limit import RateLimiter, RateLimitConfig

config = RateLimitConfig(
    default_per_minute=60,
    default_per_hour=1000,
)

rate_limiter = RateLimiter(config)
await rate_limiter.connect()

# Check rate limit
result = await rate_limiter.check_rate_limit(
    identifier="user123",
    identifier_type="user",
    endpoint="/api/v1/llm/generate"
)

if result.allowed:
    # Process request
    pass
else:
    # Rate limited
    print(f"Rate limit exceeded. Retry after {result.retry_after}s")
```

## Configuration

### Environment Variables

- `REDIS_URL`: Redis connection URL (default: `redis://redis:6379/0`)
- `RATE_LIMIT_PER_MINUTE`: Default requests per minute (default: 60)
- `RATE_LIMIT_PER_HOUR`: Default requests per hour (default: 1000)
- `RATE_LIMIT_PER_DAY`: Default requests per day (default: 10000)

### Rate Limit Headers

HTTP responses include standard rate limit headers:

- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when limit resets
- `Retry-After`: Seconds to wait before retrying (only when rate limited)

## Prometheus Metrics

- `rate_limit_checks_total`: Total rate limit checks (by identifier_type, result)
- `rate_limit_violations_total`: Total rate limit violations (by identifier_type, limit_type)
- `rate_limit_wait_time_seconds`: Time until rate limit resets
- `rate_limit_active_limits`: Number of active rate limits

## License

See main project LICENSE file.
