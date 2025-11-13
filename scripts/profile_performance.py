#!/usr/bin/env python3
"""
Performance Profiling Tool - Identifies CPU and memory hotspots.

This script profiles service performance to identify bottlenecks:
- CPU hotspots (functions using most CPU time)
- Memory hotspots (functions allocating most memory)
- Slow operations (operations taking longest time)
"""
import os
import sys
import time
import cProfile
import pstats
import io
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceProfiler:
    """Profiles application performance to identify bottlenecks."""
    
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.getenv("PROFILE_OUTPUT_DIR", "/tmp/profiles")
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self.profiler = cProfile.Profile()
    
    def profile_function(self, func, *args, **kwargs):
        """Profile a single function execution.
        
        Returns:
            Tuple of (result, stats_dict)
        """
        self.profiler.enable()
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
        finally:
            self.profiler.disable()
            duration = time.time() - start_time
        
        # Get stats
        stats = self._get_stats()
        
        return result, {
            'duration': duration,
            'stats': stats
        }
    
    def profile_code_block(self, code_block_name: str):
        """Context manager for profiling code blocks."""
        return ProfileContext(self, code_block_name)
    
    def _get_stats(self) -> Dict[str, Any]:
        """Get profiling statistics."""
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s)
        ps.sort_stats('cumulative')
        ps.print_stats(20)  # Top 20 functions
        
        stats_str = s.getvalue()
        
        # Parse stats to extract key metrics
        lines = stats_str.split('\n')
        top_functions = []
        
        for line in lines[5:25]:  # Skip header, get top functions
            if line.strip() and not line.startswith('ncalls'):
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        ncalls = parts[0]
                        tottime = float(parts[1])
                        cumtime = float(parts[2])
                        func_name = ' '.join(parts[4:]) if len(parts) > 4 else parts[3]
                        
                        top_functions.append({
                            'ncalls': ncalls,
                            'tottime': tottime,
                            'cumtime': cumtime,
                            'function': func_name
                        })
                    except (ValueError, IndexError):
                        continue
        
        return {
            'top_functions': top_functions,
            'raw_stats': stats_str
        }
    
    def save_profile(self, name: str):
        """Save profile to file."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.prof"
        filepath = Path(self.output_dir) / filename
        
        self.profiler.dump_stats(str(filepath))
        logger.info(f"Saved profile to {filepath}")
        
        # Also save human-readable stats
        stats_file = filepath.with_suffix('.txt')
        with open(stats_file, 'w') as f:
            ps = pstats.Stats(self.profiler, stream=f)
            ps.sort_stats('cumulative')
            ps.print_stats()
        
        # Save JSON summary
        json_file = filepath.with_suffix('.json')
        stats = self._get_stats()
        with open(json_file, 'w') as f:
            json.dump({
                'timestamp': timestamp,
                'name': name,
                'top_functions': stats['top_functions']
            }, f, indent=2)
        
        return filepath
    
    def reset(self):
        """Reset profiler state."""
        self.profiler = cProfile.Profile()


class ProfileContext:
    """Context manager for profiling code blocks."""
    
    def __init__(self, profiler: PerformanceProfiler, name: str):
        self.profiler = profiler
        self.name = name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.profiler.profiler.enable()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.profiler.profiler.disable()
        duration = time.time() - self.start_time
        
        logger.info(f"Profiled '{self.name}' in {duration:.3f}s")
        return False


def profile_service_startup(service_module_path: str):
    """Profile a service's startup process."""
    profiler = PerformanceProfiler()
    
    logger.info(f"Profiling service startup: {service_module_path}")
    
    # Import and profile service startup
    import importlib.util
    spec = importlib.util.spec_from_file_location("service", service_module_path)
    if spec is None:
        logger.error(f"Could not load service from {service_module_path}")
        return
    
    module = importlib.util.module_from_spec(spec)
    
    with profiler.profile_code_block("service_startup"):
        try:
            spec.loader.exec_module(module)
            # If service has a main function, call it
            if hasattr(module, 'main'):
                module.main()
        except Exception as e:
            logger.error(f"Error profiling service: {e}")
    
    profiler.save_profile("service_startup")


def main():
    """Main entry point for profiling tool."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Profile service performance")
    parser.add_argument("--service", help="Service module path to profile")
    parser.add_argument("--output-dir", help="Output directory for profiles")
    parser.add_argument("--function", help="Function to profile (if profiling specific function)")
    
    args = parser.parse_args()
    
    if args.service:
        profile_service_startup(args.service)
    else:
        logger.info("Use --service to profile a service, or import this module to use PerformanceProfiler")


if __name__ == "__main__":
    main()
