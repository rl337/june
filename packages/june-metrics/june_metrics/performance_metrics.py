"""
Performance Metrics - Comprehensive Prometheus metrics for bottleneck identification.
"""
import os
import time
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

logger = logging.getLogger(__name__)


class DatabaseMetrics:
    """Prometheus metrics for database query performance."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None, service_name: str = "default"):
        self.registry = registry
        self.service_name = service_name
        
        # Database query time histogram by query type
        self.query_duration = Histogram(
            f'{service_name}_db_query_duration_seconds',
            'Database query duration',
            ['query_type', 'table', 'operation'],
            registry=registry
        )
        
        # Database query count by status
        self.query_count = Counter(
            f'{service_name}_db_queries_total',
            'Total database queries',
            ['query_type', 'status'],
            registry=registry
        )
        
        # Slow query counter (queries > 1 second)
        self.slow_queries = Counter(
            f'{service_name}_db_slow_queries_total',
            'Slow database queries (>1s)',
            ['query_type', 'table'],
            registry=registry
        )
        
        # Database connection pool utilization
        self.pool_utilization = Gauge(
            f'{service_name}_db_pool_utilization',
            'Database connection pool utilization (0-1)',
            ['pool_name'],
            registry=registry
        )
    
    @contextmanager
    def track_query(self, query_type: str, table: str = "unknown", operation: str = "unknown"):
        """Context manager to track database query execution time."""
        start_time = time.time()
        status = "success"
        
        try:
            yield
        except Exception as e:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            self.query_duration.labels(
                query_type=query_type,
                table=table,
                operation=operation
            ).observe(duration)
            
            self.query_count.labels(
                query_type=query_type,
                status=status
            ).inc()
            
            # Track slow queries
            if duration > 1.0:
                self.slow_queries.labels(
                    query_type=query_type,
                    table=table
                ).inc()
    
    def set_pool_utilization(self, pool_name: str, active: int, max_connections: int):
        """Set connection pool utilization metric."""
        if max_connections > 0:
            utilization = active / max_connections
            self.pool_utilization.labels(pool_name=pool_name).set(utilization)


class GPUMetrics:
    """Prometheus metrics for GPU utilization."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None, service_name: str = "default"):
        self.registry = registry
        self.service_name = service_name
        
        # GPU utilization percentage
        self.gpu_utilization = Gauge(
            f'{service_name}_gpu_utilization_percent',
            'GPU utilization percentage',
            ['gpu_id', 'gpu_name'],
            registry=registry
        )
        
        # GPU memory usage
        self.gpu_memory_used = Gauge(
            f'{service_name}_gpu_memory_used_bytes',
            'GPU memory used in bytes',
            ['gpu_id', 'gpu_name'],
            registry=registry
        )
        
        # GPU memory total
        self.gpu_memory_total = Gauge(
            f'{service_name}_gpu_memory_total_bytes',
            'GPU memory total in bytes',
            ['gpu_id', 'gpu_name'],
            registry=registry
        )
        
        # GPU temperature
        self.gpu_temperature = Gauge(
            f'{service_name}_gpu_temperature_celsius',
            'GPU temperature in Celsius',
            ['gpu_id', 'gpu_name'],
            registry=registry
        )
        
        # GPU power usage
        self.gpu_power = Gauge(
            f'{service_name}_gpu_power_watts',
            'GPU power usage in watts',
            ['gpu_id', 'gpu_name'],
            registry=registry
        )
        
        # Model inference time on GPU
        self.gpu_inference_time = Histogram(
            f'{service_name}_gpu_inference_time_seconds',
            'GPU inference time',
            ['model_name', 'gpu_id'],
            registry=registry
        )
    
    def update_gpu_metrics(self, gpu_id: str, gpu_name: str, metrics: Dict[str, Any]):
        """Update GPU metrics from monitoring data.
        
        Args:
            gpu_id: GPU identifier (e.g., '0', '1')
            gpu_name: GPU name/model
            metrics: Dictionary with keys: utilization, memory_used, memory_total,
                    temperature, power
        """
        if 'utilization' in metrics:
            self.gpu_utilization.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(
                metrics['utilization']
            )
        
        if 'memory_used' in metrics:
            self.gpu_memory_used.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(
                metrics['memory_used']
            )
        
        if 'memory_total' in metrics:
            self.gpu_memory_total.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(
                metrics['memory_total']
            )
        
        if 'temperature' in metrics:
            self.gpu_temperature.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(
                metrics['temperature']
            )
        
        if 'power' in metrics:
            self.gpu_power.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(
                metrics['power']
            )
    
    def observe_inference(self, model_name: str, gpu_id: str, duration: float):
        """Observe GPU inference time."""
        self.gpu_inference_time.labels(
            model_name=model_name,
            gpu_id=gpu_id
        ).observe(duration)


class QueueMetrics:
    """Prometheus metrics for queue depth and processing."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None, service_name: str = "default"):
        self.registry = registry
        self.service_name = service_name
        
        # Queue depth (number of items waiting)
        self.queue_depth = Gauge(
            f'{service_name}_queue_depth',
            'Number of items in queue',
            ['queue_name', 'queue_type'],
            registry=registry
        )
        
        # Queue processing time
        self.queue_processing_time = Histogram(
            f'{service_name}_queue_processing_time_seconds',
            'Time to process queue item',
            ['queue_name', 'status'],
            registry=registry
        )
        
        # Queue items processed
        self.queue_items_processed = Counter(
            f'{service_name}_queue_items_processed_total',
            'Total items processed from queue',
            ['queue_name', 'status'],
            registry=registry
        )
        
        # Queue items added
        self.queue_items_added = Counter(
            f'{service_name}_queue_items_added_total',
            'Total items added to queue',
            ['queue_name'],
            registry=registry
        )
        
        # Queue wait time (time item spent waiting in queue)
        self.queue_wait_time = Histogram(
            f'{service_name}_queue_wait_time_seconds',
            'Time items wait in queue before processing',
            ['queue_name'],
            registry=registry
        )
    
    def set_queue_depth(self, queue_name: str, queue_type: str, depth: int):
        """Set current queue depth."""
        self.queue_depth.labels(
            queue_name=queue_name,
            queue_type=queue_type
        ).set(depth)
    
    def observe_processing(self, queue_name: str, duration: float, status: str = "success"):
        """Observe queue item processing time."""
        self.queue_processing_time.labels(
            queue_name=queue_name,
            status=status
        ).observe(duration)
        
        self.queue_items_processed.labels(
            queue_name=queue_name,
            status=status
        ).inc()
    
    def record_item_added(self, queue_name: str):
        """Record that an item was added to the queue."""
        self.queue_items_added.labels(queue_name=queue_name).inc()
    
    def observe_wait_time(self, queue_name: str, wait_time: float):
        """Observe time an item waited in queue."""
        self.queue_wait_time.labels(queue_name=queue_name).observe(wait_time)


class ServiceMetrics:
    """Prometheus metrics for service-level performance."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None, service_name: str = "default"):
        self.registry = registry
        self.service_name = service_name
        
        # Service memory usage
        self.memory_usage = Gauge(
            f'{service_name}_memory_usage_bytes',
            'Service memory usage in bytes',
            registry=registry
        )
        
        # Service memory RSS (Resident Set Size)
        self.memory_rss = Gauge(
            f'{service_name}_memory_rss_bytes',
            'Service RSS memory in bytes',
            registry=registry
        )
        
        # Service CPU usage percentage
        self.cpu_usage = Gauge(
            f'{service_name}_cpu_usage_percent',
            'Service CPU usage percentage',
            registry=registry
        )
        
        # Service thread count
        self.thread_count = Gauge(
            f'{service_name}_thread_count',
            'Number of active threads',
            registry=registry
        )
        
        # Service uptime
        self.uptime = Gauge(
            f'{service_name}_uptime_seconds',
            'Service uptime in seconds',
            registry=registry
        )
    
    def update_memory_usage(self, memory_bytes: int, rss_bytes: Optional[int] = None):
        """Update service memory usage metrics."""
        self.memory_usage.set(memory_bytes)
        if rss_bytes is not None:
            self.memory_rss.set(rss_bytes)
    
    def update_cpu_usage(self, cpu_percent: float):
        """Update service CPU usage metric."""
        self.cpu_usage.set(cpu_percent)
    
    def set_thread_count(self, count: int):
        """Set thread count metric."""
        self.thread_count.set(count)
    
    def set_uptime(self, seconds: float):
        """Set service uptime metric."""
        self.uptime.set(seconds)


class PerformanceMetrics:
    """Comprehensive performance metrics aggregator."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None, service_name: str = "default"):
        self.registry = registry
        self.service_name = service_name
        
        self.database = DatabaseMetrics(registry=registry, service_name=service_name)
        self.gpu = GPUMetrics(registry=registry, service_name=service_name)
        self.queue = QueueMetrics(registry=registry, service_name=service_name)
        self.service = ServiceMetrics(registry=registry, service_name=service_name)
        
        # Overall service response time by endpoint
        self.response_time = Histogram(
            f'{service_name}_response_time_seconds',
            'Service response time by endpoint',
            ['endpoint', 'method', 'status'],
            registry=registry
        )
        
        # Request throughput
        self.request_throughput = Counter(
            f'{service_name}_requests_total',
            'Total requests by endpoint',
            ['endpoint', 'method', 'status'],
            registry=registry
        )
    
    def observe_response(self, endpoint: str, method: str, status: int, duration: float):
        """Observe service response time."""
        self.response_time.labels(
            endpoint=endpoint,
            method=method,
            status=str(status)
        ).observe(duration)
        
        self.request_throughput.labels(
            endpoint=endpoint,
            method=method,
            status=str(status)
        ).inc()
