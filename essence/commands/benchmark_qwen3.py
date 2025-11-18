"""
Benchmark Qwen3 performance command - Performance benchmarking suite for Qwen3-30B-A3B model.

Usage:
    poetry run -m essence benchmark-qwen3 [--output-dir OUTPUT_DIR] [--iterations ITERATIONS]

This command measures:
- Tokens/second for text generation
- Latency for various request types (short, medium, long prompts)
- GPU memory usage
- Model loading time
- Throughput under load
"""
import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import statistics

try:
    import torch
    import psutil
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    DEPENDENCIES_AVAILABLE = False
    IMPORT_ERROR = str(e)

try:
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    from inference_core.strategies import InferenceRequest
    from inference_core.config import config
    INFERENCE_CORE_AVAILABLE = True
except ImportError:
    INFERENCE_CORE_AVAILABLE = False
    Qwen3LlmStrategy = None
    InferenceRequest = None
    config = None

from essence.command import Command

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""
    prompt_length: int
    prompt_type: str  # 'short', 'medium', 'long'
    latency_seconds: float
    tokens_generated: int
    tokens_per_second: float
    input_tokens: int
    output_tokens: int
    gpu_memory_allocated_mb: float
    gpu_memory_reserved_mb: float
    cpu_percent: float
    memory_mb: float
    success: bool
    error: Optional[str] = None


@dataclass
class ModelLoadMetrics:
    """Metrics for model loading."""
    load_time_seconds: float
    gpu_memory_after_load_mb: float
    cpu_memory_after_load_mb: float
    success: bool
    error: Optional[str] = None


@dataclass
class ThroughputMetrics:
    """Metrics for throughput under load."""
    concurrent_requests: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_time_seconds: float
    requests_per_second: float
    average_latency_seconds: float
    p50_latency_seconds: float
    p95_latency_seconds: float
    p99_latency_seconds: float
    min_latency_seconds: float
    max_latency_seconds: float


@dataclass
class PerformanceReport:
    """Complete performance report."""
    model_name: str
    device: str
    benchmark_timestamp: str
    model_load_metrics: ModelLoadMetrics
    latency_benchmarks: List[BenchmarkResult]
    throughput_benchmarks: List[ThroughputMetrics]
    summary: Dict


class GPUMonitor:
    """Monitor GPU memory usage."""
    
    def __init__(self):
        self.has_gpu = torch.cuda.is_available() if DEPENDENCIES_AVAILABLE else False
        self.device = None
        if self.has_gpu:
            self.device = torch.cuda.current_device()
    
    def get_memory_info(self) -> Tuple[float, float]:
        """Get GPU memory allocated and reserved in MB."""
        if not self.has_gpu:
            return 0.0, 0.0
        
        allocated = torch.cuda.memory_allocated(self.device) / (1024 ** 2)  # MB
        reserved = torch.cuda.memory_reserved(self.device) / (1024 ** 2)  # MB
        return allocated, reserved
    
    def reset_peak_stats(self):
        """Reset peak memory statistics."""
        if self.has_gpu:
            torch.cuda.reset_peak_memory_stats(self.device)
    
    def get_peak_memory(self) -> float:
        """Get peak memory usage in MB."""
        if not self.has_gpu:
            return 0.0
        return torch.cuda.max_memory_allocated(self.device) / (1024 ** 2)  # MB


def get_system_metrics() -> Tuple[float, float]:
    """Get CPU and system memory usage."""
    if not DEPENDENCIES_AVAILABLE:
        return 0.0, 0.0
    process = psutil.Process(os.getpid())
    cpu_percent = process.cpu_percent(interval=0.1)
    memory_mb = process.memory_info().rss / (1024 ** 2)  # MB
    return cpu_percent, memory_mb


def generate_test_prompts() -> Dict[str, List[str]]:
    """Generate test prompts of different lengths."""
    return {
        'short': [
            "Hello, how are you?",
            "What is the capital of France?",
            "Explain quantum computing in one sentence.",
            "Write a haiku about AI.",
            "What is 2+2?",
        ],
        'medium': [
            "Write a brief explanation of how neural networks work, including the concepts of forward propagation, backpropagation, and gradient descent.",
            "Explain the differences between supervised and unsupervised learning, and provide examples of each type of machine learning approach.",
            "Describe the transformer architecture and how it revolutionized natural language processing tasks.",
            "What are the key challenges in deploying machine learning models to production, and how can they be addressed?",
            "Explain the concept of transfer learning and how it can be used to improve model performance with limited data.",
        ],
        'long': [
            "Write a comprehensive guide to building a production-ready machine learning system. Include sections on data collection and preprocessing, model selection and training, evaluation metrics, deployment strategies, monitoring and maintenance, and scaling considerations. Provide code examples where appropriate.",
            "Explain in detail the evolution of large language models from early RNN architectures through transformers to modern models like GPT, BERT, and their successors. Discuss the key innovations at each stage, the trade-offs involved, and the impact on the field of AI.",
            "Create a detailed technical specification for a conversational AI system that can handle multi-turn conversations, maintain context, integrate with external APIs, and provide accurate, helpful responses. Include architecture diagrams, data flow descriptions, and implementation considerations.",
            "Describe a complete machine learning pipeline from raw data to deployed model, including data validation, feature engineering, model training with hyperparameter tuning, model validation, A/B testing, continuous monitoring, and retraining strategies.",
            "Write an in-depth analysis of the challenges and solutions for running large language models efficiently, covering topics such as model quantization, distillation, pruning, efficient attention mechanisms, distributed inference, and hardware optimization.",
        ]
    }


def measure_model_loading(strategy: Qwen3LlmStrategy, gpu_monitor: GPUMonitor) -> ModelLoadMetrics:
    """Measure model loading time and resource usage."""
    logger.info("Measuring model loading time...")
    
    start_time = time.time()
    gpu_monitor.reset_peak_stats()
    
    try:
        strategy.warmup()
        load_time = time.time() - start_time
        
        allocated, reserved = gpu_monitor.get_memory_info()
        cpu_percent, memory_mb = get_system_metrics()
        
        logger.info(f"Model loaded in {load_time:.2f} seconds")
        logger.info(f"GPU memory after load: {allocated:.2f} MB allocated, {reserved:.2f} MB reserved")
        
        return ModelLoadMetrics(
            load_time_seconds=load_time,
            gpu_memory_after_load_mb=allocated,
            cpu_memory_after_load_mb=memory_mb,
            success=True
        )
    except Exception as e:
        load_time = time.time() - start_time
        logger.error(f"Model loading failed: {e}")
        return ModelLoadMetrics(
            load_time_seconds=load_time,
            gpu_memory_after_load_mb=0.0,
            cpu_memory_after_load_mb=0.0,
            success=False,
            error=str(e)
        )


def run_single_benchmark(
    strategy: Qwen3LlmStrategy,
    prompt: str,
    prompt_type: str,
    gpu_monitor: GPUMonitor,
    max_tokens: int = 256
) -> BenchmarkResult:
    """Run a single benchmark with a given prompt."""
    try:
        # Get baseline metrics
        allocated_before, reserved_before = gpu_monitor.get_memory_info()
        cpu_before, memory_before = get_system_metrics()
        
        # Create request
        request = InferenceRequest(
            payload={
                "prompt": prompt,
                "params": {
                    "temperature": 0.7,
                    "max_tokens": max_tokens,
                    "top_p": 0.9,
                }
            },
            metadata={}
        )
        
        # Measure inference time
        start_time = time.time()
        response = strategy.infer(request)
        latency = time.time() - start_time
        
        # Get metrics after inference
        allocated_after, reserved_after = gpu_monitor.get_memory_info()
        cpu_after, memory_after = get_system_metrics()
        
        # Extract token counts
        if isinstance(response.payload, dict):
            output_tokens = response.payload.get("tokens", 0)
        else:
            output_tokens = 0
        
        input_tokens = response.metadata.get("input_tokens", len(prompt.split()))
        
        # Calculate tokens per second
        tokens_per_second = output_tokens / latency if latency > 0 else 0
        
        return BenchmarkResult(
            prompt_length=len(prompt),
            prompt_type=prompt_type,
            latency_seconds=latency,
            tokens_generated=output_tokens,
            tokens_per_second=tokens_per_second,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            gpu_memory_allocated_mb=allocated_after,
            gpu_memory_reserved_mb=reserved_after,
            cpu_percent=cpu_after,
            memory_mb=memory_after,
            success=True
        )
    except Exception as e:
        logger.error(f"Benchmark failed for prompt type {prompt_type}: {e}")
        return BenchmarkResult(
            prompt_length=len(prompt),
            prompt_type=prompt_type,
            latency_seconds=0.0,
            tokens_generated=0,
            tokens_per_second=0.0,
            input_tokens=0,
            output_tokens=0,
            gpu_memory_allocated_mb=0.0,
            gpu_memory_reserved_mb=0.0,
            cpu_percent=0.0,
            memory_mb=0.0,
            success=False,
            error=str(e)
        )


def run_latency_benchmarks(
    strategy: Qwen3LlmStrategy,
    gpu_monitor: GPUMonitor,
    iterations: int = 3
) -> List[BenchmarkResult]:
    """Run latency benchmarks for different prompt types."""
    logger.info(f"Running latency benchmarks ({iterations} iterations per prompt type)...")
    
    prompts = generate_test_prompts()
    results = []
    
    for prompt_type, prompt_list in prompts.items():
        logger.info(f"Testing {prompt_type} prompts...")
        for prompt in prompt_list:
            for i in range(iterations):
                logger.info(f"  Iteration {i+1}/{iterations}: {prompt[:50]}...")
                result = run_single_benchmark(strategy, prompt, prompt_type, gpu_monitor)
                results.append(result)
                
                if result.success:
                    logger.info(
                        f"    Latency: {result.latency_seconds:.3f}s, "
                        f"Tokens: {result.tokens_generated}, "
                        f"Tokens/s: {result.tokens_per_second:.2f}"
                    )
                else:
                    logger.warning(f"    Failed: {result.error}")
    
    return results


def run_throughput_benchmark(
    strategy: Qwen3LlmStrategy,
    gpu_monitor: GPUMonitor,
    concurrent_requests: int = 5,
    total_requests: int = 20,
    prompt: str = "Write a short story about AI."
) -> ThroughputMetrics:
    """Run throughput benchmark with concurrent requests."""
    logger.info(f"Running throughput benchmark: {concurrent_requests} concurrent, {total_requests} total requests...")
    
    import concurrent.futures
    
    latencies = []
    successful = 0
    failed = 0
    
    def run_request():
        try:
            start = time.time()
            request = InferenceRequest(
                payload={
                    "prompt": prompt,
                    "params": {"max_tokens": 128, "temperature": 0.7}
                },
                metadata={}
            )
            strategy.infer(request)
            latency = time.time() - start
            return latency, True
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return 0.0, False
    
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
        futures = [executor.submit(run_request) for _ in range(total_requests)]
        for future in concurrent.futures.as_completed(futures):
            latency, success = future.result()
            if success:
                latencies.append(latency)
                successful += 1
            else:
                failed += 1
    
    total_time = time.time() - start_time
    
    if latencies:
        latencies_sorted = sorted(latencies)
        return ThroughputMetrics(
            concurrent_requests=concurrent_requests,
            total_requests=total_requests,
            successful_requests=successful,
            failed_requests=failed,
            total_time_seconds=total_time,
            requests_per_second=total_requests / total_time if total_time > 0 else 0,
            average_latency_seconds=statistics.mean(latencies),
            p50_latency_seconds=statistics.median(latencies),
            p95_latency_seconds=latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies_sorted else 0,
            p99_latency_seconds=latencies_sorted[int(len(latencies_sorted) * 0.99)] if latencies_sorted else 0,
            min_latency_seconds=min(latencies),
            max_latency_seconds=max(latencies)
        )
    else:
        return ThroughputMetrics(
            concurrent_requests=concurrent_requests,
            total_requests=total_requests,
            successful_requests=0,
            failed_requests=total_requests,
            total_time_seconds=total_time,
            requests_per_second=0.0,
            average_latency_seconds=0.0,
            p50_latency_seconds=0.0,
            p95_latency_seconds=0.0,
            p99_latency_seconds=0.0,
            min_latency_seconds=0.0,
            max_latency_seconds=0.0
        )


def generate_summary(report: PerformanceReport) -> Dict:
    """Generate summary statistics from benchmark results."""
    successful_latency = [r for r in report.latency_benchmarks if r.success]
    
    if not successful_latency:
        return {"error": "No successful benchmarks"}
    
    # Group by prompt type
    by_type = {}
    for result in successful_latency:
        if result.prompt_type not in by_type:
            by_type[result.prompt_type] = []
        by_type[result.prompt_type].append(result)
    
    summary = {
        "model_name": report.model_name,
        "device": report.device,
        "model_load_time_seconds": report.model_load_metrics.load_time_seconds,
        "gpu_memory_after_load_mb": report.model_load_metrics.gpu_memory_after_load_mb,
        "total_benchmarks": len(report.latency_benchmarks),
        "successful_benchmarks": len(successful_latency),
        "failed_benchmarks": len(report.latency_benchmarks) - len(successful_latency),
    }
    
    # Overall statistics
    all_latencies = [r.latency_seconds for r in successful_latency]
    all_tokens_per_sec = [r.tokens_per_second for r in successful_latency]
    
    summary["overall"] = {
        "average_latency_seconds": statistics.mean(all_latencies),
        "median_latency_seconds": statistics.median(all_latencies),
        "min_latency_seconds": min(all_latencies),
        "max_latency_seconds": max(all_latencies),
        "average_tokens_per_second": statistics.mean(all_tokens_per_sec),
        "median_tokens_per_second": statistics.median(all_tokens_per_sec),
    }
    
    # Per-prompt-type statistics
    summary["by_prompt_type"] = {}
    for prompt_type, results in by_type.items():
        latencies = [r.latency_seconds for r in results]
        tokens_per_sec = [r.tokens_per_second for r in results]
        summary["by_prompt_type"][prompt_type] = {
            "count": len(results),
            "average_latency_seconds": statistics.mean(latencies),
            "median_latency_seconds": statistics.median(latencies),
            "min_latency_seconds": min(latencies),
            "max_latency_seconds": max(latencies),
            "average_tokens_per_second": statistics.mean(tokens_per_sec),
            "median_tokens_per_second": statistics.median(tokens_per_sec),
        }
    
    # Throughput summary
    if report.throughput_benchmarks:
        throughput = report.throughput_benchmarks[0]
        summary["throughput"] = {
            "requests_per_second": throughput.requests_per_second,
            "average_latency_seconds": throughput.average_latency_seconds,
            "p95_latency_seconds": throughput.p95_latency_seconds,
            "p99_latency_seconds": throughput.p99_latency_seconds,
        }
    
    return summary


def save_report(report: PerformanceReport, output_dir: Path):
    """Save performance report to JSON and text files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save JSON report
    json_path = output_dir / f"qwen3_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, 'w') as f:
        json.dump({
            "model_name": report.model_name,
            "device": report.device,
            "benchmark_timestamp": report.benchmark_timestamp,
            "model_load_metrics": asdict(report.model_load_metrics),
            "latency_benchmarks": [asdict(r) for r in report.latency_benchmarks],
            "throughput_benchmarks": [asdict(t) for t in report.throughput_benchmarks],
            "summary": report.summary
        }, f, indent=2)
    
    logger.info(f"JSON report saved to: {json_path}")
    
    # Save human-readable text report
    txt_path = output_dir / f"qwen3_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(txt_path, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("Qwen3-30B-A3B Performance Benchmark Report\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Model: {report.model_name}\n")
        f.write(f"Device: {report.device}\n")
        f.write(f"Benchmark Date: {report.benchmark_timestamp}\n\n")
        
        f.write("Model Loading Metrics\n")
        f.write("-" * 80 + "\n")
        f.write(f"Load Time: {report.model_load_metrics.load_time_seconds:.2f} seconds\n")
        f.write(f"GPU Memory After Load: {report.model_load_metrics.gpu_memory_after_load_mb:.2f} MB\n")
        f.write(f"CPU Memory After Load: {report.model_load_metrics.cpu_memory_after_load_mb:.2f} MB\n")
        f.write(f"Success: {report.model_load_metrics.success}\n\n")
        
        f.write("Latency Benchmarks Summary\n")
        f.write("-" * 80 + "\n")
        summary = report.summary
        if "overall" in summary:
            f.write(f"Total Benchmarks: {summary['total_benchmarks']}\n")
            f.write(f"Successful: {summary['successful_benchmarks']}\n")
            f.write(f"Failed: {summary['failed_benchmarks']}\n\n")
            f.write("Overall Statistics:\n")
            f.write(f"  Average Latency: {summary['overall']['average_latency_seconds']:.3f} seconds\n")
            f.write(f"  Median Latency: {summary['overall']['median_latency_seconds']:.3f} seconds\n")
            f.write(f"  Average Tokens/Second: {summary['overall']['average_tokens_per_second']:.2f}\n")
            f.write(f"  Median Tokens/Second: {summary['overall']['median_tokens_per_second']:.2f}\n\n")
            
            if "by_prompt_type" in summary:
                f.write("By Prompt Type:\n")
                for prompt_type, stats in summary["by_prompt_type"].items():
                    f.write(f"  {prompt_type.capitalize()}:\n")
                    f.write(f"    Count: {stats['count']}\n")
                    f.write(f"    Average Latency: {stats['average_latency_seconds']:.3f} seconds\n")
                    f.write(f"    Average Tokens/Second: {stats['average_tokens_per_second']:.2f}\n")
                f.write("\n")
        
        if "throughput" in summary:
            f.write("Throughput Benchmarks\n")
            f.write("-" * 80 + "\n")
            f.write(f"Requests/Second: {summary['throughput']['requests_per_second']:.2f}\n")
            f.write(f"Average Latency: {summary['throughput']['average_latency_seconds']:.3f} seconds\n")
            f.write(f"P95 Latency: {summary['throughput']['p95_latency_seconds']:.3f} seconds\n")
            f.write(f"P99 Latency: {summary['throughput']['p99_latency_seconds']:.3f} seconds\n\n")
        
        f.write("=" * 80 + "\n")
    
    logger.info(f"Text report saved to: {txt_path}")
    
    return json_path, txt_path


class BenchmarkQwen3Command(Command):
    """Command for benchmarking Qwen3-30B-A3B performance."""
    
    @classmethod
    def get_name(cls) -> str:
        return "benchmark-qwen3"
    
    @classmethod
    def get_description(cls) -> str:
        return "Benchmark Qwen3-30B-A3B model performance"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--output-dir",
            type=str,
            default="benchmark_reports",
            help="Directory to save benchmark reports (default: benchmark_reports)"
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=3,
            help="Number of iterations per prompt (default: 3)"
        )
        parser.add_argument(
            "--skip-load-test",
            action="store_true",
            help="Skip model loading benchmark (useful if model is already loaded)"
        )
        parser.add_argument(
            "--skip-throughput",
            action="store_true",
            help="Skip throughput benchmark"
        )
    
    def init(self) -> None:
        """Initialize benchmark Qwen3 command."""
        if not DEPENDENCIES_AVAILABLE:
            error_msg = f"Required dependencies not available: {IMPORT_ERROR}"
            logger.error(error_msg)
            raise RuntimeError(f"{error_msg}\nInstall with: pip install torch psutil")
        if not INFERENCE_CORE_AVAILABLE:
            error_msg = "inference_core package not available"
            logger.error(error_msg)
            raise RuntimeError(f"{error_msg}\nThis command must be run in a container with inference_core installed")
    
    def run(self) -> None:
        """Run the benchmark."""
        output_dir = Path(self.args.output_dir)
        
        logger.info("Starting Qwen3-30B-A3B performance benchmarks...")
        logger.info(f"Model: {config.model.name}")
        logger.info(f"Device: {config.model.device}")
        
        # Initialize strategy and GPU monitor
        strategy = Qwen3LlmStrategy(
            model_name=config.model.name,
            device=config.model.device,
            max_context_length=config.model.max_context_length,
            use_yarn=config.model.use_yarn,
            huggingface_token=config.model.huggingface_token,
            model_cache_dir=config.model.model_cache_dir,
        )
        
        gpu_monitor = GPUMonitor()
        
        # Measure model loading
        if self.args.skip_load_test:
            logger.info("Skipping model load test (assuming model is already loaded)")
            model_load_metrics = ModelLoadMetrics(
                load_time_seconds=0.0,
                gpu_memory_after_load_mb=0.0,
                cpu_memory_after_load_mb=0.0,
                success=True
            )
            # Still need to load the model
            strategy.warmup()
        else:
            model_load_metrics = measure_model_loading(strategy, gpu_monitor)
            if not model_load_metrics.success:
                logger.error("Model loading failed, cannot continue benchmarks")
                sys.exit(1)
        
        # Run latency benchmarks
        latency_results = run_latency_benchmarks(strategy, gpu_monitor, iterations=self.args.iterations)
        
        # Run throughput benchmarks
        throughput_results = []
        if not self.args.skip_throughput:
            throughput_metrics = run_throughput_benchmark(strategy, gpu_monitor)
            throughput_results.append(throughput_metrics)
        
        # Generate report
        report = PerformanceReport(
            model_name=config.model.name,
            device=config.model.device,
            benchmark_timestamp=datetime.now().isoformat(),
            model_load_metrics=model_load_metrics,
            latency_benchmarks=latency_results,
            throughput_benchmarks=throughput_results,
            summary={}
        )
        
        report.summary = generate_summary(report)
        
        # Save reports
        json_path, txt_path = save_report(report, output_dir)
        
        # Print summary
        print("\n" + "=" * 80)
        print("Benchmark Summary")
        print("=" * 80)
        if "overall" in report.summary:
            print(f"Average Latency: {report.summary['overall']['average_latency_seconds']:.3f} seconds")
            print(f"Average Tokens/Second: {report.summary['overall']['average_tokens_per_second']:.2f}")
            if "throughput" in report.summary:
                print(f"Throughput: {report.summary['throughput']['requests_per_second']:.2f} requests/second")
        print(f"\nReports saved to:")
        print(f"  JSON: {json_path}")
        print(f"  Text: {txt_path}")
    
    def cleanup(self) -> None:
        """Clean up benchmark Qwen3 command."""
        # No cleanup needed for this tool
        pass
