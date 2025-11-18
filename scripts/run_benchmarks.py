#!/usr/bin/env python3
"""
Run Benchmark Evaluations

Orchestrates benchmark evaluation with sandboxed execution.
All operations run in containers - no host system pollution.

Usage:
    python scripts/run_benchmarks.py [--dataset DATASET] [--max-tasks N] [--output-dir DIR]
"""
import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from essence.agents.evaluator import BenchmarkEvaluator
from essence.agents.dataset_loader import DatasetLoader
from essence.chat.utils.tracing import setup_tracing

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run benchmark evaluations")
    parser.add_argument(
        "--dataset",
        choices=["humaneval", "mbpp", "all"],
        default="humaneval",
        help="Dataset to evaluate (default: humaneval)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to evaluate (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/benchmarks/results"),
        help="Output directory for results and snapshots (default: /tmp/benchmarks/results)",
    )
    parser.add_argument(
        "--inference-api-url",
        default="inference-api:50051",
        help="gRPC endpoint for inference API (default: inference-api:50051)",
    )
    parser.add_argument(
        "--model-name",
        default="Qwen/Qwen3-30B-A3B-Thinking-2507",
        help="Model name to evaluate (default: Qwen/Qwen3-30B-A3B-Thinking-2507)",
    )
    parser.add_argument(
        "--sandbox-image",
        default="python:3.11-slim",
        help="Docker base image for sandboxes (default: python:3.11-slim)",
    )
    parser.add_argument(
        "--sandbox-memory",
        default="4g",
        help="Maximum memory for sandboxes (default: 4g)",
    )
    parser.add_argument(
        "--sandbox-cpu",
        default="2.0",
        help="Maximum CPU for sandboxes (default: 2.0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Maximum time per task in seconds (default: 300)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum agent iterations per task (default: 10)",
    )
    parser.add_argument(
        "--enable-network",
        action="store_true",
        help="Enable network access in sandboxes (default: disabled)",
    )
    
    args = parser.parse_args()
    
    # Setup tracing
    setup_tracing(service_name="june-benchmark-evaluator")
    
    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize evaluator
    evaluator = BenchmarkEvaluator(
        inference_api_url=args.inference_api_url,
        model_name=args.model_name,
        sandbox_base_image=args.sandbox_image,
        sandbox_workspace_base=args.output_dir / "sandboxes",
        max_sandbox_memory=args.sandbox_memory,
        max_sandbox_cpu=args.sandbox_cpu,
        network_disabled=not args.enable_network,
        max_iterations=args.max_iterations,
        timeout_seconds=args.timeout,
    )
    
    # Load datasets
    datasets_to_evaluate = []
    if args.dataset == "all":
        datasets_to_evaluate = ["humaneval", "mbpp"]
    else:
        datasets_to_evaluate = [args.dataset]
    
    all_reports = []
    
    for dataset_name in datasets_to_evaluate:
        logger.info(f"Loading {dataset_name} dataset...")
        
        try:
            if dataset_name == "humaneval":
                tasks = DatasetLoader.load_humaneval()
            elif dataset_name == "mbpp":
                tasks = DatasetLoader.load_mbpp()
            else:
                logger.error(f"Unknown dataset: {dataset_name}")
                continue
            
            logger.info(f"Loaded {len(tasks)} tasks from {dataset_name}")
            
            # Evaluate dataset
            dataset_output_dir = args.output_dir / dataset_name
            report = evaluator.evaluate_dataset(
                tasks=tasks,
                output_dir=dataset_output_dir,
                max_tasks=args.max_tasks,
            )
            
            all_reports.append(report)
            
            # Print summary
            logger.info(f"\n{'='*60}")
            logger.info(f"Evaluation Report: {dataset_name}")
            logger.info(f"{'='*60}")
            logger.info(f"Total tasks: {report.total_tasks}")
            logger.info(f"Successful tasks: {report.successful_tasks}")
            logger.info(f"Passed tests: {report.passed_tests}")
            logger.info(f"Pass@1: {report.pass_at_1:.2%}")
            logger.info(f"Average execution time: {report.average_execution_time:.2f}s")
            logger.info(f"Average iterations: {report.average_iterations:.2f}")
            logger.info(f"Average commands: {report.average_commands:.2f}")
            logger.info(f"Efficiency score: {report.efficiency_score:.4f}")
            logger.info(f"Results saved to: {dataset_output_dir}")
            logger.info(f"{'='*60}\n")
            
        except Exception as e:
            logger.error(f"Failed to evaluate {dataset_name}: {e}", exc_info=True)
            continue
    
    # Generate combined report if multiple datasets
    if len(all_reports) > 1:
        combined_output = args.output_dir / "combined_report.json"
        combined_data = {
            "timestamp": all_reports[0].timestamp,
            "model_name": args.model_name,
            "datasets": [r.to_dict() for r in all_reports],
        }
        import json
        with open(combined_output, 'w') as f:
            json.dump(combined_data, f, indent=2)
        logger.info(f"Combined report saved to: {combined_output}")
    
    logger.info("Benchmark evaluation completed!")


if __name__ == "__main__":
    main()
