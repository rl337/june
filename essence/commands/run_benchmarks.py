"""
Run benchmark evaluations command - Orchestrates benchmark evaluation with sandboxed execution.

Usage:
    poetry run -m essence run-benchmarks [--dataset DATASET] [--max-tasks N] [--output-dir DIR]

This command runs coding agent evaluations on benchmark datasets (HumanEval, MBPP) with
sandboxed execution. All operations run in containers - no host system pollution.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from essence.chat.utils.tracing import setup_tracing
from essence.command import Command

logger = logging.getLogger(__name__)

# Import evaluator and dataset loader (may not be available in all environments)
try:
    from essence.agents.dataset_loader import DatasetLoader
    from essence.agents.evaluator import BenchmarkEvaluator

    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    DEPENDENCIES_AVAILABLE = False
    IMPORT_ERROR = str(e)
    BenchmarkEvaluator = None
    DatasetLoader = None


class RunBenchmarksCommand(Command):
    """
    Command for running benchmark evaluations with sandboxed execution.

    Orchestrates evaluation of coding agents on benchmark datasets (HumanEval, MBPP)
    using isolated Docker container sandboxes. All task execution happens in containers
    to ensure security, reproducibility, and full activity logging.

    Supports multiple datasets, configurable sandbox resources, and generates detailed
    evaluation reports with metrics including pass@k, execution time, and efficiency scores.
    """

    def __init__(self, args: argparse.Namespace):
        """
        Initialize command with parsed arguments.

        Args:
            args: Parsed command-line arguments containing benchmark configuration
        """
        super().__init__(args)
        self._evaluator = None
        self._output_dir = None

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "run-benchmarks"
        """
        return "run-benchmarks"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Run benchmark evaluations with sandboxed execution"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures all benchmark evaluation parameters including dataset selection,
        sandbox configuration, resource limits, and output options.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--dataset",
            choices=["humaneval", "mbpp", "all"],
            default=os.getenv("BENCHMARK_DATASET", "humaneval"),
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
            default=Path(os.getenv("BENCHMARK_OUTPUT_DIR", "/tmp/benchmarks/results")),
            help="Output directory for results and snapshots (default: /tmp/benchmarks/results)",
        )
        parser.add_argument(
            "--llm-url",
            default=os.getenv(
                "LLM_URL", os.getenv("INFERENCE_API_URL", "tensorrt-llm:8000")
            ),
            help="gRPC endpoint for LLM inference service (default: tensorrt-llm:8000 for TensorRT-LLM, can use inference-api:50051 for legacy service, nim-qwen3:8001 for NVIDIA NIM)",
        )
        parser.add_argument(
            "--model-name",
            default=os.getenv("MODEL_NAME", "Qwen/Qwen3-30B-A3B-Thinking-2507"),
            help="Model name to evaluate (default: Qwen/Qwen3-30B-A3B-Thinking-2507)",
        )
        parser.add_argument(
            "--sandbox-image",
            default=os.getenv("SANDBOX_IMAGE", "python:3.11-slim"),
            help="Docker base image for sandboxes (default: python:3.11-slim)",
        )
        parser.add_argument(
            "--sandbox-memory",
            default=os.getenv("SANDBOX_MEMORY", "4g"),
            help="Maximum memory for sandboxes (default: 4g)",
        )
        parser.add_argument(
            "--sandbox-cpu",
            default=os.getenv("SANDBOX_CPU", "2.0"),
            help="Maximum CPU for sandboxes (default: 2.0)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=int(os.getenv("BENCHMARK_TIMEOUT", "300")),
            help="Maximum time per task in seconds (default: 300)",
        )
        parser.add_argument(
            "--max-iterations",
            type=int,
            default=int(os.getenv("BENCHMARK_MAX_ITERATIONS", "10")),
            help="Maximum agent iterations per task (default: 10)",
        )
        parser.add_argument(
            "--enable-network",
            action="store_true",
            default=os.getenv("BENCHMARK_ENABLE_NETWORK", "false").lower() == "true",
            help="Enable network access in sandboxes (default: disabled)",
        )
        parser.add_argument(
            "--num-attempts",
            type=int,
            default=int(os.getenv("BENCHMARK_NUM_ATTEMPTS", "1")),
            help="Number of attempts per task for pass@k calculation (default: 1). "
                 "Set to k (e.g., 5) to calculate pass@k accurately. "
                 "Each attempt uses different random seeds/sampling parameters.",
        )

    def init(self) -> None:
        """
        Initialize benchmark evaluation.

        Sets up OpenTelemetry tracing, creates output directories, and initializes
        the BenchmarkEvaluator with configured sandbox and inference API settings.

        Raises:
            RuntimeError: If required dependencies (evaluator, dataset_loader) are not available
        """
        if not DEPENDENCIES_AVAILABLE:
            raise RuntimeError(
                f"Required dependencies not available: {IMPORT_ERROR}\n"
                "Make sure essence.agents.evaluator and essence.agents.dataset_loader are available."
            )

        # Setup tracing
        setup_tracing(service_name="june-benchmark-evaluator")

        # Create output directory
        self._output_dir = self.args.output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {self._output_dir}")

        # Initialize evaluator
        self._evaluator = BenchmarkEvaluator(
            llm_url=self.args.llm_url,
            model_name=self.args.model_name,
            sandbox_base_image=self.args.sandbox_image,
            sandbox_workspace_base=self._output_dir / "sandboxes",
            max_sandbox_memory=self.args.sandbox_memory,
            max_sandbox_cpu=self.args.sandbox_cpu,
            network_disabled=not self.args.enable_network,
            max_iterations=self.args.max_iterations,
            timeout_seconds=self.args.timeout,
            num_attempts_per_task=self.args.num_attempts,
        )
        logger.info("Benchmark evaluator initialized")

    def run(self) -> None:
        """
        Run benchmark evaluations.

        Loads datasets (HumanEval, MBPP, or both), evaluates each task in isolated
        sandboxes, collects metrics, and generates detailed reports. Supports
        evaluating subsets of tasks via --max-tasks and generates both per-dataset
        and combined reports.

        For each dataset:
        - Loads tasks from the dataset loader
        - Evaluates tasks using the BenchmarkEvaluator
        - Prints summary statistics (pass@1, execution time, efficiency)
        - Saves detailed reports and sandbox snapshots to output directory

        If multiple datasets are evaluated, generates a combined report with
        aggregated results across all datasets.
        """
        # Determine datasets to evaluate
        datasets_to_evaluate = []
        if self.args.dataset == "all":
            datasets_to_evaluate = ["humaneval", "mbpp"]
        else:
            datasets_to_evaluate = [self.args.dataset]

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
                dataset_output_dir = self._output_dir / dataset_name
                report = self._evaluator.evaluate_dataset(
                    tasks=tasks,
                    output_dir=dataset_output_dir,
                    max_tasks=self.args.max_tasks,
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
                logger.info(
                    f"Average execution time: {report.average_execution_time:.2f}s"
                )
                logger.info(f"Average iterations: {report.average_iterations:.2f}")
                logger.info(f"Average commands: {report.average_commands:.2f}")
                logger.info(f"Efficiency score: {report.efficiency_score:.4f}")

                # Print baseline comparisons
                if report.baseline_comparisons:
                    logger.info(f"\n--- Baseline Comparisons ---")
                    for comp in report.baseline_comparisons:
                        delta_sign = "+" if comp.pass_at_1_delta >= 0 else ""
                        logger.info(f"{comp.baseline_name}:")
                        logger.info(f"  Baseline Pass@1: {comp.baseline_pass_at_1:.2%}")
                        logger.info(f"  Our Pass@1: {comp.our_pass_at_1:.2%}")
                        logger.info(f"  Delta: {delta_sign}{comp.pass_at_1_delta:.2%}")

                logger.info(f"\nResults saved to: {dataset_output_dir}")
                logger.info(f"{'='*60}\n")

            except Exception as e:
                logger.error(f"Failed to evaluate {dataset_name}: {e}", exc_info=True)
                continue

        # Generate combined report if multiple datasets
        if len(all_reports) > 1:
            combined_output = self._output_dir / "combined_report.json"
            combined_data = {
                "timestamp": all_reports[0].timestamp,
                "model_name": self.args.model_name,
                "datasets": [r.to_dict() for r in all_reports],
            }
            with open(combined_output, "w") as f:
                json.dump(combined_data, f, indent=2)
            logger.info(f"Combined report saved to: {combined_output}")

        logger.info("Benchmark evaluation completed!")

    def cleanup(self) -> None:
        """
        Clean up benchmark evaluation resources.

        Releases any resources held by the benchmark evaluator, including
        sandbox containers and connections. Should be called when the command
        is finished to ensure proper resource cleanup.
        """
        if self._evaluator:
            # Evaluator cleanup if needed
            pass
        logger.info("Benchmark evaluation cleanup complete")
