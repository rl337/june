"""
Tests for agent state models.
"""
import json
import pytest
from datetime import datetime
from typing import Any, Dict

from june_agent_state.models import (
    AgentState,
    AgentStatus,
    AgentCapabilities,
    AgentMetrics,
    AgentExecutionRecord,
    AgentExecutionOutcome,
    AgentPlan,
)


class TestAgentStatus:
    """Tests for AgentStatus enum."""

    def test_status_values(self):
        """Test that status enum has correct values."""
        assert AgentStatus.INIT == "init"
        assert AgentStatus.ACTIVE == "active"
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.ERROR == "error"


class TestAgentState:
    """Tests for AgentState model."""

    def test_agent_state_creation(self):
        """Test creating AgentState with required fields."""
        state = AgentState(
            agent_id="test-agent-1",
            current_task_id="task-123",
            status=AgentStatus.ACTIVE,
        )
        assert state.agent_id == "test-agent-1"
        assert state.current_task_id == "task-123"
        assert state.status == AgentStatus.ACTIVE

    def test_agent_state_defaults(self):
        """Test AgentState default values."""
        state = AgentState(agent_id="test-agent", status=AgentStatus.INIT)
        assert state.current_task_id is None
        assert state.capabilities == []
        assert state.metrics is not None
        assert isinstance(state.config, dict)
        assert state.config == {}

    def test_agent_state_status_validation(self):
        """Test that status validation works."""
        # Should raise validation error for invalid status
        with pytest.raises(ValueError, match="Invalid status"):
            AgentState(agent_id="test", status="invalid")

    def test_agent_state_serialization(self):
        """Test AgentState serialization to/from JSON."""
        state = AgentState(
            agent_id="test-agent",
            status=AgentStatus.ACTIVE,
            current_task_id="task-1",
        )
        json_str = state.model_dump_json()
        assert isinstance(json_str, str)

        # Can deserialize
        state2 = AgentState.model_validate_json(json_str)
        assert state2.agent_id == state.agent_id
        assert state2.status == state.status

    def test_agent_state_with_capabilities(self):
        """Test AgentState with capabilities."""
        capabilities = AgentCapabilities(
            tools=["tool1", "tool2"],
            metadata={"version": "1.0"},
        )
        state = AgentState(
            agent_id="test",
            status=AgentStatus.ACTIVE,
            capabilities=[capabilities],
        )
        assert len(state.capabilities) == 1


class TestAgentCapabilities:
    """Tests for AgentCapabilities model."""

    def test_agent_capabilities_creation(self):
        """Test creating AgentCapabilities."""
        caps = AgentCapabilities(
            tools=["code_execution", "git_operations"],
            metadata={"version": "1.0"},
        )
        assert len(caps.tools) == 2
        assert caps.metadata["version"] == "1.0"

    def test_agent_capabilities_defaults(self):
        """Test AgentCapabilities default values."""
        caps = AgentCapabilities()
        assert caps.tools == []
        assert isinstance(caps.metadata, dict)
        assert caps.version is None

    def test_agent_capabilities_serialization(self):
        """Test AgentCapabilities serialization."""
        caps = AgentCapabilities(tools=["tool1"], version="1.0")
        json_str = caps.model_dump_json()
        caps2 = AgentCapabilities.model_validate_json(json_str)
        assert caps2.tools == caps.tools


class TestAgentMetrics:
    """Tests for AgentMetrics model."""

    def test_agent_metrics_creation(self):
        """Test creating AgentMetrics."""
        metrics = AgentMetrics(
            tasks_completed=10,
            avg_execution_time=5.5,
            success_rate=0.9,
        )
        assert metrics.tasks_completed == 10
        assert metrics.avg_execution_time == 5.5
        assert metrics.success_rate == 0.9

    def test_agent_metrics_defaults(self):
        """Test AgentMetrics default values."""
        metrics = AgentMetrics()
        assert metrics.tasks_completed == 0
        assert metrics.avg_execution_time == 0.0
        assert metrics.success_rate == 0.0

    def test_agent_metrics_update(self):
        """Test updating metrics."""
        metrics = AgentMetrics()
        metrics.update_from_task(task_duration=10.0, success=True)
        assert metrics.tasks_completed == 1
        assert metrics.success_rate == 1.0
        assert metrics.avg_execution_time == 10.0

    def test_agent_metrics_calculate_avg_time(self):
        """Test calculating average execution time."""
        metrics = AgentMetrics()
        metrics.update_from_task(task_duration=15.0, success=True)
        metrics.update_from_task(task_duration=5.0, success=True)
        assert metrics.tasks_completed == 2
        assert metrics.total_execution_time == 20.0
        assert metrics.avg_execution_time == 10.0


class TestAgentExecutionRecord:
    """Tests for AgentExecutionRecord model."""

    def test_execution_record_creation(self):
        """Test creating AgentExecutionRecord."""
        record = AgentExecutionRecord(
            agent_id="test-agent",
            task_id="task-123",
            action_type="task_started",
            outcome=AgentExecutionOutcome.SUCCESS,
            duration_ms=1000,
        )
        assert record.agent_id == "test-agent"
        assert record.action_type == "task_started"
        assert record.outcome == AgentExecutionOutcome.SUCCESS

    def test_execution_record_with_metadata(self):
        """Test AgentExecutionRecord with metadata."""
        metadata = {"error": "test error", "retry_count": 2}
        record = AgentExecutionRecord(
            agent_id="test",
            action_type="task_failed",
            outcome=AgentExecutionOutcome.FAILURE,
            metadata=metadata,
        )
        assert record.metadata == metadata

    def test_execution_record_serialization(self):
        """Test AgentExecutionRecord serialization."""
        record = AgentExecutionRecord(
            agent_id="test",
            action_type="task_completed",
            outcome=AgentExecutionOutcome.SUCCESS,
        )
        json_str = record.model_dump_json()
        record2 = AgentExecutionRecord.model_validate_json(json_str)
        assert record2.agent_id == record.agent_id


class TestAgentPlan:
    """Tests for AgentPlan model."""

    def test_agent_plan_creation(self):
        """Test creating AgentPlan."""
        plan_data = {
            "steps": ["step1", "step2"],
            "strategy": "sequential",
        }
        plan = AgentPlan(
            agent_id="test-agent",
            task_id="task-123",
            plan_type="execution_plan",
            plan_data=plan_data,
        )
        assert plan.agent_id == "test-agent"
        assert plan.plan_type == "execution_plan"
        assert plan.plan_data == plan_data

    def test_agent_plan_defaults(self):
        """Test AgentPlan default values."""
        plan = AgentPlan(agent_id="test", plan_type="test")
        assert plan.task_id is None
        assert plan.success_rate == 0.0
        assert plan.execution_count == 0

    def test_agent_plan_serialization(self):
        """Test AgentPlan serialization."""
        plan = AgentPlan(
            agent_id="test",
            plan_type="decomposition",
            plan_data={"subtasks": ["t1", "t2"]},
        )
        json_str = plan.model_dump_json()
        plan2 = AgentPlan.model_validate_json(json_str)
        assert plan2.plan_data == plan.plan_data

    def test_agent_plan_update_success_rate(self):
        """Test updating plan success rate."""
        plan = AgentPlan(agent_id="test", plan_type="test")
        plan.increment_execution(success=True)
        assert plan.execution_count == 1
        assert plan.success_rate == 1.0

        plan.increment_execution(success=False)
        assert plan.execution_count == 2
        assert plan.success_rate == 0.5
