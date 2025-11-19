"""
Integration Tests for Code Execution Integration

Tests agent interaction with code execution environment.
"""

import pytest

from tests.agentic.simulation.mock_execution import (
    ExecutionSimulator,
    MockExecutionEnvironment,
)
from tests.agentic.simulation.mock_git import GitSimulator, MockGit


class TestCodeExecutionIntegration:
    """Tests for code execution integration."""

    @pytest.fixture
    def mock_env(self):
        """Create mock execution environment."""
        env = ExecutionSimulator.create_mock_env()
        yield env
        env.cleanup()

    def test_agent_can_execute_python_code(self, mock_env):
        """Test that agent can execute Python code."""
        # Write test file
        mock_env.write_file("test_script.py", 'print("Hello, World!")')

        # Execute
        result = mock_env.execute_command("python test_script.py")

        assert result.success is True
        assert "Hello, World!" in result.stdout

    def test_agent_can_run_tests(self, mock_env):
        """Test that agent can run test suites."""
        # Write test file
        mock_env.write_file(
            "test_feature.py",
            """
def test_feature():
    assert True
""",
        )

        # Execute tests
        result = mock_env.execute_command("pytest test_feature.py")

        assert result.success is True
        assert "PASSED" in result.stdout

    def test_agent_can_read_files(self, mock_env):
        """Test that agent can read files."""
        content = "Test file content"
        mock_env.write_file("test.txt", content)

        # Read file
        read_content = mock_env.read_file("test.txt")

        assert read_content == content

    def test_agent_can_write_files(self, mock_env):
        """Test that agent can write files."""
        content = "New file content"
        mock_env.write_file("new_file.txt", content)

        # Verify file was written
        read_content = mock_env.read_file("new_file.txt")
        assert read_content == content


class TestGitIntegration:
    """Tests for git operations integration."""

    @pytest.fixture
    def mock_git(self):
        """Create mock git repository."""
        git = GitSimulator.create_mock_repo()
        yield git
        git.cleanup()

    def test_agent_can_check_git_status(self, mock_git):
        """Test that agent can check git status."""
        mock_git.set_status("M  modified_file.py")

        status = mock_git.status_short()

        assert "modified_file.py" in status

    def test_agent_can_commit_changes(self, mock_git):
        """Test that agent can commit changes."""
        result = mock_git.commit("Add new feature")

        assert result is True
        assert len(mock_git.commits) == 1
        assert mock_git.commits[0]["message"] == "Add new feature"

    def test_agent_validates_commit_messages(self, mock_git):
        """Test that agent validates commit messages."""
        # Empty message should fail
        result = mock_git.commit("")
        assert result is False

        # Short message should fail
        result = mock_git.commit("ab")
        assert result is False

        # Valid message should succeed
        result = mock_git.commit("Add comprehensive feature")
        assert result is True

    def test_agent_can_push_changes(self, mock_git):
        """Test that agent can push changes."""
        result = mock_git.push("origin", "main")

        assert result is True
        assert "git push" in " ".join(mock_git.commands)

    def test_agent_can_checkout_branches(self, mock_git):
        """Test that agent can checkout branches."""
        result = mock_git.checkout("feature-branch", create=True)

        assert result is True
        assert mock_git.current_branch == "feature-branch"
        assert "feature-branch" in mock_git.branches


class TestEndToEndWorkflow:
    """Tests for end-to-end agent workflows."""

    @pytest.fixture
    def full_setup(self):
        """Create complete test setup."""
        from tests.agentic.simulation.mock_task_service import MockTaskService, TaskType

        # Setup task service
        service = MockTaskService()
        project = service.create_project(
            name="E2E Project",
            description="End-to-end test project",
            origin_url="https://test.com",
            local_path="/tmp/e2e-project",
        )

        # Setup execution environment
        env = ExecutionSimulator.create_mock_env(base_path="/tmp/e2e-project")

        # Setup git
        git = GitSimulator.create_mock_repo(repo_path="/tmp/e2e-project")

        yield service, project, env, git

        # Cleanup
        env.cleanup()
        git.cleanup()

    def test_complete_task_workflow(self, full_setup):
        """Test complete workflow from task creation to completion."""
        service, project, env, git = full_setup

        # 1. Create task
        task = service.create_task(
            project_id=project.id,
            title="Implement feature",
            task_type=TaskType.CONCRETE,
            task_instruction="Create test.py file with hello function",
            verification_instruction="Run python test.py",
            agent_id="test-agent",
        )

        # 2. Reserve task
        context = service.reserve_task(task_id=task.id, agent_id="agent-1")
        assert context["success"] is True

        # 3. Execute task (create file)
        env.write_file(
            "test.py",
            """
def hello():
    print("Hello, World!")

if __name__ == "__main__":
    hello()
""",
        )

        # 4. Run verification
        result = env.execute_command("python test.py")
        assert result.success is True
        assert "Hello, World!" in result.stdout

        # 5. Commit changes
        git.commit("Add test.py with hello function")

        # 6. Add progress update
        service.add_task_update(
            task_id=task.id,
            agent_id="agent-1",
            content="Created test.py file and verified it works",
            update_type="progress",
        )

        # 7. Complete task
        service.complete_task(
            task_id=task.id,
            agent_id="agent-1",
            notes="Successfully implemented and verified",
        )

        # Verify task is completed
        task_updated = service.tasks[task.id]
        assert task_updated.task_status.value == "complete"
