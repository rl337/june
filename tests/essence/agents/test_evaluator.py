"""
Unit Tests for Benchmark Evaluator

Tests the pass@k calculation logic and report generation functionality.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from essence.agents.evaluator import (
    BenchmarkEvaluator,
    BenchmarkTask,
    EvaluationReport,
    TaskResult,
)


@pytest.fixture
def mock_evaluator():
    """Create a BenchmarkEvaluator instance with mocked dependencies."""
    with patch("essence.agents.evaluator.CodingAgent"), patch(
        "essence.agents.evaluator.Sandbox"
    ), patch("essence.agents.evaluator.get_tracer"):
        evaluator = BenchmarkEvaluator(
            llm_url="mock://llm",
            model_name="test-model",
            num_attempts_per_task=1,
        )
        return evaluator


@pytest.fixture
def sample_tasks():
    """Create sample benchmark tasks for testing."""
    return [
        BenchmarkTask(
            task_id="task_1",
            dataset="test",
            prompt="Test task 1",
            test_code="assert True",
        ),
        BenchmarkTask(
            task_id="task_2",
            dataset="test",
            prompt="Test task 2",
            test_code="assert True",
        ),
        BenchmarkTask(
            task_id="task_3",
            dataset="test",
            prompt="Test task 3",
            test_code="assert True",
        ),
    ]


class TestPassAtKCalculation:
    """Tests for pass@k calculation logic."""

    def test_single_attempt_pass_at_1(self, mock_evaluator, sample_tasks):
        """Test pass@1 calculation with single attempt per task."""
        # Create results: 2 out of 3 tasks passed
        results = [
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=True,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=True,
                execution_time_seconds=2.0,
            ),
            TaskResult(
                task_id="task_3",
                dataset="test",
                success=True,
                passed_tests=False,
                execution_time_seconds=1.5,
            ),
        ]

        report = mock_evaluator._generate_report(sample_tasks, results)

        assert report.pass_at_1 == pytest.approx(2.0 / 3.0)
        # For single attempts, pass@5, pass@10, pass@100 should be placeholders (same as pass@1)
        assert report.pass_at_k[5] == pytest.approx(2.0 / 3.0)
        assert report.pass_at_k[10] == pytest.approx(2.0 / 3.0)
        assert report.pass_at_k[100] == pytest.approx(2.0 / 3.0)
        assert report.total_tasks == 3
        assert report.passed_tests == 2

    def test_multiple_attempts_pass_at_1(self):
        """Test pass@1 calculation with multiple attempts per task."""
        evaluator = BenchmarkEvaluator(
            llm_url="mock://llm",
            model_name="test-model",
            num_attempts_per_task=5,
        )

        tasks = [
            BenchmarkTask(
                task_id="task_1",
                dataset="test",
                prompt="Test task 1",
                test_code="assert True",
            ),
            BenchmarkTask(
                task_id="task_2",
                dataset="test",
                prompt="Test task 2",
                test_code="assert True",
            ),
        ]

        # Task 1: 5 attempts, first attempt passes
        # Task 2: 5 attempts, no attempts pass
        results = [
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=True,
                attempt_number=1,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=2,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=3,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=4,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=5,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=1,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=2,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=3,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=4,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=5,
                execution_time_seconds=1.0,
            ),
        ]

        report = evaluator._generate_report(tasks, results)

        # pass@1: 1 out of 2 tasks have at least one passing attempt in first attempt
        assert report.pass_at_1 == pytest.approx(1.0 / 2.0)
        assert report.total_tasks == 2
        assert report.passed_tests == 1  # Only task_1 has at least one passing attempt

    def test_multiple_attempts_pass_at_5(self):
        """Test pass@5 calculation with 5 attempts per task."""
        evaluator = BenchmarkEvaluator(
            llm_url="mock://llm",
            model_name="test-model",
            num_attempts_per_task=5,
        )

        tasks = [
            BenchmarkTask(
                task_id="task_1",
                dataset="test",
                prompt="Test task 1",
                test_code="assert True",
            ),
            BenchmarkTask(
                task_id="task_2",
                dataset="test",
                prompt="Test task 2",
                test_code="assert True",
            ),
            BenchmarkTask(
                task_id="task_3",
                dataset="test",
                prompt="Test task 3",
                test_code="assert True",
            ),
        ]

        # Task 1: 5 attempts, 3rd attempt passes
        # Task 2: 5 attempts, 5th attempt passes
        # Task 3: 5 attempts, no attempts pass
        results = []
        for task_num in [1, 2, 3]:
            for attempt in range(1, 6):
                passed = False
                if task_num == 1 and attempt == 3:
                    passed = True
                elif task_num == 2 and attempt == 5:
                    passed = True

                results.append(
                    TaskResult(
                        task_id=f"task_{task_num}",
                        dataset="test",
                        success=True,
                        passed_tests=passed,
                        attempt_number=attempt,
                        execution_time_seconds=1.0,
                    )
                )

        report = evaluator._generate_report(tasks, results)

        # pass@1: 0 tasks (neither task_1 nor task_2 pass on first attempt)
        assert report.pass_at_1 == pytest.approx(0.0 / 3.0)

        # pass@5: 2 tasks (task_1 and task_2 both have at least one passing attempt in first 5)
        assert report.pass_at_k[5] == pytest.approx(2.0 / 3.0)

        # pass@10 and pass@100 should use pass@5 as best estimate (only 5 attempts available)
        assert report.pass_at_k[10] == pytest.approx(2.0 / 3.0)
        assert report.pass_at_k[100] == pytest.approx(2.0 / 3.0)

        assert report.total_tasks == 3
        assert report.passed_tests == 2

    def test_multiple_attempts_all_passing(self):
        """Test pass@k when all tasks have at least one passing attempt."""
        evaluator = BenchmarkEvaluator(
            llm_url="mock://llm",
            model_name="test-model",
            num_attempts_per_task=3,
        )

        tasks = [
            BenchmarkTask(
                task_id="task_1",
                dataset="test",
                prompt="Test task 1",
                test_code="assert True",
            ),
            BenchmarkTask(
                task_id="task_2",
                dataset="test",
                prompt="Test task 2",
                test_code="assert True",
            ),
        ]

        # Both tasks have at least one passing attempt
        results = [
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=True,
                attempt_number=1,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=2,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=3,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=1,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=True,
                attempt_number=2,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_2",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=3,
                execution_time_seconds=1.0,
            ),
        ]

        report = evaluator._generate_report(tasks, results)

        # pass@1: 1 out of 2 tasks pass on first attempt (task_1 passes, task_2 doesn't)
        assert report.pass_at_1 == pytest.approx(1.0 / 2.0)  # 0.5
        # pass@3: Both tasks pass within 3 attempts
        assert report.pass_at_k[5] == pytest.approx(
            1.0
        )  # Both tasks pass within available attempts
        assert report.pass_at_k[100] == pytest.approx(1.0)
        assert report.total_tasks == 2
        assert report.passed_tests == 2  # Both tasks have at least one passing attempt

    def test_multiple_attempts_all_failing(self):
        """Test pass@k when no tasks have any passing attempts."""
        evaluator = BenchmarkEvaluator(
            llm_url="mock://llm",
            model_name="test-model",
            num_attempts_per_task=5,
        )

        tasks = [
            BenchmarkTask(
                task_id="task_1",
                dataset="test",
                prompt="Test task 1",
                test_code="assert True",
            ),
        ]

        # All attempts fail
        results = [
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=i,
                execution_time_seconds=1.0,
            )
            for i in range(1, 6)
        ]

        report = evaluator._generate_report(tasks, results)

        # No passing attempts
        assert report.pass_at_1 == pytest.approx(0.0)
        assert report.pass_at_k[5] == pytest.approx(0.0)
        assert report.total_tasks == 1
        assert report.passed_tests == 0

    def test_empty_results_raises_error(self, mock_evaluator, sample_tasks):
        """Test that empty results raise ValueError."""
        with pytest.raises(ValueError, match="No results to generate report from"):
            mock_evaluator._generate_report(sample_tasks, [])

    def test_attempt_number_tracking(self):
        """Test that attempt_number is properly tracked in TaskResult."""
        result = TaskResult(
            task_id="task_1",
            dataset="test",
            success=True,
            passed_tests=True,
            attempt_number=3,
            execution_time_seconds=1.0,
        )

        assert result.attempt_number == 3
        assert result.task_id == "task_1"
        assert result.passed_tests is True

    def test_single_attempt_no_attempt_number(self):
        """Test that single attempts don't set attempt_number."""
        result = TaskResult(
            task_id="task_1",
            dataset="test",
            success=True,
            passed_tests=True,
            attempt_number=None,
            execution_time_seconds=1.0,
        )

        assert result.attempt_number is None

    def test_pass_at_k_with_insufficient_attempts(self):
        """Test pass@k when k > num_attempts_per_task."""
        evaluator = BenchmarkEvaluator(
            llm_url="mock://llm",
            model_name="test-model",
            num_attempts_per_task=3,  # Only 3 attempts
        )

        tasks = [
            BenchmarkTask(
                task_id="task_1",
                dataset="test",
                prompt="Test task 1",
                test_code="assert True",
            ),
        ]

        # Task passes on 2nd attempt
        results = [
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=1,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=True,
                attempt_number=2,
                execution_time_seconds=1.0,
            ),
            TaskResult(
                task_id="task_1",
                dataset="test",
                success=True,
                passed_tests=False,
                attempt_number=3,
                execution_time_seconds=1.0,
            ),
        ]

        report = evaluator._generate_report(tasks, results)

        # pass@1: 0 (doesn't pass on first attempt)
        assert report.pass_at_1 == pytest.approx(0.0)

        # pass@5 and pass@100: Use best available estimate (pass@1, which is 0.0 since it doesn't pass on first attempt)
        # Actually, wait - it passes on attempt 2, so within 5 attempts it should pass
        # But we only calculate for k in [1, 5, 10, 100], and since k=3 isn't in that list,
        # we need to check pass@5 which should be 1.0 (passes within 5 attempts)
        assert report.pass_at_k[5] == pytest.approx(1.0)
        assert report.pass_at_k[100] == pytest.approx(1.0)
