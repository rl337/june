"""System monitoring module for admin dashboard."""
import os
import logging
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Service URLs from environment variables
SERVICE_URLS = {
    "gateway": os.getenv("GATEWAY_URL", "http://gateway:8000"),
    "inference-api": os.getenv("INFERENCE_API_URL", "http://inference-api:8001"),
    "stt": os.getenv("STT_URL", "http://stt:8002"),
    "tts": os.getenv("TTS_URL", "http://tts:8003"),
    "telegram": os.getenv("TELEGRAM_URL", "http://telegram:8080"),
    "postgres": os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@postgres:5432/conversations"),
    "minio": os.getenv("MINIO_URL", "http://minio:9000"),
}

# Prometheus URL
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

# Grafana URL (optional)
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")

# Loki URL (optional, for logs)
LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")


def check_service_health(service_name: str, service_url: str) -> Dict[str, Any]:
    """
    Check health of a service by calling its /health endpoint.
    
    Args:
        service_name: Name of the service
        service_url: Base URL of the service
        
    Returns:
        Dictionary with health status, response time, and details
    """
    try:
        start_time = datetime.now()
        response = httpx.get(f"{service_url}/health", timeout=5.0)
        response_time = (datetime.now() - start_time).total_seconds() * 1000  # milliseconds
        
        if response.status_code == 200:
            health_data = response.json()
            status = health_data.get("status", "unknown")
            return {
                "service": service_name,
                "status": "healthy" if status == "healthy" else "unhealthy",
                "response_time_ms": round(response_time, 2),
                "details": health_data,
                "last_check": datetime.now().isoformat(),
                "error": None
            }
        else:
            return {
                "service": service_name,
                "status": "unhealthy",
                "response_time_ms": round(response_time, 2),
                "details": {"http_status": response.status_code},
                "last_check": datetime.now().isoformat(),
                "error": f"HTTP {response.status_code}"
            }
    except httpx.TimeoutException:
        return {
            "service": service_name,
            "status": "unreachable",
            "response_time_ms": None,
            "details": {},
            "last_check": datetime.now().isoformat(),
            "error": "Connection timeout"
        }
    except Exception as e:
        logger.error(f"Failed to check health for {service_name}: {e}", exc_info=True)
        return {
            "service": service_name,
            "status": "error",
            "response_time_ms": None,
            "details": {},
            "last_check": datetime.now().isoformat(),
            "error": str(e)
        }


def get_all_services_health() -> Dict[str, Any]:
    """
    Get health status for all services.
    
    Returns:
        Dictionary with services list and summary
    """
    services = []
    healthy_count = 0
    unhealthy_count = 0
    unreachable_count = 0
    
    # Check each service
    for service_name, service_url in SERVICE_URLS.items():
        # Skip postgres and minio as they don't have /health endpoints
        if service_name in ["postgres", "minio"]:
            continue
            
        health = check_service_health(service_name, service_url)
        services.append(health)
        
        if health["status"] == "healthy":
            healthy_count += 1
        elif health["status"] == "unreachable":
            unreachable_count += 1
        else:
            unhealthy_count += 1
    
    # Check PostgreSQL (via connection test)
    postgres_health = check_postgres_health()
    services.append(postgres_health)
    if postgres_health["status"] == "healthy":
        healthy_count += 1
    else:
        unhealthy_count += 1
    
    # Check MinIO (via health endpoint if available)
    minio_health = check_minio_health()
    services.append(minio_health)
    if minio_health["status"] == "healthy":
        healthy_count += 1
    else:
        unhealthy_count += 1
    
    return {
        "services": services,
        "summary": {
            "total": len(services),
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "unreachable": unreachable_count,
            "timestamp": datetime.now().isoformat()
        }
    }


def check_postgres_health() -> Dict[str, Any]:
    """Check PostgreSQL health by attempting a connection."""
    try:
        import psycopg2
        from urllib.parse import urlparse
        
        parsed = urlparse(SERVICE_URLS["postgres"])
        conn = psycopg2.connect(
            host=parsed.hostname or "postgres",
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/") or "conversations",
            user=parsed.username or "postgres",
            password=parsed.password or "postgres",
            connect_timeout=3
        )
        conn.close()
        
        return {
            "service": "postgres",
            "status": "healthy",
            "response_time_ms": None,
            "details": {"database": parsed.path.lstrip("/") or "conversations"},
            "last_check": datetime.now().isoformat(),
            "error": None
        }
    except Exception as e:
        logger.error(f"Failed to check PostgreSQL health: {e}", exc_info=True)
        return {
            "service": "postgres",
            "status": "unhealthy",
            "response_time_ms": None,
            "details": {},
            "last_check": datetime.now().isoformat(),
            "error": str(e)
        }


def check_minio_health() -> Dict[str, Any]:
    """Check MinIO health."""
    try:
        response = httpx.get(f"{SERVICE_URLS['minio']}/minio/health/live", timeout=5.0)
        if response.status_code == 200:
            return {
                "service": "minio",
                "status": "healthy",
                "response_time_ms": None,
                "details": {},
                "last_check": datetime.now().isoformat(),
                "error": None
            }
        else:
            return {
                "service": "minio",
                "status": "unhealthy",
                "response_time_ms": None,
                "details": {"http_status": response.status_code},
                "last_check": datetime.now().isoformat(),
                "error": f"HTTP {response.status_code}"
            }
    except Exception as e:
        logger.error(f"Failed to check MinIO health: {e}", exc_info=True)
        return {
            "service": "minio",
            "status": "unreachable",
            "response_time_ms": None,
            "details": {},
            "last_check": datetime.now().isoformat(),
            "error": str(e)
        }


def get_prometheus_metrics(query: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Query Prometheus for metrics.
    
    Args:
        query: PromQL query string
        start_time: Start time for range query (optional)
        end_time: End time for range query (optional)
        
    Returns:
        Dictionary with metric data
    """
    try:
        if start_time and end_time:
            # Range query
            params = {
                "query": query,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "step": "15s"
            }
            url = f"{PROMETHEUS_URL}/api/v1/query_range"
        else:
            # Instant query
            params = {"query": query}
            url = f"{PROMETHEUS_URL}/api/v1/query"
        
        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to query Prometheus: {e}", exc_info=True)
        return {"error": str(e)}


def get_service_metrics(service_name: str) -> Dict[str, Any]:
    """
    Get metrics for a specific service from Prometheus.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Dictionary with service metrics
    """
    metrics = {}
    
    # CPU usage (if available from node-exporter)
    cpu_query = f'100 - (avg(irate(node_cpu_seconds_total{{mode="idle", instance=~".*{service_name}.*"}}[5m])) * 100)'
    cpu_result = get_prometheus_metrics(cpu_query)
    if "data" in cpu_result and "result" in cpu_result["data"]:
        metrics["cpu_usage_percent"] = cpu_result["data"]["result"][0].get("value", [None, None])[1] if cpu_result["data"]["result"] else None
    
    # Memory usage (if available)
    memory_query = f'node_memory_MemTotal_bytes{{instance=~".*{service_name}.*"}} - node_memory_MemAvailable_bytes{{instance=~".*{service_name}.*"}}'
    memory_result = get_prometheus_metrics(memory_query)
    if "data" in memory_result and "result" in memory_result["data"]:
        metrics["memory_usage_bytes"] = memory_result["data"]["result"][0].get("value", [None, None])[1] if memory_result["data"]["result"] else None
    
    # Request rate (from gateway metrics)
    if service_name == "gateway":
        request_rate_query = 'rate(gateway_requests_total[5m])'
        request_rate_result = get_prometheus_metrics(request_rate_query)
        if "data" in request_rate_result and "result" in request_rate_result["data"]:
            metrics["request_rate_per_second"] = request_rate_result["data"]["result"][0].get("value", [None, None])[1] if request_rate_result["data"]["result"] else None
    
    # Error rate
    error_rate_query = f'rate(gateway_requests_total{{status=~"5..", endpoint=~".*{service_name}.*"}}[5m])'
    error_rate_result = get_prometheus_metrics(error_rate_query)
    if "data" in error_rate_result and "result" in error_rate_result["data"]:
        metrics["error_rate_per_second"] = error_rate_result["data"]["result"][0].get("value", [None, None])[1] if error_rate_result["data"]["result"] else None
    
    return {
        "service": service_name,
        "metrics": metrics,
        "timestamp": datetime.now().isoformat()
    }


def get_all_metrics() -> Dict[str, Any]:
    """
    Get metrics for all services.
    
    Returns:
        Dictionary with metrics for all services
    """
    services_metrics = []
    
    for service_name in SERVICE_URLS.keys():
        service_metrics = get_service_metrics(service_name)
        services_metrics.append(service_metrics)
    
    return {
        "services": services_metrics,
        "timestamp": datetime.now().isoformat()
    }


def get_recent_errors() -> List[Dict[str, Any]]:
    """
    Get recent errors and warnings from services.
    
    Returns:
        List of error/warning entries
    """
    # This would typically query logs from Loki or a log aggregation service
    # For now, return a placeholder structure
    return [
        {
            "timestamp": datetime.now().isoformat(),
            "service": "gateway",
            "level": "error",
            "message": "Sample error message",
            "details": {}
        }
    ]


def get_service_uptime(service_name: str) -> Optional[Dict[str, Any]]:
    """
    Get service uptime information.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Dictionary with uptime information
    """
    # Query Prometheus for service start time or uptime metric
    uptime_query = f'process_start_time_seconds{{job="{service_name}"}}'
    uptime_result = get_prometheus_metrics(uptime_query)
    
    if "data" in uptime_result and "result" in uptime_result["data"] and uptime_result["data"]["result"]:
        start_timestamp = float(uptime_result["data"]["result"][0].get("value", [None, None])[1])
        start_time = datetime.fromtimestamp(start_timestamp)
        uptime_delta = datetime.now() - start_time
        
        return {
            "service": service_name,
            "start_time": start_time.isoformat(),
            "uptime_seconds": uptime_delta.total_seconds(),
            "uptime_formatted": str(uptime_delta).split('.')[0]  # Remove microseconds
        }
    
    return None
