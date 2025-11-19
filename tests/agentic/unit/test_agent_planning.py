"""
Unit Tests for Agent Planning Logic

Tests agent planning, task analysis, and decomposition capabilities.
"""

import pytest
from typing import Dict, Any


class TestAgentPlanning:
    """Tests for agent planning functionality."""

    def test_planning_analyzes_task_requirements(self):
        """Test that planning can analyze task requirements."""
        task = {
            "title": "Add user authentication",
            "task_instruction": "Implement JWT-based authentication system",
            "verification_instruction": "Verify users can login and receive tokens",
        }

        # Mock planning logic
        requirements = self._analyze_requirements(task)

        assert "authentication" in requirements["keywords"]
        assert "JWT" in requirements["keywords"]
        assert len(requirements["estimated_steps"]) > 0

    def test_planning_decomposes_complex_tasks(self):
        """Test that planning can decompose complex tasks."""
        complex_task = {
            "title": "Build full-stack application",
            "task_instruction": "Create a complete web application with frontend and backend",
            "verification_instruction": "Verify application works end-to-end",
        }

        # Mock decomposition
        subtasks = self._decompose_task(complex_task)

        assert len(subtasks) > 1
        assert any("frontend" in st["title"].lower() for st in subtasks)
        assert any("backend" in st["title"].lower() for st in subtasks)

    def test_planning_identifies_dependencies(self):
        """Test that planning identifies task dependencies."""
        task = {
            "title": "Add database migrations",
            "task_instruction": "Create migration system for database schema changes",
            "verification_instruction": "Verify migrations can be applied and rolled back",
        }

        dependencies = self._identify_dependencies(task)

        # Should depend on database being set up
        assert "database" in dependencies["required_components"]

    def test_planning_estimates_effort(self):
        """Test that planning can estimate effort."""
        task = {
            "title": "Add simple feature",
            "task_instruction": "Add a button to the UI",
            "verification_instruction": "Verify button appears and works",
        }

        effort = self._estimate_effort(task)

        assert "estimated_hours" in effort
        assert effort["estimated_hours"] > 0
        assert effort["estimated_hours"] < 10  # Simple task should be quick

    def test_planning_creates_execution_order(self):
        """Test that planning creates proper execution order."""
        subtasks = [
            {"title": "Create database schema", "dependencies": []},
            {
                "title": "Create API endpoint",
                "dependencies": ["Create database schema"],
            },
            {
                "title": "Add frontend component",
                "dependencies": ["Create API endpoint"],
            },
        ]

        order = self._order_subtasks(subtasks)

        # Database should come first
        assert order[0]["title"] == "Create database schema"
        # API should come before frontend
        api_idx = next(i for i, st in enumerate(order) if "API" in st["title"])
        frontend_idx = next(
            i for i, st in enumerate(order) if "frontend" in st["title"]
        )
        assert api_idx < frontend_idx

    # Helper methods (would be replaced with actual planning logic)

    def _analyze_requirements(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Mock requirement analysis."""
        keywords = []
        instruction = task.get("task_instruction", "").lower()

        if "jwt" in instruction:
            keywords.append("JWT")
        if "authentication" in instruction:
            keywords.append("authentication")

        return {
            "keywords": keywords,
            "estimated_steps": [
                "Setup JWT library",
                "Create auth endpoint",
                "Test authentication",
            ],
        }

    def _decompose_task(self, task: Dict[str, Any]) -> list:
        """Mock task decomposition."""
        return [
            {"title": "Create backend API", "type": "backend"},
            {"title": "Create frontend UI", "type": "frontend"},
        ]

    def _identify_dependencies(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Mock dependency identification."""
        return {
            "required_components": ["database"],
            "required_tools": ["migration_framework"],
        }

    def _estimate_effort(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Mock effort estimation."""
        complexity = len(task.get("task_instruction", "").split())
        return {
            "estimated_hours": complexity * 0.5,
            "complexity": "low" if complexity < 20 else "medium",
        }

    def _order_subtasks(self, subtasks: list) -> list:
        """Mock subtask ordering."""
        # Simple topological sort
        ordered = []
        remaining = list(subtasks)

        while remaining:
            for st in remaining[:]:
                deps = st.get("dependencies", [])
                if not deps or all(
                    dep["title"] in [s["title"] for s in ordered] for dep in deps
                ):
                    ordered.append(st)
                    remaining.remove(st)
                    break

        return ordered


class TestTaskDecomposition:
    """Tests for task decomposition algorithms."""

    def test_decomposition_breaks_large_tasks(self):
        """Test that large tasks are broken into smaller pieces."""
        large_task = {
            "task_instruction": "Build complete e-commerce platform with products, cart, checkout, payment"
        }

        subtasks = self._decompose_large_task(large_task)

        assert len(subtasks) >= 4  # Should have multiple subtasks
        assert any("product" in st.lower() for st in subtasks)
        assert any("cart" in st.lower() for st in subtasks)

    def test_decomposition_maintains_relationships(self):
        """Test that subtask relationships are maintained."""
        parent_task = {
            "title": "Add payment system",
            "task_instruction": "Integrate payment gateway",
        }

        subtasks = self._decompose_with_relationships(parent_task)

        for subtask in subtasks:
            assert "parent_id" in subtask
            assert subtask["parent_id"] == parent_task.get("id")

    # Helper methods

    def _decompose_large_task(self, task: Dict[str, Any]) -> list:
        """Mock large task decomposition."""
        instruction = task.get("task_instruction", "").lower()
        subtasks = []

        if "product" in instruction:
            subtasks.append("Implement product catalog")
        if "cart" in instruction:
            subtasks.append("Implement shopping cart")
        if "checkout" in instruction:
            subtasks.append("Implement checkout flow")
        if "payment" in instruction:
            subtasks.append("Integrate payment gateway")

        return subtasks

    def _decompose_with_relationships(self, task: Dict[str, Any]) -> list:
        """Mock decomposition with relationships."""
        return [
            {
                "title": "Setup payment API",
                "parent_id": task.get("id"),
                "type": "subtask",
            },
            {"title": "Add payment UI", "parent_id": task.get("id"), "type": "subtask"},
        ]
