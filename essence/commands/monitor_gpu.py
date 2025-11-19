"""
GPU monitoring command - Collects GPU metrics and exports to Prometheus.

Usage:
    poetry run -m essence monitor-gpu [--port PORT] [--interval INTERVAL]

This command monitors GPU utilization, memory, temperature, and power usage
and updates Prometheus metrics for bottleneck identification.
"""
import argparse
import logging
import os
import sys
import time
from typing import Optional

try:
    from prometheus_client import start_http_server, Gauge, CollectorRegistry
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Don't exit here - let the command handle it gracefully

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

from essence.command import Command

logger = logging.getLogger(__name__)


class MonitorGpuCommand(Command):
    """
    Command for monitoring GPU metrics and exporting to Prometheus.
    
    Continuously monitors GPU utilization, memory usage, temperature, power
    consumption, and other metrics using NVIDIA Management Library (NVML).
    Exports metrics to Prometheus format for integration with monitoring systems.
    
    Provides real-time GPU health monitoring essential for large model inference
    workloads. Metrics are exposed via HTTP endpoint for Prometheus scraping.
    """
    
    def __init__(self, args: argparse.Namespace):
        """
        Initialize command with parsed arguments.
        
        Args:
            args: Parsed command-line arguments containing monitoring configuration
        """
        super().__init__(args)
        self._metrics_port = None
        self._update_interval = None
        self._registry = None
        self._metrics = {}
        self._monitoring_active = False
    
    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.
        
        Returns:
            Command name: "monitor-gpu"
        """
        return "monitor-gpu"
    
    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.
        
        Returns:
            Description of what this command does
        """
        return "Monitor GPU metrics and export to Prometheus"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.
        
        Configures Prometheus metrics server port and update interval for GPU monitoring.
        
        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("GPU_MONITOR_PORT", "9101")),
            help="Port for Prometheus metrics server (default: 9101)"
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=int(os.getenv("GPU_MONITOR_INTERVAL", "5")),
            help="Update interval in seconds (default: 5)"
        )
    
    def init(self) -> None:
        """
        Initialize GPU monitoring.
        
        Validates NVML availability, sets up signal handlers, creates Prometheus
        metrics registry, defines all GPU metrics (utilization, memory, temperature,
        power), and initializes NVML library. Must be called before run().
        
        Raises:
            RuntimeError: If pynvml is not available or NVML initialization fails
        """
        if not NVML_AVAILABLE:
            logger.warning("pynvml not available. GPU monitoring will be limited.")
            raise RuntimeError("pynvml not available. Install with: pip install pynvml")
        
        if not PROMETHEUS_AVAILABLE:
            raise RuntimeError("prometheus-client not available. Install with: pip install prometheus-client")
        
        # Setup signal handlers for graceful shutdown
        self.setup_signal_handlers()
        
        self._metrics_port = self.args.port
        self._update_interval = self.args.interval
        
        # Create Prometheus metrics registry
        self._registry = CollectorRegistry()
        
        # Create GPU metrics
        service_name = "gpu_monitor"
        self._metrics['gpu_utilization'] = Gauge(
            f'{service_name}_gpu_utilization_percent',
            'GPU utilization percentage',
            ['gpu_id', 'gpu_name'],
            registry=self._registry
        )
        self._metrics['gpu_memory_used'] = Gauge(
            f'{service_name}_gpu_memory_used_bytes',
            'GPU memory used in bytes',
            ['gpu_id', 'gpu_name'],
            registry=self._registry
        )
        self._metrics['gpu_memory_total'] = Gauge(
            f'{service_name}_gpu_memory_total_bytes',
            'GPU memory total in bytes',
            ['gpu_id', 'gpu_name'],
            registry=self._registry
        )
        self._metrics['gpu_temperature'] = Gauge(
            f'{service_name}_gpu_temperature_celsius',
            'GPU temperature in Celsius',
            ['gpu_id', 'gpu_name'],
            registry=self._registry
        )
        self._metrics['gpu_power'] = Gauge(
            f'{service_name}_gpu_power_watts',
            'GPU power usage in watts',
            ['gpu_id', 'gpu_name'],
            registry=self._registry
        )
        self._metrics['gpu_count'] = Gauge(
            'gpu_count',
            'Number of GPUs detected',
            registry=self._registry
        )
        self._metrics['monitoring_errors'] = Gauge(
            'gpu_monitoring_errors_total',
            'Total GPU monitoring errors',
            registry=self._registry
        )
        
        # Initialize NVML
        try:
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            logger.info(f"Initialized NVML, found {device_count} GPU(s)")
            self._metrics['gpu_count'].set(device_count)
        except Exception as e:
            logger.error(f"Failed to initialize NVML: {e}")
            raise
    
    def _get_gpu_metrics(self, gpu_id: int) -> Optional[dict]:
        """Get metrics for a specific GPU.
        
        Returns:
            Dictionary with GPU metrics or None if unavailable
        """
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
            self._metrics['monitoring_errors'].inc()
            return None
    
    def run(self) -> None:
        """
        Run the GPU monitoring loop.
        
        Starts the Prometheus HTTP metrics server and begins continuous GPU
        monitoring. Updates metrics at the configured interval until stopped
        (via signal handler). This method blocks until monitoring is stopped.
        
        Monitors all detected GPUs and exports metrics including utilization,
        memory usage, temperature, and power consumption.
        """
        # Start Prometheus metrics server
        try:
            start_http_server(self._metrics_port, registry=self._registry)
            logger.info(f"Started GPU monitoring metrics server on port {self._metrics_port}")
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
            raise
        
        device_count = pynvml.nvmlDeviceGetCount()
        logger.info(f"Starting GPU monitoring for {device_count} GPU(s), updating every {self._update_interval}s")
        
        self._monitoring_active = True
        
        try:
            while self._monitoring_active:
                try:
                    for gpu_id in range(device_count):
                        metrics = self._get_gpu_metrics(gpu_id)
                        if metrics:
                            gpu_id_str = metrics['gpu_id']
                            gpu_name = metrics['gpu_name']
                            
                            # Update GPU metrics
                            if metrics.get('utilization') is not None:
                                self._metrics['gpu_utilization'].labels(
                                    gpu_id=gpu_id_str, gpu_name=gpu_name
                                ).set(metrics['utilization'])
                            
                            if metrics.get('memory_used') is not None:
                                self._metrics['gpu_memory_used'].labels(
                                    gpu_id=gpu_id_str, gpu_name=gpu_name
                                ).set(metrics['memory_used'])
                            
                            if metrics.get('memory_total') is not None:
                                self._metrics['gpu_memory_total'].labels(
                                    gpu_id=gpu_id_str, gpu_name=gpu_name
                                ).set(metrics['memory_total'])
                            
                            if metrics.get('temperature') is not None:
                                self._metrics['gpu_temperature'].labels(
                                    gpu_id=gpu_id_str, gpu_name=gpu_name
                                ).set(metrics['temperature'])
                            
                            if metrics.get('power') is not None:
                                self._metrics['gpu_power'].labels(
                                    gpu_id=gpu_id_str, gpu_name=gpu_name
                                ).set(metrics['power'])
                    
                    time.sleep(self._update_interval)
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                    self._metrics['monitoring_errors'].inc()
                    time.sleep(self._update_interval)
        except KeyboardInterrupt:
            logger.info("Stopping GPU monitoring")
            self._monitoring_active = False
        finally:
            self._monitoring_active = False
    
    def cleanup(self) -> None:
        """
        Clean up GPU monitoring resources.
        
        Stops the monitoring loop and shuts down NVML library. Releases all
        GPU monitoring resources including Prometheus metrics registry and
        HTTP server connections. Should be called when the command is finished.
        """
        self._monitoring_active = False
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlShutdown()
                logger.info("NVML shutdown complete")
            except Exception as e:
                logger.warning(f"Error shutting down NVML: {e}")
