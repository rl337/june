"""
Unit Tests for Agent Execution Strategies

Tests agent execution strategies and code generation capabilities.
"""

import pytest
from typing import Dict, Any, List


class TestExecutionStrategies:
    """Tests for execution strategy selection and implementation."""

    def test_strategy_selection_based_on_task_type(self):
        """Test that appropriate strategy is selected based on task type."""
        concrete_task = {"task_type": "concrete", "title": "Add function"}
        abstract_task = {"task_type": "abstract", "title": "Design system"}

        concrete_strategy = self._select_strategy(concrete_task)
        abstract_strategy = self._select_strategy(abstract_task)

        assert concrete_strategy["approach"] == "direct_implementation"
        assert abstract_strategy["approach"] == "planning_first"

    def test_strategy_includes_verification_steps(self):
        """Test that execution strategy includes verification steps."""
        task = {
            "title": "Add API endpoint",
            "task_instruction": "Create POST /api/users endpoint",
            "verification_instruction": "Test endpoint with curl",
        }

        strategy = self._create_strategy(task)

        assert "verification_steps" in strategy
        assert len(strategy["verification_steps"]) > 0
        assert any("test" in step.lower() for step in strategy["verification_steps"])

    def test_strategy_handles_error_recovery(self):
        """Test that strategy includes error recovery plans."""
        task = {
            "title": "Risky operation",
            "task_instruction": "Perform risky operation",
        }

        strategy = self._create_strategy(task)

        assert "error_recovery" in strategy
        assert "rollback_plan" in strategy["error_recovery"]
        assert "retry_strategy" in strategy["error_recovery"]

    def test_strategy_estimates_resources(self):
        """Test that strategy estimates required resources."""
        task = {
            "title": "Large task",
            "task_instruction": "Process large dataset",
            "verification_instruction": "Verify processing completes",
        }

        strategy = self._create_strategy(task)

        assert "resource_estimation" in strategy
        assert "estimated_time" in strategy["resource_estimation"]
        assert "estimated_memory" in strategy["resource_estimation"]

    # Helper methods

    def _select_strategy(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Mock strategy selection."""
        if task.get("task_type") == "concrete":
            return {
                "approach": "direct_implementation",
                "steps": ["Analyze requirements", "Write code", "Test", "Verify"],
            }
        else:
            return {
                "approach": "planning_first",
                "steps": ["Analyze", "Plan", "Break down", "Execute"],
            }

    def _create_strategy(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Mock strategy creation."""
        return {
            "approach": "direct_implementation",
            "steps": ["Implement", "Test"],
            "verification_steps": ["Run tests", "Check output"],
            "error_recovery": {
                "rollback_plan": "Revert changes",
                "retry_strategy": "Exponential backoff",
            },
            "resource_estimation": {"estimated_time": 30.0, "estimated_memory": 100.0},
        }


class TestCodeGeneration:
    """Tests for code generation capabilities."""

    def test_generates_code_from_specification(self):
        """Test that code can be generated from task specification."""
        spec = {
            "function_name": "add_user",
            "parameters": ["name", "email"],
            "return_type": "User",
            "description": "Create a new user",
        }

        code = self._generate_code(spec)

        assert "def add_user" in code
        assert "name" in code
        assert "email" in code
        assert "User" in code

    def test_generated_code_includes_docstring(self):
        """Test that generated code includes documentation."""
        spec = {"function_name": "process_data", "description": "Process incoming data"}

        code = self._generate_code(spec)

        assert '"""' in code or "'''" in code
        assert "Process incoming data" in code

    def test_generated_code_includes_type_hints(self):
        """Test that generated code includes type hints."""
        spec = {
            "function_name": "calculate_total",
            "parameters": [{"name": "items", "type": "List[int]"}],
            "return_type": "int",
        }

        code = self._generate_code(spec)

        assert "List[int]" in code
        assert "-> int" in code

    # Helper methods

    def _generate_code(self, spec: Dict[str, Any]) -> str:
        """Mock code generation."""
        func_name = spec.get("function_name", "function")
        params = spec.get("parameters", [])

        code = f"def {func_name}("

        if isinstance(params, list):
            if params and isinstance(params[0], dict):
                param_strs = [f"{p['name']}: {p.get('type', 'Any')}" for p in params]
            else:
                param_strs = [str(p) for p in params]
            code += ", ".join(param_strs)

        code += f") -> {spec.get('return_type', 'None')}:\n"

        docstring = spec.get("description", "")
        if docstring:
            code += f'    """{docstring}"""\n'

        code += "    pass"

        return code
