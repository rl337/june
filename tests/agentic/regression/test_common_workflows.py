"""
Regression Tests for Common Agent Workflows

Tests to ensure existing capabilities still work.
"""

import pytest

from tests.agentic.simulation.mock_execution import ExecutionSimulator
from tests.agentic.simulation.mock_git import GitSimulator
from tests.agentic.simulation.mock_task_service import (
    MockTaskService,
    TaskStatus,
    TaskType,
)


class TestCommonWorkflows:
    """Tests for common agent workflows."""

    @pytest.fixture
    def setup(self):
        """Setup test environment."""
        service = MockTaskService()
        project = service.create_project(
            name="Regression Test Project",
            description="Regression test project",
            origin_url="https://test.com",
            local_path="/tmp/regression",
        )
        env = ExecutionSimulator.create_mock_env()
        git = GitSimulator.create_mock_repo()

        yield service, project, env, git

        env.cleanup()
        git.cleanup()

    def test_basic_task_workflow(self, setup):
        """Test basic task workflow: create -> reserve -> update -> complete."""
        service, project, env, git = setup

        # Create task
        task = service.create_task(
            project_id=project.id,
            title="Basic Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something simple",
            verification_instruction="Verify it works",
            agent_id="test-agent",
        )

        # Reserve
        context = service.reserve_task(task_id=task.id, agent_id="agent-1")
        assert context["success"] is True

        # Update
        service.add_task_update(
            task_id=task.id,
            agent_id="agent-1",
            content="Working on it",
            update_type="progress",
        )

        # Complete
        service.complete_task(task_id=task.id, agent_id="agent-1", notes="Done")

        # Verify
        task_updated = service.tasks[task.id]
        assert task_updated.task_status == TaskStatus.COMPLETE

    def test_task_with_git_operations(self, setup):
        """Test workflow with git operations."""
        service, project, env, git = setup

        task = service.create_task(
            project_id=project.id,
            title="Git Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Make changes and commit",
            verification_instruction="Verify commit",
            agent_id="test-agent",
        )

        service.reserve_task(task_id=task.id, agent_id="agent-1")

        # Make changes
        env.write_file("new_file.py", "print('hello')")

        # Commit
        git.commit("Add new_file.py")

        # Verify commit
        assert len(git.commits) == 1

        # Complete
        service.complete_task(task_id=task.id, agent_id="agent-1")

        assert service.tasks[task.id].task_status == TaskStatus.COMPLETE

    def test_task_with_test_execution(self, setup):
        """Test workflow with test execution."""
        service, project, env, git = setup

        task = service.create_task(
            project_id=project.id,
            title="Test Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Write and test code",
            verification_instruction="Run tests",
            agent_id="test-agent",
        )

        service.reserve_task(task_id=task.id, agent_id="agent-1")

        # Write code and tests
        env.write_file("code.py", "def add(a, b): return a + b")
        env.write_file(
            "test_code.py",
            """
def test_add():
    assert add(1, 2) == 3
""",
        )

        # Run tests
        result = env.execute_command("pytest test_code.py")

        assert result.success is True

        # Complete
        service.complete_task(task_id=task.id, agent_id="agent-1")

    def test_task_unlock_on_error(self, setup):
        """Test that tasks are unlocked on error."""
        service, project, env, git = setup

        task = service.create_task(
            project_id=project.id,
            title="Error Task",
            task_type=TaskType.CONCRETE,
            task_instruction="This will fail",
            verification_instruction="Verify failure handling",
            agent_id="test-agent",
        )

        service.reserve_task(task_id=task.id, agent_id="agent-1")

        # Simulate error
        service.add_task_update(
            task_id=task.id,
            agent_id="agent-1",
            content="Encountered error, unlocking task",
            update_type="blocker",
        )

        # Unlock
        service.unlock_task(task_id=task.id, agent_id="agent-1")

        # Verify unlocked
        task_updated = service.tasks[task.id]
        assert task_updated.task_status == TaskStatus.AVAILABLE
        assert task_updated.assigned_agent is None

    def test_multiple_agents_coordination(self, setup):
        """Test that multiple agents can work without conflicts."""
        service, project, env, git = setup

        # Create multiple tasks
        tasks = []
        for i in range(5):
            task = service.create_task(
                project_id=project.id,
                title=f"Task {i}",
                task_type=TaskType.CONCRETE,
                task_instruction="Do something",
                verification_instruction="Verify it",
                agent_id="test-agent",
            )
            tasks.append(task)

        # Agents reserve different tasks
        service.reserve_task(task_id=tasks[0].id, agent_id="agent-1")
        service.reserve_task(task_id=tasks[1].id, agent_id="agent-2")
        service.reserve_task(task_id=tasks[2].id, agent_id="agent-3")

        # Verify no conflicts
        assert service.tasks[tasks[0].id].assigned_agent == "agent-1"
        assert service.tasks[tasks[1].id].assigned_agent == "agent-2"
        assert service.tasks[tasks[2].id].assigned_agent == "agent-3"

        # Verify other tasks are still available
        available = service.query_tasks(task_status="available")
        assert len(available) == 2
