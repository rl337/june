"""
Performance Tests for Agent Capabilities

Tests agent performance, resource usage, and scalability.
"""

import pytest
import time
from typing import Dict, Any


class TestAgentPerformance:
    """Tests for agent performance metrics."""

    def test_task_reservation_performance(self):
        """Test that task reservation is fast."""
        from tests.agentic.simulation.mock_task_service import MockTaskService, TaskType

        service = MockTaskService()
        project = service.create_project(
            name="Perf Test",
            description="Performance test",
            origin_url="https://test.com",
            local_path="/tmp/perf",
        )

        task = service.create_task(
            project_id=project.id,
            title="Test Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it",
            agent_id="test-agent",
        )

        # Measure reservation time
        start = time.time()
        service.reserve_task(task_id=task.id, agent_id="agent-1")
        elapsed = time.time() - start

        # Should be very fast (< 100ms)
        assert elapsed < 0.1

    def test_concurrent_task_processing(self):
        """Test performance with concurrent task processing."""
        from tests.agentic.simulation.mock_task_service import MockTaskService, TaskType
        import threading

        service = MockTaskService()
        project = service.create_project(
            name="Concurrent Test",
            description="Concurrent processing test",
            origin_url="https://test.com",
            local_path="/tmp/concurrent",
        )

        # Create multiple tasks
        tasks = []
        for i in range(10):
            task = service.create_task(
                project_id=project.id,
                title=f"Task {i}",
                task_type=TaskType.CONCRETE,
                task_instruction="Do something",
                verification_instruction="Verify it",
                agent_id="test-agent",
            )
            tasks.append(task)

        # Process tasks concurrently
        def process_task(task_id):
            try:
                service.reserve_task(task_id=task_id, agent_id=f"agent-{task_id}")
                time.sleep(0.01)  # Simulate work
                service.complete_task(task_id=task_id, agent_id=f"agent-{task_id}")
            except ValueError:
                pass  # Task already reserved

        start = time.time()
        threads = []
        for task in tasks:
            thread = threading.Thread(target=process_task, args=(task.id,))
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        elapsed = time.time() - start

        # Concurrent processing should be faster than sequential
        # (though with locks it might not be much faster)
        assert elapsed < 1.0  # Should complete quickly

    def test_task_context_retrieval_performance(self):
        """Test that task context retrieval is fast."""
        from tests.agentic.simulation.mock_task_service import MockTaskService, TaskType

        service = MockTaskService()
        project = service.create_project(
            name="Context Test",
            description="Context retrieval test",
            origin_url="https://test.com",
            local_path="/tmp/context",
        )

        task = service.create_task(
            project_id=project.id,
            title="Context Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it",
            agent_id="test-agent",
        )

        # Add many updates
        for i in range(100):
            service.add_task_update(
                task_id=task.id,
                agent_id="agent-1",
                content=f"Update {i}",
                update_type="progress",
            )

        # Measure context retrieval
        start = time.time()
        context = service.get_task_context(task.id)
        elapsed = time.time() - start

        # Should handle many updates efficiently (< 500ms)
        assert elapsed < 0.5
        assert len(context["updates"]) == 100


class TestResourceUsage:
    """Tests for resource usage profiling."""

    def test_memory_usage_is_reasonable(self):
        """Test that agent operations don't use excessive memory."""
        import sys
        from tests.agentic.simulation.mock_task_service import MockTaskService, TaskType

        service = MockTaskService()
        project = service.create_project(
            name="Memory Test",
            description="Memory usage test",
            origin_url="https://test.com",
            local_path="/tmp/memory",
        )

        # Create many tasks
        initial_size = sys.getsizeof(service.tasks)

        for i in range(1000):
            service.create_task(
                project_id=project.id,
                title=f"Task {i}",
                task_type=TaskType.CONCRETE,
                task_instruction="Do something",
                verification_instruction="Verify it",
                agent_id="test-agent",
            )

        final_size = sys.getsizeof(service.tasks)

        # Memory usage should be reasonable (less than 10MB for 1000 tasks)
        size_increase = final_size - initial_size
        assert size_increase < 10 * 1024 * 1024  # 10MB


class TestScalability:
    """Tests for system scalability."""

    def test_handles_many_tasks(self):
        """Test that system can handle many tasks."""
        from tests.agentic.simulation.mock_task_service import MockTaskService, TaskType

        service = MockTaskService()
        project = service.create_project(
            name="Scale Test",
            description="Scalability test",
            origin_url="https://test.com",
            local_path="/tmp/scale",
        )

        # Create many tasks
        tasks = []
        for i in range(1000):
            task = service.create_task(
                project_id=project.id,
                title=f"Task {i}",
                task_type=TaskType.CONCRETE,
                task_instruction="Do something",
                verification_instruction="Verify it",
                agent_id="test-agent",
            )
            tasks.append(task)

        # List available tasks should still be fast
        start = time.time()
        available = service.list_available_tasks(agent_type="implementation", limit=100)
        elapsed = time.time() - start

        assert len(available) == 100
        assert elapsed < 1.0  # Should be fast even with 1000 tasks
