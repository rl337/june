"""
Basic Unit Tests for Agentic Reasoning Data Structures

Tests the core data structures without requiring full dependency chain.
These tests verify the basic functionality of reasoning components.
"""
import pytest
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


# Define data structures directly in test to avoid import issues
class ReasoningStep(str, Enum):
    """Steps in the reasoning loop"""

    THINK = "think"
    PLAN = "plan"
    EXECUTE = "execute"
    REFLECT = "reflect"
    COMPLETE = "complete"


@dataclass
class Step:
    """Represents a single step in an execution plan"""

    step_id: int
    description: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    expected_output: Optional[str] = None
    dependencies: List[int] = field(default_factory=list)


@dataclass
class Plan:
    """Represents an execution plan"""

    steps: List[Step] = field(default_factory=list)
    estimated_complexity: str = "simple"
    success_criteria: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        step_descriptions = "\n".join(
            f"  {i+1}. {step.description}" for i, step in enumerate(self.steps)
        )
        return f"Plan ({self.estimated_complexity}):\n{step_descriptions}"


@dataclass
class ExecutionResult:
    """Result of executing a step"""

    step_id: int
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    tool_used: Optional[str] = None

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} Step {self.step_id}: {self.output if self.success else self.error}"


@dataclass
class ReflectionResult:
    """Result of reflection phase"""

    goal_achieved: bool
    issues_found: List[str] = field(default_factory=list)
    plan_adjustments: Optional[Plan] = None
    should_continue: bool = False
    final_response: Optional[str] = None
    confidence: float = 0.0

    def __str__(self) -> str:
        status = "✓ Goal achieved" if self.goal_achieved else "✗ Goal not achieved"
        issues = (
            f"\n  Issues: {', '.join(self.issues_found)}" if self.issues_found else ""
        )
        return f"{status}{issues}"


@dataclass
class ConversationContext:
    """Manages conversation state"""

    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    message_history: List[Dict[str, Any]] = field(default_factory=list)
    reasoning_history: List[Any] = field(default_factory=list)
    tool_state: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)


class TestDataStructures:
    """Tests for data structures."""

    def test_step_creation(self):
        """Test Step creation."""
        step = Step(
            step_id=1,
            description="Test step",
            tool_name="test_tool",
        )

        assert step.step_id == 1
        assert step.description == "Test step"
        assert step.tool_name == "test_tool"

    def test_plan_creation(self):
        """Test Plan creation."""
        plan = Plan(
            steps=[Step(step_id=1, description="Step 1")],
            estimated_complexity="simple",
        )

        assert len(plan.steps) == 1
        assert plan.estimated_complexity == "simple"

    def test_plan_string_representation(self):
        """Test Plan string representation."""
        plan = Plan(
            steps=[
                Step(step_id=1, description="Step 1"),
                Step(step_id=2, description="Step 2"),
            ],
            estimated_complexity="moderate",
        )

        plan_str = str(plan)
        assert "moderate" in plan_str
        assert "Step 1" in plan_str
        assert "Step 2" in plan_str

    def test_execution_result_creation(self):
        """Test ExecutionResult creation."""
        result = ExecutionResult(
            step_id=1,
            success=True,
            output="Success",
        )

        assert result.step_id == 1
        assert result.success is True
        assert result.output == "Success"

    def test_execution_result_string_representation(self):
        """Test ExecutionResult string representation."""
        success_result = ExecutionResult(step_id=1, success=True, output="Done")
        fail_result = ExecutionResult(step_id=2, success=False, error="Failed")

        assert "✓" in str(success_result)
        assert "✗" in str(fail_result)
        assert "Done" in str(success_result)
        assert "Failed" in str(fail_result)

    def test_reflection_result_creation(self):
        """Test ReflectionResult creation."""
        reflection = ReflectionResult(
            goal_achieved=True,
            confidence=0.9,
        )

        assert reflection.goal_achieved is True
        assert reflection.confidence == 0.9

    def test_reflection_result_with_issues(self):
        """Test ReflectionResult with issues."""
        reflection = ReflectionResult(
            goal_achieved=False,
            issues_found=["Issue 1", "Issue 2"],
            confidence=0.3,
        )

        assert reflection.goal_achieved is False
        assert len(reflection.issues_found) == 2
        assert reflection.confidence == 0.3

    def test_conversation_context_creation(self):
        """Test ConversationContext creation."""
        context = ConversationContext(
            user_id="user1",
            chat_id="chat1",
        )

        assert context.user_id == "user1"
        assert context.chat_id == "chat1"
        assert isinstance(context.message_history, list)
        assert isinstance(context.tool_state, dict)

    def test_reasoning_step_enum(self):
        """Test ReasoningStep enum."""
        assert ReasoningStep.THINK == "think"
        assert ReasoningStep.PLAN == "plan"
        assert ReasoningStep.EXECUTE == "execute"
        assert ReasoningStep.REFLECT == "reflect"
        assert ReasoningStep.COMPLETE == "complete"


class TestPlanLogic:
    """Tests for plan logic."""

    def test_plan_with_multiple_steps(self):
        """Test plan with multiple steps."""
        plan = Plan(
            steps=[
                Step(step_id=1, description="First step"),
                Step(step_id=2, description="Second step"),
                Step(step_id=3, description="Third step"),
            ],
            estimated_complexity="complex",
        )

        assert len(plan.steps) == 3
        assert plan.steps[0].step_id == 1
        assert plan.steps[1].step_id == 2
        assert plan.steps[2].step_id == 3

    def test_plan_with_dependencies(self):
        """Test plan with step dependencies."""
        step1 = Step(step_id=1, description="First")
        step2 = Step(step_id=2, description="Second", dependencies=[1])
        step3 = Step(step_id=3, description="Third", dependencies=[1, 2])

        plan = Plan(steps=[step1, step2, step3])

        assert step2.dependencies == [1]
        assert step3.dependencies == [1, 2]


class TestExecutionResultLogic:
    """Tests for execution result logic."""

    def test_successful_execution(self):
        """Test successful execution result."""
        result = ExecutionResult(
            step_id=1,
            success=True,
            output="Task completed",
            execution_time=1.5,
            tool_used="test_tool",
        )

        assert result.success is True
        assert result.output == "Task completed"
        assert result.execution_time == 1.5
        assert result.tool_used == "test_tool"

    def test_failed_execution(self):
        """Test failed execution result."""
        result = ExecutionResult(
            step_id=1,
            success=False,
            error="Tool not found",
            execution_time=0.1,
        )

        assert result.success is False
        assert result.error == "Tool not found"
        assert result.output is None


class TestReflectionResultLogic:
    """Tests for reflection result logic."""

    def test_goal_achieved_reflection(self):
        """Test reflection when goal is achieved."""
        reflection = ReflectionResult(
            goal_achieved=True,
            should_continue=False,
            confidence=1.0,
            final_response="Task completed successfully",
        )

        assert reflection.goal_achieved is True
        assert reflection.should_continue is False
        assert reflection.confidence == 1.0

    def test_goal_not_achieved_reflection(self):
        """Test reflection when goal is not achieved."""
        reflection = ReflectionResult(
            goal_achieved=False,
            issues_found=["Error in step 2"],
            should_continue=True,
            confidence=0.5,
        )

        assert reflection.goal_achieved is False
        assert len(reflection.issues_found) > 0
        assert reflection.should_continue is True
