# June Metrics

Comprehensive Prometheus metrics module for performance monitoring and bottleneck identification.

## Features

- **Database Metrics**: Query time tracking, slow query detection, connection pool utilization
- **GPU Metrics**: GPU utilization, memory usage, temperature, power, inference time
- **Queue Metrics**: Queue depth, processing time, wait time, throughput
- **Service Metrics**: Memory usage, CPU usage, thread count, uptime
- **Performance Metrics**: Response time, request throughput by endpoint

## Usage

```python
from june_metrics import PerformanceMetrics
from prometheus_client import CollectorRegistry

# Create metrics instance
registry = CollectorRegistry()
metrics = PerformanceMetrics(registry=registry, service_name="gateway")

# Track database query
with metrics.database.track_query("SELECT", table="users", operation="read"):
    # Execute query
    cursor.execute("SELECT * FROM users")

# Track GPU inference
metrics.gpu.observe_inference("qwen3-30b", "0", duration=0.5)

# Track queue processing
metrics.queue.set_queue_depth("voice_queue", "fifo", depth=10)
metrics.queue.observe_processing("voice_queue", duration=2.0, status="success")

# Track service metrics
metrics.service.update_memory_usage(memory_bytes=1024*1024*100)
metrics.service.update_cpu_usage(cpu_percent=45.5)

# Track response time
metrics.observe_response("/api/chat", "POST", 200, duration=0.3)
```

## Metrics Exposed

All metrics follow Prometheus naming conventions and include appropriate labels for filtering and aggregation.

### Database Metrics
- `{service}_db_query_duration_seconds` - Query execution time histogram
- `{service}_db_queries_total` - Total queries counter
- `{service}_db_slow_queries_total` - Slow queries (>1s) counter
- `{service}_db_pool_utilization` - Connection pool utilization gauge

### GPU Metrics
- `{service}_gpu_utilization_percent` - GPU utilization percentage
- `{service}_gpu_memory_used_bytes` - GPU memory used
- `{service}_gpu_memory_total_bytes` - GPU memory total
- `{service}_gpu_temperature_celsius` - GPU temperature
- `{service}_gpu_power_watts` - GPU power usage
- `{service}_gpu_inference_time_seconds` - GPU inference time histogram

### Queue Metrics
- `{service}_queue_depth` - Current queue depth
- `{service}_queue_processing_time_seconds` - Item processing time histogram
- `{service}_queue_items_processed_total` - Items processed counter
- `{service}_queue_items_added_total` - Items added counter
- `{service}_queue_wait_time_seconds` - Wait time histogram

### Service Metrics
- `{service}_memory_usage_bytes` - Service memory usage
- `{service}_memory_rss_bytes` - Service RSS memory
- `{service}_cpu_usage_percent` - Service CPU usage
- `{service}_thread_count` - Active thread count
- `{service}_uptime_seconds` - Service uptime

## Integration

This module is designed to be integrated into June services to provide comprehensive performance monitoring. Metrics are automatically exposed via Prometheus and can be visualized in Grafana dashboards.
