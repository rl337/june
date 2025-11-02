"""
Integration Tests for TODO Service Integration

Tests agent interaction with TODO MCP Service.
"""

import pytest
from tests.agentic.simulation.mock_task_service import (
    MockTaskService, TaskType, TaskStatus
)


class TestTodoServiceIntegration:
    """Tests for TODO service integration."""
    
    @pytest.fixture
    def mock_service(self):
        """Create mock TODO service."""
        service = MockTaskService()
        # Create test project
        project = service.create_project(
            name="Test Project",
            description="Test project for integration tests",
            origin_url="https://test.com",
            local_path="/tmp/test-project"
        )
        return service, project
    
    def test_agent_can_list_available_tasks(self, mock_service):
        """Test that agent can list available tasks."""
        service, project = mock_service
        
        # Create some tasks
        task1 = service.create_task(
            project_id=project.id,
            title="Task 1",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        task2 = service.create_task(
            project_id=project.id,
            title="Task 2",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something else",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        # List available tasks
        available = service.list_available_tasks(
            agent_type="implementation",
            project_id=project.id
        )
        
        assert len(available) == 2
        assert task1.id in [t.id for t in available]
        assert task2.id in [t.id for t in available]
    
    def test_agent_can_reserve_task(self, mock_service):
        """Test that agent can reserve tasks."""
        service, project = mock_service
        
        task = service.create_task(
            project_id=project.id,
            title="Reservable Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        # Reserve task
        context = service.reserve_task(task_id=task.id, agent_id="agent-1")
        
        assert context["success"] is True
        assert context["task"]["task_status"] == TaskStatus.IN_PROGRESS.value
        assert context["task"]["assigned_agent"] == "agent-1"
        
        # Verify task is locked
        task_updated = service.tasks[task.id]
        assert task_updated.task_status == TaskStatus.IN_PROGRESS
        assert task_updated.assigned_agent == "agent-1"
    
    def test_agent_can_add_progress_updates(self, mock_service):
        """Test that agent can add progress updates."""
        service, project = mock_service
        
        task = service.create_task(
            project_id=project.id,
            title="Task with Updates",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        service.reserve_task(task_id=task.id, agent_id="agent-1")
        
        # Add progress update
        result = service.add_task_update(
            task_id=task.id,
            agent_id="agent-1",
            content="Making progress",
            update_type="progress"
        )
        
        assert result["success"] is True
        
        # Verify update was added
        context = service.get_task_context(task.id)
        assert len(context["updates"]) == 1
        assert context["updates"][0]["content"] == "Making progress"
    
    def test_agent_can_complete_task(self, mock_service):
        """Test that agent can complete tasks."""
        service, project = mock_service
        
        task = service.create_task(
            project_id=project.id,
            title="Completable Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        service.reserve_task(task_id=task.id, agent_id="agent-1")
        
        # Complete task
        result = service.complete_task(
            task_id=task.id,
            agent_id="agent-1",
            notes="Completed successfully"
        )
        
        assert result["success"] is True
        
        # Verify task is completed
        task_updated = service.tasks[task.id]
        assert task_updated.task_status == TaskStatus.COMPLETE
        assert task_updated.completed_at is not None
        assert task_updated.notes == "Completed successfully"
    
    def test_agent_can_unlock_task(self, mock_service):
        """Test that agent can unlock tasks."""
        service, project = mock_service
        
        task = service.create_task(
            project_id=project.id,
            title="Unlockable Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        service.reserve_task(task_id=task.id, agent_id="agent-1")
        
        # Unlock task
        result = service.unlock_task(task_id=task.id, agent_id="agent-1")
        
        assert result["success"] is True
        
        # Verify task is unlocked
        task_updated = service.tasks[task.id]
        assert task_updated.task_status == TaskStatus.AVAILABLE
        assert task_updated.assigned_agent is None
    
    def test_agent_can_query_tasks(self, mock_service):
        """Test that agent can query tasks by status."""
        service, project = mock_service
        
        # Create tasks in different states
        task1 = service.create_task(
            project_id=project.id,
            title="Task 1",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        task2 = service.create_task(
            project_id=project.id,
            title="Task 2",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        # Reserve one task
        service.reserve_task(task_id=task1.id, agent_id="agent-1")
        
        # Query in-progress tasks
        in_progress = service.query_tasks(
            task_status="in_progress",
            agent_id="agent-1"
        )
        
        assert len(in_progress) == 1
        assert in_progress[0].id == task1.id
        
        # Query available tasks
        available = service.query_tasks(task_status="available")
        
        assert len(available) == 1
        assert available[0].id == task2.id
    
    def test_agent_can_handle_concurrent_reservations(self, mock_service):
        """Test that concurrent reservations are handled correctly."""
        service, project = mock_service
        
        task = service.create_task(
            project_id=project.id,
            title="Concurrent Task",
            task_type=TaskType.CONCRETE,
            task_instruction="Do something",
            verification_instruction="Verify it works",
            agent_id="test-agent"
        )
        
        # First agent reserves
        service.reserve_task(task_id=task.id, agent_id="agent-1")
        
        # Second agent tries to reserve (should fail)
        with pytest.raises(ValueError, match="not available"):
            service.reserve_task(task_id=task.id, agent_id="agent-2")
