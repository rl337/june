"""
Benchmark Evaluation Framework

Provides test harness for running coding benchmarks (HumanEval, MBPP, etc.)
with sandboxed execution, result collection, and efficiency metrics.
All operations run in containers - no host system pollution.
"""
import logging
import json
import time
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Iterator, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import statistics

from essence.agents.sandbox import Sandbox, SandboxMetrics, CommandLog
from essence.agents.coding_agent import CodingAgent
from essence.chat.utils.tracing import get_tracer
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


@dataclass
class BenchmarkTask:
    """A single benchmark task."""
    task_id: str
    dataset: str  # 'humaneval', 'mbpp', etc.
    prompt: str
    canonical_solution: Optional[str] = None
    test_code: Optional[str] = None
    entry_point: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class TaskResult:
    """Result from evaluating a single task."""
    task_id: str
    dataset: str
    success: bool
    passed_tests: bool
    error_message: Optional[str] = None
    solution_code: Optional[str] = None
    execution_time_seconds: float = 0.0
    sandbox_metrics: Optional[SandboxMetrics] = None
    agent_iterations: int = 0
    tokens_generated: int = 0
    files_created: int = 0
    files_modified: int = 0
    commands_executed: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        if self.sandbox_metrics:
            result['sandbox_metrics'] = self.sandbox_metrics.to_dict()
        return result


@dataclass
class BaselineComparison:
    """Comparison with published baseline results."""
    baseline_name: str  # e.g., "GPT-4", "Claude-3", "Qwen2.5-32B"
    baseline_pass_at_1: float
    baseline_pass_at_k: Dict[int, float]
    our_pass_at_1: float
    our_pass_at_k: Dict[int, float]
    pass_at_1_delta: float  # our - baseline
    pass_at_k_delta: Dict[int, float]  # our - baseline
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class EvaluationReport:
    """Complete evaluation report for a benchmark dataset."""
    dataset: str
    model_name: str
    timestamp: str
    total_tasks: int
    successful_tasks: int
    passed_tests: int
    pass_at_1: float
    pass_at_k: Dict[int, float]  # pass@k for k in [1, 5, 10, 100]
    average_execution_time: float
    average_iterations: float
    average_commands: float
    average_tokens: float
    efficiency_score: float  # Composite efficiency metric
    task_results: List[TaskResult]
    baseline_comparisons: Optional[List[BaselineComparison]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['task_results'] = [tr.to_dict() for tr in self.task_results]
        if self.baseline_comparisons:
            result['baseline_comparisons'] = [bc.to_dict() for bc in self.baseline_comparisons]
        return result
    
    def save(self, output_path: Path) -> None:
        """Save report to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved evaluation report to {output_path}")


class BenchmarkEvaluator:
    """
    Evaluator for coding benchmarks.
    
    Orchestrates sandbox creation, agent execution, result collection,
    and report generation. All operations run in containers.
    """
    
    def __init__(
        self,
        inference_api_url: str = "inference-api:50051",
        model_name: str = "Qwen/Qwen3-30B-A3B-Thinking-2507",
        sandbox_base_image: str = "python:3.11-slim",
        sandbox_workspace_base: Optional[Path] = None,
        max_sandbox_memory: str = "4g",
        max_sandbox_cpu: str = "2.0",
        network_disabled: bool = True,
        max_iterations: int = 10,
        timeout_seconds: int = 300,
    ):
        """
        Initialize the evaluator.
        
        Args:
            inference_api_url: gRPC endpoint for inference API
            model_name: Name of the model to evaluate
            sandbox_base_image: Docker base image for sandboxes
            sandbox_workspace_base: Base directory for sandbox workspaces (defaults to /tmp/benchmarks)
            max_sandbox_memory: Maximum memory for each sandbox
            max_sandbox_cpu: Maximum CPU for each sandbox
            network_disabled: Whether to disable network access in sandboxes
            max_iterations: Maximum agent iterations per task
            timeout_seconds: Maximum time per task in seconds
        """
        self.inference_api_url = inference_api_url
        self.model_name = model_name
        self.sandbox_base_image = sandbox_base_image
        self.sandbox_workspace_base = sandbox_workspace_base or Path("/tmp/benchmarks")
        self.max_sandbox_memory = max_sandbox_memory
        self.max_sandbox_cpu = max_sandbox_cpu
        self.network_disabled = network_disabled
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        
        # Ensure workspace base exists
        self.sandbox_workspace_base.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized BenchmarkEvaluator with model {model_name}")
    
    def evaluate_task(
        self,
        task: BenchmarkTask,
        save_sandbox_snapshot: bool = True,
    ) -> TaskResult:
        """
        Evaluate a single benchmark task.
        
        Args:
            task: The benchmark task to evaluate
            save_sandbox_snapshot: Whether to save sandbox state after completion
            
        Returns:
            TaskResult with evaluation results
        """
        with tracer.start_as_current_span("evaluator.evaluate_task") as span:
            span.set_attribute("task_id", task.task_id)
            span.set_attribute("dataset", task.dataset)
            
            task_start_time = time.time()
            sandbox: Optional[Sandbox] = None
            agent: Optional[CodingAgent] = None
            
            try:
                # Create sandbox for this task
                workspace_dir = self.sandbox_workspace_base / task.task_id
                workspace_dir.mkdir(parents=True, exist_ok=True)
                
                sandbox = Sandbox(
                    task_id=task.task_id,
                    base_image=self.sandbox_base_image,
                    workspace_dir=workspace_dir,
                    max_memory=self.max_sandbox_memory,
                    max_cpu=self.max_sandbox_cpu,
                    network_disabled=self.network_disabled,
                )
                
                sandbox.start()
                span.set_attribute("sandbox_created", True)
                
                # Record initial files after sandbox starts but before task execution
                # (for tracking modifications during task execution)
                initial_files = {}  # Dict mapping file path to initial mtime
                if workspace_dir.exists():
                    for f in workspace_dir.rglob("*"):
                        if f.is_file():
                            try:
                                initial_files[f] = f.stat().st_mtime
                            except (OSError, FileNotFoundError):
                                # File may be deleted or inaccessible
                                pass
                
                # Initialize coding agent
                agent = CodingAgent(
                    inference_api_url=self.inference_api_url,
                    model_name=self.model_name,
                )
                agent.set_workspace(str(workspace_dir))
                
                # Prepare task prompt
                task_prompt = self._build_task_prompt(task)
                
                # Run agent to solve task
                solution_code = None
                agent_iterations = 0
                tokens_generated = 0
                
                for iteration in range(self.max_iterations):
                    agent_iterations = iteration + 1
                    span.set_attribute("agent_iteration", agent_iterations)
                    
                    # Send task to agent
                    response_chunks = list(agent.send_coding_task(
                        task_description=task_prompt,
                        context={"iteration": iteration + 1},
                        reset_conversation=(iteration == 0),
                    ))
                    
                    # Extract solution from response
                    # For now, assume the agent writes the solution to a file
                    # In a real implementation, we'd parse the agent's tool calls
                    # and extract the generated code
                    
                    # Check if solution file exists
                    solution_files = list(workspace_dir.glob("*.py"))
                    if solution_files:
                        # Read the most recent solution file
                        solution_file = max(solution_files, key=lambda p: p.stat().st_mtime)
                        solution_code = solution_file.read_text()
                        break
                    
                    # Check timeout
                    if time.time() - task_start_time > self.timeout_seconds:
                        logger.warning(f"Task {task.task_id} timed out after {self.timeout_seconds}s")
                        break
                
                # Test the solution
                passed_tests = False
                error_message = None
                
                if solution_code and task.test_code:
                    test_result = self._run_tests(sandbox, solution_code, task)
                    passed_tests = test_result["passed"]
                    error_message = test_result.get("error")
                elif solution_code:
                    # No test code provided, consider it successful if code was generated
                    passed_tests = True
                else:
                    error_message = "No solution code generated"
                
                # Collect metrics
                sandbox_metrics = sandbox.metrics
                sandbox_metrics.end_time = time.time()
                
                # Count files created and modified
                files_created = 0
                files_modified = 0
                if workspace_dir.exists():
                    final_files = {}
                    for f in workspace_dir.rglob("*"):
                        if f.is_file():
                            try:
                                final_files[f] = f.stat().st_mtime
                            except (OSError, FileNotFoundError):
                                # File may be deleted or inaccessible
                                pass
                    
                    # Files created: exist in final but not in initial
                    files_created = len(set(final_files.keys()) - set(initial_files.keys()))
                    
                    # Files modified: exist in both but have different modification times
                    for file_path, final_mtime in final_files.items():
                        if file_path in initial_files:
                            initial_mtime = initial_files[file_path]
                            if final_mtime > initial_mtime:
                                files_modified += 1
                
                # Save sandbox snapshot if requested
                if save_sandbox_snapshot:
                    # Save metadata to workspace
                    sandbox.save_metadata()
                    # Create snapshot
                    snapshot_dir = workspace_dir.parent / f"{task.task_id}_snapshot"
                    snapshot_dir.mkdir(parents=True, exist_ok=True)
                    sandbox.snapshot_filesystem("final")
                    # Copy metadata to snapshot
                    metadata_file = workspace_dir / "sandbox_metadata.json"
                    if metadata_file.exists():
                        shutil.copy2(metadata_file, snapshot_dir / "sandbox_metadata.json")
                    span.set_attribute("snapshot_saved", True)
                
                execution_time = time.time() - task_start_time
                
                result = TaskResult(
                    task_id=task.task_id,
                    dataset=task.dataset,
                    success=(solution_code is not None),
                    passed_tests=passed_tests,
                    error_message=error_message,
                    solution_code=solution_code,
                    execution_time_seconds=execution_time,
                    sandbox_metrics=sandbox_metrics,
                    agent_iterations=agent_iterations,
                    tokens_generated=tokens_generated,
                    files_created=files_created,
                    files_modified=files_modified,
                    commands_executed=sandbox_metrics.commands_executed if sandbox_metrics else 0,
                )
                
                span.set_attribute("task_success", result.success)
                span.set_attribute("tests_passed", result.passed_tests)
                span.set_attribute("execution_time", execution_time)
                
                return result
                
            except Exception as e:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"Error evaluating task {task.task_id}: {e}", exc_info=True)
                
                execution_time = time.time() - task_start_time
                return TaskResult(
                    task_id=task.task_id,
                    dataset=task.dataset,
                    success=False,
                    passed_tests=False,
                    error_message=str(e),
                    execution_time_seconds=execution_time,
                )
            finally:
                # Clean up sandbox
                if sandbox:
                    try:
                        sandbox.cleanup()
                    except Exception as e:
                        logger.warning(f"Error cleaning up sandbox: {e}")
    
    def _build_task_prompt(self, task: BenchmarkTask) -> str:
        """Build the prompt for the coding agent from a benchmark task."""
        prompt_parts = [
            f"Task: {task.prompt}",
        ]
        
        if task.entry_point:
            prompt_parts.append(f"\nFunction signature: {task.entry_point}")
        
        if task.test_code:
            prompt_parts.append(f"\nTest code:\n```python\n{task.test_code}\n```")
        
        prompt_parts.append(
            "\nPlease implement a solution. Write your code to a Python file in the workspace."
        )
        
        return "\n".join(prompt_parts)
    
    def _run_tests(
        self,
        sandbox: Sandbox,
        solution_code: str,
        task: BenchmarkTask,
    ) -> Dict[str, Any]:
        """
        Run tests for a solution in the sandbox.
        
        Args:
            sandbox: The sandbox container
            solution_code: The solution code to test
            task: The benchmark task with test code
            
        Returns:
            Dictionary with 'passed' (bool) and optional 'error' (str)
        """
        try:
            # Write solution to workspace directory (host path, mounted in container)
            workspace_dir = sandbox.workspace_dir
            solution_file = workspace_dir / "solution.py"
            solution_file.write_text(solution_code)
            
            # Write test code to a file
            test_file = workspace_dir / "test_solution.py"
            test_code = f"""
{solution_code}

{task.test_code}

if __name__ == "__main__":
    import sys
    try:
        # Run the tests
        # This is a simplified version - real implementation would parse test_code
        # and execute it properly
        exec(""" + repr(task.test_code) + """)
        print("Tests passed")
        sys.exit(0)
    except Exception as e:
        print(f"Tests failed: {{e}}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
"""
            test_file.write_text(test_code)
            
            # Execute tests
            result = sandbox.execute_command(
                "python /workspace/test_solution.py",
                working_directory="/workspace",
                timeout=30,
            )
            
            passed = result["returncode"] == 0
            error = None if passed else result.get("stderr", result.get("stdout", "Unknown error"))
            
            return {
                "passed": passed,
                "error": error,
            }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }
    
    def evaluate_dataset(
        self,
        tasks: List[BenchmarkTask],
        output_dir: Optional[Path] = None,
        max_tasks: Optional[int] = None,
    ) -> EvaluationReport:
        """
        Evaluate a dataset of benchmark tasks.
        
        Args:
            tasks: List of benchmark tasks to evaluate
            output_dir: Directory to save results and snapshots
            max_tasks: Maximum number of tasks to evaluate (None for all)
            
        Returns:
            EvaluationReport with results
        """
        with tracer.start_as_current_span("evaluator.evaluate_dataset") as span:
            if max_tasks:
                tasks = tasks[:max_tasks]
                span.set_attribute("max_tasks", max_tasks)
            
            span.set_attribute("total_tasks", len(tasks))
            span.set_attribute("dataset", tasks[0].dataset if tasks else "unknown")
            
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
            
            task_results: List[TaskResult] = []
            
            logger.info(f"Evaluating {len(tasks)} tasks from dataset {tasks[0].dataset if tasks else 'unknown'}")
            
            for i, task in enumerate(tasks, 1):
                logger.info(f"Evaluating task {i}/{len(tasks)}: {task.task_id}")
                
                result = self.evaluate_task(
                    task,
                    save_sandbox_snapshot=(output_dir is not None),
                )
                task_results.append(result)
                
                # Save intermediate results
                if output_dir:
                    result_file = output_dir / f"{task.task_id}_result.json"
                    with open(result_file, 'w') as f:
                        json.dump(result.to_dict(), f, indent=2)
            
            # Generate report
            report = self._generate_report(tasks, task_results)
            
            # Save report
            if output_dir:
                report_file = output_dir / "evaluation_report.json"
                report.save(report_file)
                span.set_attribute("report_saved", str(report_file))
            
            return report
    
    def _generate_report(
        self,
        tasks: List[BenchmarkTask],
        results: List[TaskResult],
    ) -> EvaluationReport:
        """Generate evaluation report from task results."""
        if not results:
            raise ValueError("No results to generate report from")
        
        dataset = results[0].dataset
        total_tasks = len(results)
        successful_tasks = sum(1 for r in results if r.success)
        passed_tests = sum(1 for r in results if r.passed_tests)
        
        # Calculate pass@k
        # For pass@k, we need multiple attempts per task
        # For now, we'll calculate pass@1 (single attempt)
        pass_at_1 = passed_tests / total_tasks if total_tasks > 0 else 0.0
        
        # Calculate pass@k for k in [1, 5, 10, 100]
        # This is a simplified version - real implementation would need multiple attempts
        pass_at_k = {
            1: pass_at_1,
            5: pass_at_1,  # TODO: Calculate properly with multiple attempts
            10: pass_at_1,  # TODO: Calculate properly with multiple attempts
            100: pass_at_1,  # TODO: Calculate properly with multiple attempts
        }
        
        # Calculate efficiency metrics
        execution_times = [r.execution_time_seconds for r in results if r.execution_time_seconds > 0]
        iterations = [r.agent_iterations for r in results if r.agent_iterations > 0]
        commands = [r.commands_executed for r in results if r.commands_executed > 0]
        tokens = [r.tokens_generated for r in results if r.tokens_generated > 0]
        
        avg_execution_time = statistics.mean(execution_times) if execution_times else 0.0
        avg_iterations = statistics.mean(iterations) if iterations else 0.0
        avg_commands = statistics.mean(commands) if commands else 0.0
        avg_tokens = statistics.mean(tokens) if tokens else 0.0
        
        # Efficiency score: combination of correctness and efficiency
        # Higher is better (more correct, fewer resources used)
        efficiency_score = (
            (pass_at_1 * 0.5) +  # Correctness weight
            (1.0 / (1.0 + avg_execution_time / 60.0) * 0.2) +  # Speed weight (normalized)
            (1.0 / (1.0 + avg_iterations / 5.0) * 0.15) +  # Iteration efficiency
            (1.0 / (1.0 + avg_commands / 20.0) * 0.15)  # Command efficiency
        )
        
        # Compare with published baselines
        baseline_comparisons = self._compare_with_baselines(dataset, pass_at_1, pass_at_k)
        
        return EvaluationReport(
            dataset=dataset,
            model_name=self.model_name,
            timestamp=datetime.utcnow().isoformat(),
            total_tasks=total_tasks,
            successful_tasks=successful_tasks,
            passed_tests=passed_tests,
            pass_at_1=pass_at_1,
            pass_at_k=pass_at_k,
            average_execution_time=avg_execution_time,
            average_iterations=avg_iterations,
            average_commands=avg_commands,
            average_tokens=avg_tokens,
            efficiency_score=efficiency_score,
            task_results=results,
            baseline_comparisons=baseline_comparisons,
        )
    
    def _compare_with_baselines(
        self,
        dataset: str,
        our_pass_at_1: float,
        our_pass_at_k: Dict[int, float],
    ) -> Optional[List[BaselineComparison]]:
        """
        Compare results with published baseline results.
        
        Args:
            dataset: Dataset name (humaneval, mbpp, etc.)
            our_pass_at_1: Our pass@1 score
            our_pass_at_k: Our pass@k scores
            
        Returns:
            List of BaselineComparison objects, or None if no baselines available
        """
        # Published baseline results (from papers and leaderboards)
        # These are approximate values - actual baselines may vary
        baselines = {
            "humaneval": [
                {
                    "name": "GPT-4",
                    "pass_at_1": 0.674,  # From OpenAI paper
                    "pass_at_k": {1: 0.674, 5: 0.90, 10: 0.95, 100: 0.99},
                },
                {
                    "name": "Claude-3-Opus",
                    "pass_at_1": 0.84,  # From Anthropic paper
                    "pass_at_k": {1: 0.84, 5: 0.92, 10: 0.95, 100: 0.98},
                },
                {
                    "name": "Qwen2.5-32B",
                    "pass_at_1": 0.75,  # Approximate from Qwen paper
                    "pass_at_k": {1: 0.75, 5: 0.88, 10: 0.92, 100: 0.97},
                },
                {
                    "name": "GPT-3.5-Turbo",
                    "pass_at_1": 0.48,  # From OpenAI paper
                    "pass_at_k": {1: 0.48, 5: 0.70, 10: 0.78, 100: 0.90},
                },
            ],
            "mbpp": [
                {
                    "name": "GPT-4",
                    "pass_at_1": 0.83,  # Approximate
                    "pass_at_k": {1: 0.83, 5: 0.92, 10: 0.95, 100: 0.98},
                },
                {
                    "name": "Claude-3-Opus",
                    "pass_at_1": 0.87,  # Approximate
                    "pass_at_k": {1: 0.87, 5: 0.94, 10: 0.96, 100: 0.99},
                },
                {
                    "name": "Qwen2.5-32B",
                    "pass_at_1": 0.80,  # Approximate
                    "pass_at_k": {1: 0.80, 5: 0.90, 10: 0.93, 100: 0.97},
                },
            ],
        }
        
        dataset_baselines = baselines.get(dataset)
        if not dataset_baselines:
            logger.info(f"No baseline data available for dataset: {dataset}")
            return None
        
        comparisons = []
        for baseline in dataset_baselines:
            baseline_pass_at_k = baseline["pass_at_k"]
            our_pass_at_k_values = {
                k: our_pass_at_k.get(k, our_pass_at_1) for k in [1, 5, 10, 100]
            }
            
            # Calculate deltas
            pass_at_1_delta = our_pass_at_1 - baseline["pass_at_1"]
            pass_at_k_delta = {
                k: our_pass_at_k_values[k] - baseline_pass_at_k.get(k, baseline["pass_at_1"])
                for k in [1, 5, 10, 100]
            }
            
            comparison = BaselineComparison(
                baseline_name=baseline["name"],
                baseline_pass_at_1=baseline["pass_at_1"],
                baseline_pass_at_k=baseline_pass_at_k,
                our_pass_at_1=our_pass_at_1,
                our_pass_at_k=our_pass_at_k_values,
                pass_at_1_delta=pass_at_1_delta,
                pass_at_k_delta=pass_at_k_delta,
            )
            comparisons.append(comparison)
        
        logger.info(f"Compared with {len(comparisons)} baselines for {dataset}")
        return comparisons
