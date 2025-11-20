"""
Unit Tests for Decision Logic

Tests the decision logic that determines when to use agentic flow vs direct response.
"""
from typing import Any, Dict, List

import pytest

from essence.agents.decision import estimate_request_complexity, should_use_agentic_flow


class TestShouldUseAgenticFlow:
    """Tests for should_use_agentic_flow function."""

    def test_explicit_reasoning_keywords(self):
        """Test that explicit reasoning keywords trigger agentic flow."""
        assert should_use_agentic_flow("Can you plan the steps?")
        assert should_use_agentic_flow("I need you to think about this")
        assert should_use_agentic_flow("Please break down the problem")
        assert should_use_agentic_flow("How to implement this feature?")

    def test_message_length_threshold(self):
        """Test that long messages trigger agentic flow."""
        short_message = "Hello"
        long_message = "A" * 201  # Exceeds default threshold of 200

        assert not should_use_agentic_flow(short_message)
        assert should_use_agentic_flow(long_message)

    def test_custom_complexity_threshold(self):
        """Test that custom complexity threshold works."""
        message = "A" * 150
        assert should_use_agentic_flow(message, complexity_threshold=100)
        assert not should_use_agentic_flow(message, complexity_threshold=200)

    def test_tool_keywords(self):
        """Test that tool-related keywords trigger agentic flow."""
        assert should_use_agentic_flow("Create a file")
        assert should_use_agentic_flow("Write some code")
        assert should_use_agentic_flow("Modify the configuration")
        assert should_use_agentic_flow("Execute this command")
        assert should_use_agentic_flow("Run the tests")
        assert should_use_agentic_flow("Implement the feature")

    def test_conversation_history_complexity(self):
        """Test that multi-turn conversations trigger agentic flow."""
        simple_history: List[Dict[str, Any]] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        complex_history: List[Dict[str, Any]] = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Message 3"},
        ]

        assert not should_use_agentic_flow(
            "Simple question", message_history=simple_history
        )
        assert should_use_agentic_flow(
            "Follow-up question", message_history=complex_history
        )

    def test_tool_indicators_with_available_tools(self):
        """Test that tool indicators with available tools trigger agentic flow."""
        available_tools = [{"name": "read_file"}, {"name": "write_file"}]

        assert should_use_agentic_flow(
            "Process this with a tool", available_tools=available_tools
        )
        assert should_use_agentic_flow(
            "Do this using a function", available_tools=available_tools
        )
        assert should_use_agentic_flow(
            "Use a method to solve this", available_tools=available_tools
        )

    def test_tool_indicators_without_tools(self):
        """Test that tool indicators without available tools don't trigger agentic flow."""
        assert not should_use_agentic_flow(
            "Process this with a tool", available_tools=[]
        )
        assert not should_use_agentic_flow(
            "Process this with a tool", available_tools=None
        )

    def test_simple_requests_dont_trigger(self):
        """Test that simple requests don't trigger agentic flow."""
        assert not should_use_agentic_flow("Hello")
        assert not should_use_agentic_flow("What is the weather?")
        assert not should_use_agentic_flow("Tell me a joke")

    def test_case_insensitive_keyword_matching(self):
        """Test that keyword matching is case-insensitive."""
        assert should_use_agentic_flow("PLAN the steps")
        assert should_use_agentic_flow("Create A File")
        assert should_use_agentic_flow("How To Do This")


class TestEstimateRequestComplexity:
    """Tests for estimate_request_complexity function."""

    def test_simple_requests(self):
        """Test that simple requests are classified as simple."""
        assert estimate_request_complexity("Hello") == "simple"
        assert estimate_request_complexity("What is 2+2?") == "simple"
        assert estimate_request_complexity("Short message") == "simple"

    def test_length_based_scoring(self):
        """Test that message length affects complexity scoring."""
        # Short message (score 0-1)
        assert estimate_request_complexity("A" * 50) == "simple"

        # Medium message (score 1-2)
        assert estimate_request_complexity("A" * 150) in ["simple", "moderate"]

        # Long message (score 2-3)
        assert estimate_request_complexity("A" * 600) in ["moderate", "complex"]

    def test_complex_keywords(self):
        """Test that complex keywords increase complexity score."""
        message = (
            "This is a multiple, complex, advanced, sophisticated, comprehensive task"
        )
        assert estimate_request_complexity(message) == "complex"

    def test_moderate_keywords(self):
        """Test that moderate keywords increase complexity score."""
        message = "Create and modify the system, then analyze and process the data"
        result = estimate_request_complexity(message)
        assert result in ["moderate", "complex"]

    def test_conversation_history_scoring(self):
        """Test that conversation history affects complexity scoring."""
        short_history: List[Dict[str, Any]] = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
        ]
        medium_history: List[Dict[str, Any]] = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
        ]
        long_history: List[Dict[str, Any]] = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Message 3"},
            {"role": "assistant", "content": "Response 3"},
            {"role": "user", "content": "Message 4"},
        ]

        simple_result = estimate_request_complexity(
            "Follow-up", message_history=short_history
        )
        medium_result = estimate_request_complexity(
            "Follow-up", message_history=medium_history
        )
        long_result = estimate_request_complexity(
            "Follow-up", message_history=long_history
        )

        # Longer history should increase complexity
        assert simple_result in ["simple", "moderate"]
        assert medium_result in ["simple", "moderate"]
        assert long_result in ["moderate", "complex"]

    def test_combined_factors(self):
        """Test that multiple factors combine to determine complexity."""
        # Long message with complex keywords
        message = "A" * 600 + " This is a multiple, complex, advanced task"
        assert estimate_request_complexity(message) == "complex"

        # Medium message with moderate keywords
        message = "A" * 300 + " Create and modify the system"
        result = estimate_request_complexity(message)
        assert result in ["moderate", "complex"]

    def test_empty_message(self):
        """Test that empty message is classified as simple."""
        assert estimate_request_complexity("") == "simple"

    def test_no_history(self):
        """Test that function works without message history."""
        assert estimate_request_complexity("Test message") in ["simple", "moderate"]
        assert estimate_request_complexity("Test message", message_history=None) in [
            "simple",
            "moderate",
        ]
