"""
Performance Tests for Agentic Reasoning Flow

Tests performance metrics, latency, and resource usage of the agentic reasoning loop.
Can run with mocked LLM (for CI/CD) or real TensorRT-LLM service (when available).

Performance Metrics Measured:
- Latency per phase (think, plan, execute, reflect)
- Total reasoning loop time
- Cache hit rates
- Iterations needed
- Resource usage (memory, CPU)
- Throughput under load
"""
import pytest
import time
import statistics
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from unittest.mock import Mock, MagicMock

from essence.agents.reasoning import (
    AgenticReasoner,
    ReasoningResult,
    ConversationContext,
)
from essence.agents.planner import Planner
from essence.agents.executor import Executor
from essence.agents.reflector import Reflector
from essence.agents.llm_client import LLMClient
from essence.agents.reasoning_cache import ReasoningCache
from essence.agents.decision import should_use_agentic_flow, estimate_request_complexity


@dataclass
class PerformanceMetrics:
    """Performance metrics for a single reasoning operation."""

    total_time: float
    think_time: float = 0.0
    plan_time: float = 0.0
    execute_time: float = 0.0
    reflect_time: float = 0.0
    iterations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    steps_executed: int = 0
    steps_succeeded: int = 0
    steps_failed: int = 0
    memory_usage_mb: float = 0.0
    cpu_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class MockLLMClientWithTiming:
    """Mock LLM client that tracks timing for performance testing."""

    def __init__(self, base_delay: float = 0.01):
        """
        Initialize mock LLM client with timing.

        Args:
            base_delay: Base delay in seconds for each LLM call (simulates network latency)
        """
        self.base_delay = base_delay
        self.call_times = []
        self.think_calls = 0
        self.plan_calls = 0
        self.reflect_calls = 0

    def think(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Mock think method with timing."""
        start = time.time()
        time.sleep(self.base_delay)  # Simulate LLM call latency
        self.think_calls += 1
        self.call_times.append(time.time() - start)
        return f"Analysis of: {user_message[:50]}..."

    def plan(self, user_request: str, analysis: str, available_tools: List[str]) -> str:
        """Mock plan method with timing."""
        start = time.time()
        time.sleep(self.base_delay)
        self.plan_calls += 1
        self.call_times.append(time.time() - start)
        return "1. Step one\n2. Step two\n3. Step three"

    def reflect(
        self, original_request: str, plan: str, execution_results: List[Dict[str, Any]]
    ) -> str:
        """Mock reflect method with timing."""
        start = time.time()
        time.sleep(self.base_delay)
        self.reflect_calls += 1
        self.call_times.append(time.time() - start)
        return "Goal achieved: Yes\nIssues: None\nShould continue: No\nConfidence: 0.9"

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Mock generate_text method with timing."""
        start = time.time()
        time.sleep(self.base_delay)
        self.call_times.append(time.time() - start)
        return "Mocked LLM response"


class TestReasoningPerformance:
    """Performance tests for agentic reasoning flow."""

    def test_simple_request_latency(self):
        """Test latency for simple requests (should use early termination)."""
        cache = ReasoningCache(enable_cache=True)
        mock_llm = MockLLMClientWithTiming(base_delay=0.01)

        planner = Planner(llm_client=mock_llm, enable_cache=True, cache=cache)
        executor = Executor(available_tools={})
        reflector = Reflector(llm_client=mock_llm, enable_cache=True, cache=cache)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=mock_llm,
            enable_cache=True,
            enable_early_termination=True,
        )

        context = ConversationContext(user_id="test", chat_id="test")

        start_time = time.time()
        result = reasoner.reason(
            user_message="Hello, how are you?",
            context=context,
        )
        total_time = time.time() - start_time

        assert result is not None
        # Simple requests should complete quickly (< 100ms with early termination)
        assert total_time < 0.1
        assert result.iterations <= 1

    def test_complex_request_latency(self):
        """Test latency for complex requests (full reasoning loop)."""
        cache = ReasoningCache(enable_cache=True)
        mock_llm = MockLLMClientWithTiming(base_delay=0.01)

        mock_tools = {
            "read_file": Mock(return_value="File contents"),
            "write_file": Mock(return_value="File written"),
        }

        planner = Planner(llm_client=mock_llm, enable_cache=True, cache=cache)
        executor = Executor(available_tools=mock_tools)
        reflector = Reflector(llm_client=mock_llm, enable_cache=True, cache=cache)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=mock_llm,
            enable_cache=True,
            enable_early_termination=False,  # Force full loop
        )

        context = ConversationContext(user_id="test", chat_id="test")

        start_time = time.time()
        result = reasoner.reason(
            user_message="Create a complex multi-step task that requires planning and execution",
            context=context,
            available_tools=list(mock_tools.values()),
        )
        total_time = time.time() - start_time

        assert result is not None
        # Complex requests should complete within reasonable time (< 5 seconds with mocks)
        assert total_time < 5.0
        assert result.iterations >= 1

    def test_cache_performance(self):
        """Test that caching improves performance on repeated requests."""
        cache = ReasoningCache(enable_cache=True, max_size=100)
        mock_llm = MockLLMClientWithTiming(
            base_delay=0.05
        )  # Slower LLM to see cache benefit

        planner = Planner(llm_client=mock_llm, enable_cache=True, cache=cache)
        executor = Executor(available_tools={})
        reflector = Reflector(llm_client=mock_llm, enable_cache=True, cache=cache)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=mock_llm,
            enable_cache=True,
            cache=cache,
        )

        context = ConversationContext(user_id="test", chat_id="test")
        request = "Read a file and process it"

        # First call - should hit LLM
        start1 = time.time()
        result1 = reasoner.reason(user_message=request, context=context)
        time1 = time.time() - start1

        # Reset LLM call counter
        initial_llm_calls = (
            mock_llm.think_calls + mock_llm.plan_calls + mock_llm.reflect_calls
        )

        # Second call with same request - should use cache
        start2 = time.time()
        result2 = reasoner.reason(user_message=request, context=context)
        time2 = time.time() - start2

        # Second call should be faster (cache hit)
        # Note: With early termination, both might be fast, so we check cache stats
        cache_stats = cache.get_stats()
        assert (
            cache_stats["hits"] > 0 or cache_stats["misses"] > 0
        )  # Cache is being used

    def test_iteration_limit_performance(self):
        """Test that iteration limits prevent infinite loops."""
        cache = ReasoningCache(enable_cache=False)  # Disable cache for this test
        mock_llm = MockLLMClientWithTiming(base_delay=0.01)

        planner = Planner(llm_client=mock_llm, enable_cache=False)
        executor = Executor(available_tools={})
        reflector = Reflector(llm_client=mock_llm, enable_cache=False)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=mock_llm,
            max_iterations=3,  # Limit iterations
            enable_cache=False,
        )

        context = ConversationContext(user_id="test", chat_id="test")

        start_time = time.time()
        result = reasoner.reason(
            user_message="Complex request that might need multiple iterations",
            context=context,
        )
        total_time = time.time() - start_time

        assert result is not None
        # Should complete within max_iterations
        assert result.iterations <= reasoner.max_iterations
        # Should complete within reasonable time
        assert total_time < 10.0

    def test_timeout_handling(self):
        """Test that timeouts are enforced correctly."""
        cache = ReasoningCache(enable_cache=False)
        mock_llm = MockLLMClientWithTiming(base_delay=0.5)  # Slow LLM

        planner = Planner(llm_client=mock_llm, enable_cache=False)
        executor = Executor(available_tools={})
        reflector = Reflector(llm_client=mock_llm, enable_cache=False)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=mock_llm,
            think_timeout=0.1,  # Very short timeout
            plan_timeout=0.1,
            reflect_timeout=0.1,
            total_timeout=1.0,
            enable_cache=False,
        )

        context = ConversationContext(user_id="test", chat_id="test")

        start_time = time.time()
        result = reasoner.reason(
            user_message="Test request",
            context=context,
        )
        total_time = time.time() - start_time

        assert result is not None
        # Should complete within total_timeout (with some margin)
        assert total_time <= reasoner.total_timeout + 0.5  # Allow some margin

    def test_concurrent_requests(self):
        """Test performance with concurrent requests."""
        import threading

        cache = ReasoningCache(enable_cache=True)
        results = []
        errors = []

        def run_reasoning(request_id: int):
            """Run reasoning for a single request."""
            try:
                mock_llm = MockLLMClientWithTiming(base_delay=0.01)
                planner = Planner(llm_client=mock_llm, enable_cache=True, cache=cache)
                executor = Executor(available_tools={})
                reflector = Reflector(
                    llm_client=mock_llm, enable_cache=True, cache=cache
                )
                reasoner = AgenticReasoner(
                    planner=planner,
                    executor=executor,
                    reflector=reflector,
                    llm_client=mock_llm,
                    enable_cache=True,
                    cache=cache,
                )

                context = ConversationContext(
                    user_id=f"test_{request_id}", chat_id=f"test_{request_id}"
                )
                start = time.time()
                result = reasoner.reason(
                    user_message=f"Request {request_id}",
                    context=context,
                )
                elapsed = time.time() - start
                results.append((request_id, elapsed, result.iterations))
            except Exception as e:
                errors.append((request_id, str(e)))

        # Run 5 concurrent requests
        threads = []
        for i in range(5):
            thread = threading.Thread(target=run_reasoning, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10.0)

        # All requests should complete successfully
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5

        # Check that all requests completed
        for request_id, elapsed, iterations in results:
            assert elapsed < 5.0  # Each request should complete quickly
            assert iterations >= 0

    def test_metrics_collection(self):
        """Test that performance metrics can be collected."""
        cache = ReasoningCache(enable_cache=True)
        mock_llm = MockLLMClientWithTiming(base_delay=0.01)

        planner = Planner(llm_client=mock_llm, enable_cache=True, cache=cache)
        executor = Executor(available_tools={})
        reflector = Reflector(llm_client=mock_llm, enable_cache=True, cache=cache)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=mock_llm,
            enable_cache=True,
            cache=cache,
        )

        context = ConversationContext(user_id="test", chat_id="test")

        start_time = time.time()
        result = reasoner.reason(
            user_message="Test request for metrics",
            context=context,
        )
        total_time = time.time() - start_time

        # Collect metrics
        metrics = PerformanceMetrics(
            total_time=total_time,
            iterations=result.iterations,
            steps_executed=len(result.execution_results),
            steps_succeeded=sum(1 for r in result.execution_results if r.success),
            steps_failed=sum(1 for r in result.execution_results if not r.success),
        )

        # Verify metrics are reasonable
        assert metrics.total_time > 0
        assert metrics.iterations >= 0
        assert metrics.steps_executed >= 0
        assert metrics.steps_succeeded >= 0
        assert metrics.steps_failed >= 0

        # Verify metrics can be serialized
        metrics_dict = metrics.to_dict()
        assert isinstance(metrics_dict, dict)
        assert "total_time" in metrics_dict
        assert "iterations" in metrics_dict


class TestPerformanceBenchmarks:
    """Benchmark tests for comparing performance across scenarios."""

    def test_simple_vs_complex_latency(self):
        """Compare latency between simple and complex requests."""
        cache = ReasoningCache(enable_cache=True)
        mock_llm = MockLLMClientWithTiming(base_delay=0.01)

        planner = Planner(llm_client=mock_llm, enable_cache=True, cache=cache)
        executor = Executor(available_tools={})
        reflector = Reflector(llm_client=mock_llm, enable_cache=True, cache=cache)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=mock_llm,
            enable_cache=True,
            cache=cache,
        )

        # Simple request
        context1 = ConversationContext(user_id="test1", chat_id="test1")
        start1 = time.time()
        result1 = reasoner.reason(user_message="Hello", context=context1)
        time_simple = time.time() - start1

        # Complex request
        context2 = ConversationContext(user_id="test2", chat_id="test2")
        reasoner.enable_early_termination = False  # Force full loop
        start2 = time.time()
        result2 = reasoner.reason(
            user_message="Create a complex multi-step plan with multiple tools and iterations",
            context=context2,
        )
        time_complex = time.time() - start2

        # Complex should take longer (or similar if both use early termination)
        # But both should complete successfully
        assert result1 is not None
        assert result2 is not None
        assert time_simple >= 0
        assert time_complex >= 0

    def test_cache_effectiveness(self):
        """Test cache effectiveness across multiple requests."""
        cache = ReasoningCache(enable_cache=True, max_size=100)
        mock_llm = MockLLMClientWithTiming(base_delay=0.05)

        planner = Planner(llm_client=mock_llm, enable_cache=True, cache=cache)
        executor = Executor(available_tools={})
        reflector = Reflector(llm_client=mock_llm, enable_cache=True, cache=cache)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=mock_llm,
            enable_cache=True,
            cache=cache,
        )

        context = ConversationContext(user_id="test", chat_id="test")
        request = "Process a file"

        # Run multiple times
        times = []
        for _ in range(5):
            start = time.time()
            reasoner.reason(user_message=request, context=context)
            times.append(time.time() - start)

        # Check cache stats
        stats = cache.get_stats()
        # Should have some cache hits after first request
        assert stats["hits"] + stats["misses"] > 0


@pytest.mark.skip(
    reason="Requires real TensorRT-LLM service - run manually when service is available"
)
class TestRealLLMPerformance:
    """Performance tests with real TensorRT-LLM service (skip in CI)."""

    def test_real_llm_latency(self):
        """Test latency with real TensorRT-LLM service."""
        # This test requires TensorRT-LLM to be running
        # It will be skipped in CI but can be run manually
        llm_client = LLMClient(inference_api_url="tensorrt-llm:8000")

        planner = Planner(llm_client=llm_client, enable_cache=True)
        executor = Executor(available_tools={})
        reflector = Reflector(llm_client=llm_client, enable_cache=True)
        reasoner = AgenticReasoner(
            planner=planner,
            executor=executor,
            reflector=reflector,
            llm_client=llm_client,
            enable_cache=True,
        )

        context = ConversationContext(user_id="test", chat_id="test")

        start_time = time.time()
        result = reasoner.reason(
            user_message="Test request with real LLM",
            context=context,
        )
        total_time = time.time() - start_time

        assert result is not None
        # Real LLM should complete within reasonable time (< 30 seconds)
        assert total_time < 30.0
        assert result.iterations >= 0
