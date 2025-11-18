"""
Unit tests for streaming agent response handling.

Tests the extraction and accumulation logic to ensure messages are properly
accumulated and streamed incrementally to Telegram.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Iterator, Tuple

# Import from essence package (code moved from services/chat-service-base to essence/chat/agent)
from essence.chat.agent.response import (
    stream_chat_response_agent,
    _extract_human_readable_from_json_line
)


class TestExtractHumanReadable:
    """Test the JSON line extraction function."""
    
    def test_extract_assistant_message_full(self):
        """Test extracting full assistant message."""
        json_line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "Hi. How can I help you today?\n\nI can help with:\n- **Tasks & Projects** — list, create, or manage tasks\n- **Documentation** — search or create docs\n- **Knowledge** — query or store facts\n\nWhat would you like to do?"
                    }
                ]
            }
        })
        
        result = _extract_human_readable_from_json_line(json_line)
        assert result is not None
        assert "Hi. How can I help you today?" in result
        assert "Tasks & Projects" in result
        assert len(result) > 100
    
    def test_extract_assistant_message_incremental_chunk_1(self):
        """Test extracting first incremental chunk."""
        json_line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "Hi. How can"
                    }
                ]
            }
        })
        
        result = _extract_human_readable_from_json_line(json_line)
        assert result == "Hi. How can"
    
    def test_extract_assistant_message_incremental_chunk_2(self):
        """Test extracting second incremental chunk (should contain first)."""
        json_line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "Hi. How can I help you today?"
                    }
                ]
            }
        })
        
        result = _extract_human_readable_from_json_line(json_line)
        assert result == "Hi. How can I help you today?"
        assert "Hi. How can" in result  # Should contain the first chunk
    
    def test_extract_middle_chunk_problem(self):
        """Test the problematic case: extracting a middle chunk."""
        # This simulates the "order or not al" problem
        json_line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "order or not al"
                    }
                ]
            }
        })
        
        result = _extract_human_readable_from_json_line(json_line)
        assert result == "order or not al"
        # This is a problem - we're getting a middle chunk, not the full message
    
    def test_extract_skips_thinking(self):
        """Test that thinking states are skipped."""
        json_line = json.dumps({
            "type": "thinking",
            "content": "I need to think about this..."
        })
        
        result = _extract_human_readable_from_json_line(json_line)
        assert result is None
    
    def test_extract_skips_descriptions(self):
        """Test that description messages are skipped."""
        json_line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "Writing response to file..."
                    }
                ]
            }
        })
        
        result = _extract_human_readable_from_json_line(json_line)
        assert result is None


class TestStreamAccumulation:
    """Test the message accumulation logic in streaming."""
    
    def test_accumulation_with_incremental_chunks(self):
        """Test that incremental chunks are properly accumulated."""
        # Simulate cursor-agent output: each line contains the previous text plus more
        json_lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can"}]
                }
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can I help you today?"}]
                }
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can I help you today?\n\nI can help with:\n- **Tasks & Projects**"}]
                }
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can I help you today?\n\nI can help with:\n- **Tasks & Projects** — list, create, or manage tasks\n- **Documentation** — search or create docs\n- **Knowledge** — query or store facts\n\nWhat would you like to do?"}]
                }
            }),
        ]
        
        # Mock the streaming_popen_generator to yield our test lines
        def mock_generator(*args, **kwargs):
            for i, line in enumerate(json_lines):
                is_final = (i == len(json_lines) - 1)
                yield (line, is_final)
        
        with patch('essence.chat.agent.response.streaming_popen_generator', mock_generator):
            with patch('essence.chat.agent.response.os.path.exists', return_value=True):
                with patch('essence.chat.agent.response.os.access', return_value=True):
                    results = list(stream_chat_response_agent(
                        "test message",
                        user_id=123,
                        chat_id=456,
                        line_timeout=30.0,
                        max_total_time=300.0
                    ))
        
        # Should yield messages with increasing length
        assert len(results) > 0
        
        # Check that messages are accumulated (each should be longer or equal)
        message_lengths = [len(msg) for msg, is_final, msg_type in results if msg]
        if len(message_lengths) > 1:
            # Messages should generally increase in length (accumulation)
            # But we might get the same length if it's the same accumulated message
            assert all(msg_len >= message_lengths[0] for msg_len in message_lengths), \
                f"Message lengths should not decrease: {message_lengths}"
    
    def test_accumulation_with_middle_chunk_problem(self):
        """Test the problematic case where we get a middle chunk."""
        # Simulate the "order or not al" problem - getting a middle chunk
        json_lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can"}]
                }
            }),
            # Problem: we get a middle chunk that doesn't contain the previous one
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "order or not al"}]
                }
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can I help you today?\n\nI can help with tasks, order or not all of them."}]
                }
            }),
        ]
        
        def mock_generator(*args, **kwargs):
            for i, line in enumerate(json_lines):
                is_final = (i == len(json_lines) - 1)
                yield (line, is_final)
        
        with patch('essence.chat.agent.response.streaming_popen_generator', mock_generator):
            with patch('essence.chat.agent.response.os.path.exists', return_value=True):
                with patch('essence.chat.agent.response.os.access', return_value=True):
                    results = list(stream_chat_response_agent(
                        "test message",
                        user_id=123,
                        chat_id=456,
                        line_timeout=30.0,
                        max_total_time=300.0
                    ))
        
        # The problem: we should NOT yield "order or not al" as a separate message
        # We should only yield the accumulated longest message
        messages = [msg for msg, is_final, msg_type in results if msg]
        
        # Check that we don't have the middle chunk as a standalone message
        # (unless it's longer than what we had before)
        for msg in messages:
            if msg == "order or not al":
                # This is the problem - we're yielding a middle chunk
                # We should only yield it if it's part of a longer accumulated message
                pytest.fail("Should not yield standalone middle chunk 'order or not al'")
        
        # The final message should contain the full text
        final_messages = [msg for msg, is_final, msg_type in results if msg and not is_final]
        if final_messages:
            longest = max(final_messages, key=len)
            assert "Hi. How can" in longest or "order or not" in longest, \
                "Final message should contain accumulated text"
    
    def test_always_use_longest_message(self):
        """Test that we always use the longest accumulated message."""
        # Simulate getting chunks in wrong order or with gaps
        json_lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Short"}]
                }
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "This is a much longer message that contains Short"}]
                }
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Medium length"}]
                }
            }),
        ]
        
        def mock_generator(*args, **kwargs):
            for i, line in enumerate(json_lines):
                is_final = (i == len(json_lines) - 1)
                yield (line, is_final)
        
        with patch('essence.chat.agent.response.streaming_popen_generator', mock_generator):
            with patch('essence.chat.agent.response.os.path.exists', return_value=True):
                with patch('essence.chat.agent.response.os.access', return_value=True):
                    results = list(stream_chat_response_agent(
                        "test message",
                        user_id=123,
                        chat_id=456,
                        line_timeout=30.0,
                        max_total_time=300.0
                    ))
        
        # Should yield the longest message we've seen
        messages = [msg for msg, is_final, msg_type in results if msg and not is_final]
        if messages:
            longest_yielded = max(messages, key=len)
            # Should contain the longest message we saw
            assert "This is a much longer message" in longest_yielded or len(longest_yielded) >= 40


class TestMiddleChunkProblem:
    """Test the specific problem: getting middle chunks like 'order or not al'."""
    
    def test_middle_chunk_extraction(self):
        """Test that we can reproduce the middle chunk extraction issue."""
        # Simulate what might be happening - extracting from a partial JSON field
        # Maybe cursor-agent is outputting incremental deltas, not full messages?
        json_line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "order or not al"  # This is a middle chunk
                    }
                ]
            }
        })
        
        result = _extract_human_readable_from_json_line(json_line)
        # The extraction function will return this - that's correct
        # The problem is in the accumulation logic - we shouldn't yield this if it's shorter
        assert result == "order or not al"
    
    def test_accumulation_skips_middle_chunks(self):
        """Test that accumulation logic skips standalone middle chunks."""
        # Simulate getting chunks out of order or partial chunks
        json_lines = [
            # First chunk
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can"}]
                }
            }),
            # Problem: middle chunk that doesn't contain the first
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "order or not al"}]
                }
            }),
            # Full message that contains both
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can I help you? You can order or not all of the items."}]
                }
            }),
        ]
        
        def mock_generator(*args, **kwargs):
            for i, line in enumerate(json_lines):
                is_final = (i == len(json_lines) - 1)
                yield (line, is_final)
        
        with patch('essence.chat.agent.response.streaming_popen_generator', mock_generator):
            with patch('essence.chat.agent.response.os.path.exists', return_value=True):
                with patch('essence.chat.agent.response.os.access', return_value=True):
                    results = list(stream_chat_response_agent(
                        "test",
                        user_id=123,
                        chat_id=456,
                        line_timeout=30.0,
                        max_total_time=300.0
                    ))
        
        # Extract all non-empty, non-final messages
        messages = [msg for msg, is_final, msg_type in results if msg and not is_final]
        
        # Should NOT have "order or not al" as a standalone message
        # (unless it's part of a longer accumulated message)
        standalone_middle_chunks = [msg for msg in messages if msg == "order or not al"]
        assert len(standalone_middle_chunks) == 0, \
            f"Should not yield standalone middle chunk. Got messages: {messages}"
        
        # The longest message should contain the full text
        if messages:
            longest = max(messages, key=len)
            assert len(longest) > len("order or not al"), \
                f"Longest message should be longer than middle chunk. Got: {longest[:50]}"
    
    def test_partial_text_extraction(self):
        """Test extracting from different JSON structures that might cause partial text."""
        # Maybe cursor-agent outputs text in chunks via a different structure?
        test_cases = [
            # Case 1: Direct text field (should work)
            {
                "type": "assistant",
                "text": "order or not al"
            },
            # Case 2: Nested in result
            {
                "type": "result",
                "subtype": "success",
                "result": "order or not al"
            },
            # Case 3: In message field directly
            {
                "type": "assistant",
                "message": "order or not al"
            },
        ]
        
        for test_case in test_cases:
            json_line = json.dumps(test_case)
            result = _extract_human_readable_from_json_line(json_line)
            # Some of these might extract, some might not
            # The key is that we shouldn't yield short standalone chunks
            if result:
                assert result == "order or not al" or len(result) > len("order or not al")


class TestRealWorldScenario:
    """Test with real-world scenario based on HTTP endpoint output."""
    
    def test_full_message_scenario(self):
        """Test with the actual full message from HTTP endpoint."""
        # Based on the HTTP endpoint response:
        # "Hi. How can I help you today?\n\nI can help with:\n- **Tasks & Projects** — list, create, or manage tasks\n- **Documentation** — search or create docs\n- **Knowledge** — query or store facts\n\nWhat would you like to do?"
        
        full_message = "Hi. How can I help you today?\n\nI can help with:\n- **Tasks & Projects** — list, create, or manage tasks\n- **Documentation** — search or create docs\n- **Knowledge** — query or store facts\n\nWhat would you like to do?"
        
        # Simulate incremental chunks that cursor-agent might send
        chunks = [
            "Hi. How can",
            "Hi. How can I help you today?",
            "Hi. How can I help you today?\n\nI can help with:",
            "Hi. How can I help you today?\n\nI can help with:\n- **Tasks & Projects**",
            full_message
        ]
        
        json_lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": chunk}]
                }
            })
            for chunk in chunks
        ]
        
        def mock_generator(*args, **kwargs):
            for i, line in enumerate(json_lines):
                is_final = (i == len(json_lines) - 1)
                yield (line, is_final)
        
        with patch('essence.chat.agent.response.streaming_popen_generator', mock_generator):
            with patch('essence.chat.agent.response.os.path.exists', return_value=True):
                with patch('essence.chat.agent.response.os.access', return_value=True):
                    results = list(stream_chat_response_agent(
                        "Hi",
                        user_id=39833618,
                        chat_id=39833618,
                        line_timeout=30.0,
                        max_total_time=300.0
                    ))
        
        # Should yield incremental updates
        messages = [msg for msg, is_final, msg_type in results if msg and not is_final]
        
        # Each message should be longer than or equal to the previous (accumulation)
        if len(messages) > 1:
            for i in range(1, len(messages)):
                assert len(messages[i]) >= len(messages[i-1]) or messages[i-1] in messages[i], \
                    f"Message {i} should be longer or contain previous: {messages[i-1][:50]} -> {messages[i][:50]}"
        
        # Final non-empty message should be the full message
        final_non_empty = [msg for msg, is_final, msg_type in results if msg][-1] if results else None
        if final_non_empty and final_non_empty != "":
            # Should contain the full message content
            assert "Tasks & Projects" in final_non_empty
            assert "Documentation" in final_non_empty
            assert len(final_non_empty) > 100
    
    def test_reproduces_middle_chunk_issue(self):
        """Test that reproduces the exact issue: getting 'order or not al' as output."""
        # This test should FAIL if the bug exists, showing that we yield middle chunks
        # Simulate what might be happening in production
        
        # Scenario: cursor-agent might be outputting text deltas, not full messages
        # Or the JSON structure might be different than expected
        problematic_json_lines = [
            # First, we get a partial message
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can"}]
                }
            }),
            # Then we get a middle chunk (this is the problem)
            # This might happen if cursor-agent outputs incremental deltas
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "order or not al"}]
                }
            }),
            # Finally, we get the full message
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hi. How can I help you? You can order or not all items."}]
                }
            }),
        ]
        
        def mock_generator(*args, **kwargs):
            for i, line in enumerate(problematic_json_lines):
                is_final = (i == len(problematic_json_lines) - 1)
                yield (line, is_final)
        
        with patch('essence.chat.agent.response.streaming_popen_generator', mock_generator):
            with patch('essence.chat.agent.response.os.path.exists', return_value=True):
                with patch('essence.chat.agent.response.os.access', return_value=True):
                    results = list(stream_chat_response_agent(
                        "test",
                        user_id=123,
                        chat_id=456,
                        line_timeout=30.0,
                        max_total_time=300.0
                    ))
        
        # Extract all yielded messages (non-final)
        all_messages = [msg for msg, is_final, msg_type in results if msg and not is_final]
        
        # The bug: we should NOT yield "order or not al" as a standalone message
        # We should only yield messages that are longer than what we've seen before
        # OR messages that contain the previous message
        
        # Check: if we have "order or not al" as a standalone message, that's the bug
        standalone_middle = [msg for msg in all_messages if msg == "order or not al"]
        
        if standalone_middle:
            pytest.fail(
                f"BUG REPRODUCED: Yielding standalone middle chunk 'order or not al'. "
                f"All messages: {all_messages}. "
                f"This means the accumulation logic is not working correctly."
            )
        
        # The final message should be the longest one
        if all_messages:
            longest = max(all_messages, key=len)
            assert "Hi. How can" in longest or len(longest) > 20, \
                f"Final message should be the longest accumulated. Got: {longest[:50]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

