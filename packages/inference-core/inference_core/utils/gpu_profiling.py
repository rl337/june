"""
GPU profiling utilities for monitoring GPU utilization and memory usage.
"""
import logging
from typing import Dict, Any, Optional
import time

logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available, GPU profiling will be limited")

try:
    import subprocess
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False


class GPUProfiler:
    """Profiles GPU memory usage and utilization."""
    
    def __init__(self, device: Optional[str] = None):
        """Initialize GPU profiler.
        
        Args:
            device: CUDA device ID (e.g., "cuda:0") or None for default
        """
        self.device = device or "cuda:0" if TORCH_AVAILABLE and torch.cuda.is_available() else None
        self.has_gpu = TORCH_AVAILABLE and torch.cuda.is_available() if self.device else False
        
    def get_memory_info(self) -> Dict[str, float]:
        """Get current GPU memory usage in MB.
        
        Returns:
            Dictionary with 'allocated_mb', 'reserved_mb', 'free_mb', 'total_mb'
        """
        if not self.has_gpu:
            return {
                "allocated_mb": 0.0,
                "reserved_mb": 0.0,
                "free_mb": 0.0,
                "total_mb": 0.0,
            }
        
        try:
            device_id = int(self.device.split(":")[-1]) if ":" in self.device else 0
            allocated = torch.cuda.memory_allocated(device_id) / (1024 ** 2)  # MB
            reserved = torch.cuda.memory_reserved(device_id) / (1024 ** 2)  # MB
            total = torch.cuda.get_device_properties(device_id).total_memory / (1024 ** 2)  # MB
            free = total - reserved
            
            return {
                "allocated_mb": allocated,
                "reserved_mb": reserved,
                "free_mb": free,
                "total_mb": total,
            }
        except Exception as e:
            logger.error(f"Failed to get GPU memory info: {e}")
            return {
                "allocated_mb": 0.0,
                "reserved_mb": 0.0,
                "free_mb": 0.0,
                "total_mb": 0.0,
            }
    
    def get_utilization(self) -> Dict[str, float]:
        """Get GPU utilization percentage using nvidia-smi.
        
        Returns:
            Dictionary with 'gpu_utilization', 'memory_utilization'
        """
        if not self.has_gpu:
            return {
                "gpu_utilization": 0.0,
                "memory_utilization": 0.0,
            }
        
        try:
            # Use nvidia-smi to get utilization
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                values = result.stdout.strip().split(", ")
                if len(values) == 2:
                    return {
                        "gpu_utilization": float(values[0]),
                        "memory_utilization": float(values[1]),
                    }
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
            logger.debug(f"Failed to get GPU utilization via nvidia-smi: {e}")
        
        return {
            "gpu_utilization": 0.0,
            "memory_utilization": 0.0,
        }
    
    def reset_peak_stats(self) -> None:
        """Reset peak memory statistics."""
        if self.has_gpu:
            try:
                device_id = int(self.device.split(":")[-1]) if ":" in self.device else 0
                torch.cuda.reset_peak_memory_stats(device_id)
            except Exception as e:
                logger.error(f"Failed to reset peak stats: {e}")
    
    def get_peak_memory(self) -> float:
        """Get peak memory allocated in MB."""
        if not self.has_gpu:
            return 0.0
        
        try:
            device_id = int(self.device.split(":")[-1]) if ":" in self.device else 0
            return torch.cuda.max_memory_allocated(device_id) / (1024 ** 2)  # MB
        except Exception as e:
            logger.error(f"Failed to get peak memory: {e}")
            return 0.0
    
    def profile_operation(self, operation_name: str, operation_func, *args, **kwargs) -> Dict[str, Any]:
        """Profile a GPU operation and return metrics.
        
        Args:
            operation_name: Name of the operation being profiled
            operation_func: Function to profile
            *args, **kwargs: Arguments to pass to operation_func
            
        Returns:
            Dictionary with operation metrics including timing and memory usage
        """
        if not self.has_gpu:
            # Run operation without profiling
            start_time = time.time()
            result = operation_func(*args, **kwargs)
            duration = time.time() - start_time
            return {
                "operation": operation_name,
                "duration_seconds": duration,
                "memory_before_mb": 0.0,
                "memory_after_mb": 0.0,
                "memory_delta_mb": 0.0,
                "peak_memory_mb": 0.0,
            }
        
        # Reset peak stats before operation
        self.reset_peak_stats()
        
        # Get memory before
        memory_before = self.get_memory_info()
        
        # Run operation
        start_time = time.time()
        result = operation_func(*args, **kwargs)
        duration = time.time() - start_time
        
        # Get memory after
        memory_after = self.get_memory_info()
        peak_memory = self.get_peak_memory()
        
        return {
            "operation": operation_name,
            "duration_seconds": duration,
            "memory_before_mb": memory_before["allocated_mb"],
            "memory_after_mb": memory_after["allocated_mb"],
            "memory_delta_mb": memory_after["allocated_mb"] - memory_before["allocated_mb"],
            "peak_memory_mb": peak_memory,
            "result": result,
        }
    
    def get_full_report(self) -> Dict[str, Any]:
        """Get a full GPU profiling report.
        
        Returns:
            Dictionary with complete GPU status including memory and utilization
        """
        memory_info = self.get_memory_info()
        utilization = self.get_utilization()
        
        return {
            "device": self.device,
            "has_gpu": self.has_gpu,
            "memory": memory_info,
            "utilization": utilization,
            "peak_memory_mb": self.get_peak_memory(),
        }
