#!/usr/bin/env python3
"""
GPU Monitoring Script - Collects GPU metrics and exports to Prometheus.

This script monitors GPU utilization, memory, temperature, and power usage
and updates Prometheus metrics for bottleneck identification.
"""
import os
import sys
import time
import logging
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

try:
    from prometheus_client import start_http_server, Gauge, Histogram
    from june_metrics import GPUMetrics, CollectorRegistry
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    print("Make sure prometheus-client and june-metrics are installed")
    sys.exit(1)

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False
    print("Warning: pynvml not available. GPU monitoring will be limited.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
registry = CollectorRegistry()
gpu_metrics = GPUMetrics(registry=registry, service_name="gpu_monitor")

# Additional metrics for monitoring script itself
gpu_count = Gauge('gpu_count', 'Number of GPUs detected', registry=registry)
monitoring_errors = Gauge('gpu_monitoring_errors_total', 'Total GPU monitoring errors', registry=registry)


def init_nvml():
    """Initialize NVIDIA Management Library."""
    if not NVML_AVAILABLE:
        logger.warning("pynvml not available, cannot monitor GPU")
        return False
    
    try:
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        logger.info(f"Initialized NVML, found {device_count} GPU(s)")
        gpu_count.set(device_count)
        return True
    except Exception as e:
        logger.error(f"Failed to initialize NVML: {e}")
        return False


def get_gpu_metrics(gpu_id):
    """Get metrics for a specific GPU.
    
    Returns:
        Dictionary with GPU metrics or None if unavailable
    """
    if not NVML_AVAILABLE:
        return None
    
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
        
        # Get GPU name
        gpu_name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
        
        # Get utilization
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        utilization = util.gpu
        
        # Get memory info
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        memory_used = mem_info.used
        memory_total = mem_info.total
        
        # Get temperature
        try:
            temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        except:
            temperature = None
        
        # Get power usage
        try:
            power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # Convert mW to W
        except:
            power = None
        
        return {
            'gpu_id': str(gpu_id),
            'gpu_name': gpu_name,
            'utilization': utilization,
            'memory_used': memory_used,
            'memory_total': memory_total,
            'temperature': temperature,
            'power': power
        }
    except Exception as e:
        logger.error(f"Error getting GPU {gpu_id} metrics: {e}")
        monitoring_errors.inc()
        return None


def monitor_loop(interval=5):
    """Main monitoring loop."""
    if not init_nvml():
        logger.error("Cannot start monitoring without NVML")
        return
    
    device_count = pynvml.nvmlDeviceGetCount()
    logger.info(f"Starting GPU monitoring for {device_count} GPU(s), updating every {interval}s")
    
    while True:
        try:
            for gpu_id in range(device_count):
                metrics = get_gpu_metrics(gpu_id)
                if metrics:
                    gpu_metrics.update_gpu_metrics(
                        gpu_id=metrics['gpu_id'],
                        gpu_name=metrics['gpu_name'],
                        metrics={
                            'utilization': metrics['utilization'],
                            'memory_used': metrics['memory_used'],
                            'memory_total': metrics['memory_total'],
                            'temperature': metrics['temperature'],
                            'power': metrics['power']
                        }
                    )
            
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Stopping GPU monitoring")
            break
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            monitoring_errors.inc()
            time.sleep(interval)


def main():
    """Main entry point."""
    # Get configuration from environment
    metrics_port = int(os.getenv("GPU_MONITOR_PORT", "9101"))
    update_interval = int(os.getenv("GPU_MONITOR_INTERVAL", "5"))
    
    # Start Prometheus metrics server
    try:
        start_http_server(metrics_port, registry=registry)
        logger.info(f"Started GPU monitoring metrics server on port {metrics_port}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
        sys.exit(1)
    
    # Start monitoring loop
    monitor_loop(interval=update_interval)


if __name__ == "__main__":
    main()
