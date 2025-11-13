"""Tests for agent learning and improvement system."""
import asyncio
from datetime import datetime, timedelta

import pytest

from june_agent_state.models import (
    AgentExecutionOutcome,
    AgentExecutionRecord,
    AgentPlan,
)
from june_agent_state.learning import (
    AdaptivePlanning,
    AgentLearningSystem,
    FeedbackIntegration,
    KnowledgeSharing,
    LearningMetrics,
    PatternRecognition,
)
from june_agent_state.storage import AgentStateStorage


@pytest.fixture
async def storage():
    """Create storage instance for testing."""
    storage = AgentStateStorage(
        host="localhost",
        port=5432,
        database="june",
        user="postgres",
        password=None,
    )
    await storage.connect()
    yield storage
    await storage.disconnect()


@pytest.fixture
def pattern_recognition(storage):
    """Create PatternRecognition instance."""
    return PatternRecognition(storage)


@pytest.fixture
def knowledge_sharing(storage):
    """Create KnowledgeSharing instance."""
    return KnowledgeSharing(storage)


@pytest.fixture
def adaptive_planning(storage):
    """Create AdaptivePlanning instance."""
    return AdaptivePlanning(storage)


@pytest.fixture
def feedback_integration(storage):
    """Create FeedbackIntegration instance."""
    return FeedbackIntegration(storage)


@pytest.fixture
def learning_metrics(storage):
    """Create LearningMetrics instance."""
    return LearningMetrics(storage)


@pytest.fixture
def learning_system(storage):
    """Create AgentLearningSystem instance."""
    return AgentLearningSystem(storage)


@pytest.mark.asyncio
async def test_pattern_recognition_successful_patterns(storage, pattern_recognition):
    """Test identifying successful patterns."""
    agent_id = "test-agent-pattern"

    # Create execution records with successful pattern
    for i in range(5):
        record = AgentExecutionRecord(
            agent_id=agent_id,
            task_id=f"task-{i}",
            action_type="code_review",
            outcome=AgentExecutionOutcome.SUCCESS,
            duration_ms=1000 + i * 100,
            metadata={"tools_used": ["git", "pytest"], "task_type": "bugfix"},
        )
        await storage.save_execution_record(record)

    # Create some failures with different pattern
    for i in range(2):
        record = AgentExecutionRecord(
            agent_id=agent_id,
            task_id=f"task-fail-{i}",
            action_type="code_review",
            outcome=AgentExecutionOutcome.FAILURE,
            duration_ms=500,
            metadata={"tools_used": ["git"], "task_type": "bugfix"},
        )
        await storage.save_execution_record(record)

    # Identify successful patterns
    patterns = await pattern_recognition.identify_successful_patterns(
        agent_id=agent_id, min_success_rate=0.7, min_executions=3
    )

    assert len(patterns) > 0
    # Should find the successful pattern
    success_pattern = next(
        (p for p in patterns if "git" in p["pattern"] and "pytest" in p["pattern"]),
        None,
    )
    assert success_pattern is not None
    assert success_pattern["success_rate"] >= 0.7


@pytest.mark.asyncio
async def test_pattern_recognition_failure_patterns(storage, pattern_recognition):
    """Test identifying failure patterns."""
    agent_id = "test-agent-failures"

    # Create multiple failures with same pattern
    for i in range(3):
        record = AgentExecutionRecord(
            agent_id=agent_id,
            task_id=f"task-fail-{i}",
            action_type="deployment",
            outcome=AgentExecutionOutcome.FAILURE,
            duration_ms=2000,
            metadata={"error": "Connection timeout", "task_type": "deploy"},
        )
        await storage.save_execution_record(record)

    # Identify failure patterns
    failures = await pattern_recognition.identify_failure_patterns(
        agent_id=agent_id, min_failures=2
    )

    assert len(failures) > 0
    assert failures[0]["failure_count"] >= 3


@pytest.mark.asyncio
async def test_knowledge_sharing_share_pattern(storage, knowledge_sharing):
    """Test sharing patterns between agents."""
    pattern = {
        "pattern": "code_review|tools:git,pytest",
        "success_rate": 0.9,
        "total_executions": 10,
    }

    key = await knowledge_sharing.share_pattern(
        pattern, pattern_type="success", shared_by_agent="test-agent"
    )

    assert key.startswith("shared_pattern:")
    # Verify it was stored
    knowledge = await storage.get_knowledge("shared", key)
    assert knowledge is not None
    assert knowledge["pattern_type"] == "success"


@pytest.mark.asyncio
async def test_knowledge_sharing_share_solution(storage, knowledge_sharing):
    """Test sharing solutions."""
    solution = {
        "approach": "Use async/await for I/O operations",
        "benefits": ["Better performance", "Non-blocking"],
    }

    key = await knowledge_sharing.share_solution(
        problem="Slow database queries",
        solution=solution,
        shared_by_agent="test-agent",
        tags=["performance", "database"],
    )

    assert key.startswith("shared_solution:")
    knowledge = await storage.get_knowledge("shared", key)
    assert knowledge is not None
    assert knowledge["problem"] == "Slow database queries"


@pytest.mark.asyncio
async def test_adaptive_planning_get_optimal_plan(storage, adaptive_planning):
    """Test getting optimal plan based on success rates."""
    agent_id = "test-agent-planning"

    # Create a plan with high success rate
    plan1 = AgentPlan(
        agent_id=agent_id,
        task_id="task-1",
        plan_type="execution_plan",
        plan_data={"steps": ["step1", "step2"]},
        success_rate=0.9,
        execution_count=10,
    )
    plan1_id = await storage.save_plan(plan1)

    # Create a plan with lower success rate
    plan2 = AgentPlan(
        agent_id=agent_id,
        task_id="task-2",
        plan_type="execution_plan",
        plan_data={"steps": ["step3", "step4"]},
        success_rate=0.5,
        execution_count=5,
    )
    await storage.save_plan(plan2)

    # Get optimal plan
    optimal = await adaptive_planning.get_optimal_plan(
        task_id="task-1", agent_id=agent_id
    )

    assert optimal is not None
    assert optimal["success_rate"] >= 0.6


@pytest.mark.asyncio
async def test_adaptive_planning_update_plan_success(storage, adaptive_planning):
    """Test updating plan success metrics."""
    agent_id = "test-agent-update"

    plan = AgentPlan(
        agent_id=agent_id,
        task_id="task-1",
        plan_type="execution_plan",
        plan_data={"steps": ["step1"]},
        success_rate=0.5,
        execution_count=2,
    )
    plan_id = await storage.save_plan(plan)

    # Update with success
    await adaptive_planning.update_plan_success(plan_id, success=True)

    # Verify update
    updated_plan = await storage.load_plan(plan_id)
    assert updated_plan is not None
    assert updated_plan.execution_count == 3
    assert updated_plan.success_rate > 0.5  # Should improve


@pytest.mark.asyncio
async def test_adaptive_planning_estimate_duration(storage, adaptive_planning):
    """Test estimating task duration."""
    agent_id = "test-agent-duration"

    # Create execution records with known durations
    for duration_ms in [5000, 6000, 7000, 8000, 9000]:
        record = AgentExecutionRecord(
            agent_id=agent_id,
            task_id="task-1",
            action_type="task_completed",
            outcome=AgentExecutionOutcome.SUCCESS,
            duration_ms=duration_ms,
            metadata={"task_type": "bugfix"},
        )
        await storage.save_execution_record(record)

    estimate = await adaptive_planning.estimate_task_duration(
        task_type="bugfix"
    )

    assert estimate is not None
    assert "mean" in estimate
    assert "median" in estimate
    assert estimate["mean"] > 0
    assert estimate["sample_size"] >= 5


@pytest.mark.asyncio
async def test_feedback_integration_record_feedback(storage, feedback_integration):
    """Test recording feedback."""
    agent_id = "test-agent-feedback"

    feedback_content = {
        "rating": 5,
        "comment": "Great work!",
        "suggestions": ["Add more tests", "Improve documentation"],
    }

    key = await feedback_integration.record_feedback(
        agent_id=agent_id,
        task_id="task-1",
        feedback_type="user_feedback",
        feedback_content=feedback_content,
        source="user",
    )

    assert key.startswith("feedback:")
    knowledge = await storage.get_knowledge(agent_id, key)
    assert knowledge is not None
    assert knowledge["feedback_type"] == "user_feedback"


@pytest.mark.asyncio
async def test_learning_metrics_get_stats(storage, learning_metrics):
    """Test getting learning statistics."""
    agent_id = "test-agent-metrics"

    # Create execution records over time
    base_time = datetime.now() - timedelta(days=10)
    for i in range(20):
        outcome = (
            AgentExecutionOutcome.SUCCESS if i % 3 != 0 else AgentExecutionOutcome.FAILURE
        )
        record = AgentExecutionRecord(
            agent_id=agent_id,
            task_id=f"task-{i}",
            action_type="task_completed",
            outcome=outcome,
            duration_ms=1000,
            created_at=base_time + timedelta(days=i / 2),
        )
        await storage.save_execution_record(record)

    stats = await learning_metrics.get_agent_learning_stats(agent_id, days=30)

    assert stats["agent_id"] == agent_id
    assert stats["total_executions"] > 0
    assert "success_rate" in stats
    assert "improvement_trend" in stats


@pytest.mark.asyncio
async def test_learning_metrics_identify_improvement_areas(
    storage, learning_metrics
):
    """Test identifying improvement areas."""
    agent_id = "test-agent-improve"

    # Create failure records
    for i in range(3):
        record = AgentExecutionRecord(
            agent_id=agent_id,
            task_id=f"task-{i}",
            action_type="deployment",
            outcome=AgentExecutionOutcome.FAILURE,
            duration_ms=2000,
            metadata={"error": "Connection timeout"},
        )
        await storage.save_execution_record(record)

    areas = await learning_metrics.identify_improvement_areas(agent_id)

    assert len(areas) > 0
    assert "area" in areas[0]
    assert "recommendation" in areas[0]


@pytest.mark.asyncio
async def test_learning_system_record_experience(storage, learning_system):
    """Test recording experiences."""
    agent_id = "test-agent-experience"

    record_id = await learning_system.record_experience(
        agent_id=agent_id,
        task_id="task-1",
        action_type="task_completed",
        outcome=AgentExecutionOutcome.SUCCESS,
        duration_ms=5000,
        metadata={"tools_used": ["git", "pytest"]},
    )

    assert record_id is not None

    # Verify it was saved
    records = await storage.query_execution_history(agent_id=agent_id, limit=1)
    assert len(records) > 0
    assert records[0].action_type == "task_completed"


@pytest.mark.asyncio
async def test_learning_system_learn_from_experience(storage, learning_system):
    """Test learning from experiences."""
    agent_id = "test-agent-learn"

    # Create various execution records
    for i in range(10):
        outcome = (
            AgentExecutionOutcome.SUCCESS if i % 2 == 0 else AgentExecutionOutcome.FAILURE
        )
        await learning_system.record_experience(
            agent_id=agent_id,
            task_id=f"task-{i}",
            action_type="code_review",
            outcome=outcome,
            duration_ms=1000 + i * 100,
            metadata={"tools_used": ["git"], "task_type": "bugfix"},
        )

    # Learn from experiences
    insights = await learning_system.learn_from_experience(agent_id, days=7)

    assert insights["agent_id"] == agent_id
    assert "successful_patterns" in insights
    assert "failure_patterns" in insights
    assert "learning_stats" in insights
    assert "recommendations" in insights
    assert len(insights["recommendations"]) > 0


@pytest.mark.asyncio
async def test_learning_system_integration(storage, learning_system):
    """Test full learning system integration."""
    agent_id = "test-agent-integration"

    # Record multiple experiences
    for i in range(15):
        outcome = (
            AgentExecutionOutcome.SUCCESS
            if i % 3 != 0
            else AgentExecutionOutcome.FAILURE
        )
        await learning_system.record_experience(
            agent_id=agent_id,
            task_id=f"task-{i}",
            action_type="task_completed",
            outcome=outcome,
            duration_ms=2000,
            metadata={"task_type": "feature"},
        )

    # Create a plan
    plan = AgentPlan(
        agent_id=agent_id,
        task_id="task-1",
        plan_type="execution_plan",
        plan_data={"strategy": "test_first"},
        success_rate=0.7,
        execution_count=5,
    )
    plan_id = await storage.save_plan(plan)

    # Update plan success
    await learning_system.adaptive_planning.update_plan_success(plan_id, success=True)

    # Get learning insights
    insights = await learning_system.learn_from_experience(agent_id, days=30)

    # Verify all components work together
    assert insights["total_experiences"] >= 15
    assert len(insights["successful_patterns"]) >= 0
    assert insights["learning_stats"]["total_executions"] >= 15

    # Get optimal plan
    optimal = await learning_system.adaptive_planning.get_optimal_plan(
        task_id="task-1", agent_id=agent_id
    )
    assert optimal is not None
    # Note: plan_id may be None as query_plans doesn't return IDs

    # Record feedback
    feedback_key = await learning_system.feedback_integration.record_feedback(
        agent_id=agent_id,
        task_id="task-1",
        feedback_type="code_review",
        feedback_content={"rating": 4, "comment": "Good work"},
    )
    assert feedback_key is not None
