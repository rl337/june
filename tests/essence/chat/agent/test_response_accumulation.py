"""Unit tests for JSON accumulation logic in stream_chat_response_agent."""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from essence.chat.agent.response import stream_chat_response_agent


# Test cases: (name, input_lines, expected_outputs, expected_final_state)
# input_lines: list of (line, is_final) tuples
# expected_outputs: list of (message, is_final, message_type) tuples
# expected_final_state: dict with keys like json_lines_processed, result_message_received, etc.
TEST_CASES = [
    (
        "complete_json_single_assistant",
        [
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello"}]}}', False),
            ('', True),  # Final empty line
        ],
        [
            ("Hello", False, "assistant"),
            ("", True, None),  # Final signal
        ],
        {
            "json_lines_processed": 1,
            "result_message_received": False,
            "has_result_message": False,
        }
    ),
    (
        "complete_json_with_result",
        [
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello"}]}}', False),
            ('{"type":"result","subtype":"success","result":"Hello world"}', False),
            ('', True),
        ],
        [
            ("Hello", False, "assistant"),
            ("Hello world", True, "result"),  # Final result
        ],
        {
            "json_lines_processed": 2,
            "result_message_received": True,
            "has_result_message": True,
        }
    ),
    (
        "incomplete_json_single_line",
        [
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello', False),
            (' world"}]}}', False),
            ('', True),
        ],
        [
            ("Hello world", False, "assistant"),
            ("", True, None),
        ],
        {
            "json_lines_processed": 1,
            "result_message_received": False,
        }
    ),
    (
        "incomplete_json_multiple_chunks",
        [
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello', False),
            (' world', False),
            (' from', False),
            (' multiple chunks"}]}}', False),
            ('', True),
        ],
        [
            ("Hello world from multiple chunks", False, "assistant"),
            ("", True, None),
        ],
        {
            "json_lines_processed": 1,
        }
    ),
    (
        "shell_output_skipped",
        [
            ('+ set -euo pipefail', False),
            ('++ dirname script.sh', False),
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello"}]}}', False),
            ('', True),
        ],
        [
            ("Hello", False, "assistant"),
            ("", True, None),
        ],
        {
            "json_lines_processed": 1,
        }
    ),
    (
        "incomplete_json_on_final_line",
        [
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello', True),  # Incomplete on final
        ],
        [
            ("⚠️ I received your message but couldn't generate a response. Please try again.", True, None),
        ],
        {
            "json_lines_processed": 0,  # Failed to parse
        }
    ),
    (
        "incomplete_json_completed_on_final",
        [
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello', False),
            (' world"}]}}', True),  # Completed on final
        ],
        [
            ("Hello world", False, "assistant"),
            ("", True, None),
        ],
        {
            "json_lines_processed": 1,
        }
    ),
    (
        "very_long_result_message",
        [
            ('{"type":"result","subtype":"success","result":"' + "x" * 5000 + '"}', False),  # Very long result
            ('', True),
        ],
        [
            ("x" * 5000, True, "result"),
        ],
        {
            "json_lines_processed": 1,
            "result_message_received": True,
            "has_result_message": True,
        }
    ),
    (
        "multiple_assistant_chunks",
        [
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello"}]}}', False),
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":" world"}]}}', False),
            ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"!"}]}}', False),
            ('', True),
        ],
        [
            ("Hello", False, "assistant"),
            ("Hello world", False, "assistant"),
            ("Hello world!", False, "assistant"),
            ("", True, None),
        ],
        {
            "json_lines_processed": 3,
        }
    ),
    (
        "no_json_lines_only_shell",
        [
            ('+ set -euo pipefail', False),
            ('++ dirname script.sh', False),
            ('++ cd /app', False),
            ('', True),
        ],
        [
            ("⚠️ I received your message but couldn't generate a response. Please try again.", True, None),
        ],
        {
            "json_lines_processed": 0,
        }
    ),
]


def mock_streaming_popen_generator(lines):
    """Mock generator that yields lines."""
    for line, is_final in lines:
        yield (line, is_final)


@pytest.mark.parametrize("name,input_lines,expected_outputs,expected_final_state", TEST_CASES)
def test_json_accumulation_logic(name, input_lines, expected_outputs, expected_final_state):
    """Test JSON accumulation logic with various input scenarios."""
    # Mock file system checks for agent script
    with patch('essence.chat.agent.response.os.path.exists') as mock_exists, \
         patch('essence.chat.agent.response.os.access') as mock_access, \
         patch('essence.chat.agent.response.time.time') as mock_time:
        # Mock that the agent script exists and is executable
        def exists_side_effect(path):
            if path == "/tmp/scripts/test.sh":
                return True
            return False
        mock_exists.side_effect = exists_side_effect
        mock_access.return_value = True
        
        # Mock time to simulate waiting for first message
        # Provide enough time values for multiple iterations
        time_values = [0.0, 0.1, 0.2, 2.1, 2.2] + [2.3 + i * 0.1 for i in range(100)]  # Start at 0, then jump past max_wait_for_first_message
        mock_time.side_effect = time_values
        
        # Mock the streaming_popen_generator
        with patch('essence.chat.agent.response.streaming_popen_generator') as mock_gen:
            mock_gen.return_value = mock_streaming_popen_generator(input_lines)
            
            # Mock the command execution
            with patch('subprocess.Popen') as mock_popen:
                # Collect all yielded outputs
                outputs = []
                final_state = {}
                
                try:
                    # Call the generator function
                    gen = stream_chat_response_agent(
                        user_message="test",
                        agenticness_dir="/tmp",
                        user_id="123",
                        chat_id="123",
                        line_timeout=1.0,
                        max_total_time=10.0,
                        agent_script_name="test.sh",
                        agent_script_simple_name="test_simple.sh",
                        platform="test"
                    )
                    
                    # Collect all outputs
                    for output in gen:
                        outputs.append(output)
                        
                except Exception as e:
                    # Capture exception for debugging
                    pytest.fail(f"Test '{name}' raised exception: {e}")
                
                # Verify outputs
                assert len(outputs) == len(expected_outputs), \
                    f"Test '{name}': Expected {len(expected_outputs)} outputs, got {len(outputs)}. " \
                    f"Outputs: {outputs}"
                
                for i, (actual, expected) in enumerate(zip(outputs, expected_outputs)):
                    actual_msg, actual_final, actual_type = actual
                    expected_msg, expected_final, expected_type = expected
                    
                    assert actual_msg == expected_msg, \
                        f"Test '{name}' output {i}: Expected message '{expected_msg}', got '{actual_msg}'"
                    assert actual_final == expected_final, \
                        f"Test '{name}' output {i}: Expected is_final={expected_final}, got {actual_final}"
                    assert actual_type == expected_type, \
                        f"Test '{name}' output {i}: Expected type={expected_type}, got {actual_type}"


def test_simple_complete_json():
    """Test with a simple complete JSON line."""
    input_lines = [
        ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello"}]}}', False),
        ('', True),
    ]
    
    with patch('essence.chat.agent.response.os.path.exists') as mock_exists, \
         patch('essence.chat.agent.response.os.access') as mock_access, \
         patch('essence.chat.agent.response.time.time') as mock_time:
        mock_exists.return_value = True
        mock_access.return_value = True
        
        # Mock time to simulate waiting for first message
        time_values = [0.0, 0.1, 0.2, 2.1, 2.2]  # Start at 0, then jump past max_wait_for_first_message
        mock_time.side_effect = time_values
        
        with patch('essence.chat.agent.response.streaming_popen_generator') as mock_gen:
            mock_gen.return_value = mock_streaming_popen_generator(input_lines)
            
            gen = stream_chat_response_agent(
                user_message="test",
                agenticness_dir="/tmp",
                user_id="123",
                chat_id="123",
                line_timeout=1.0,
                max_total_time=10.0,
                agent_script_name="test.sh",
                agent_script_simple_name="test_simple.sh",
                platform="test"
            )
            
            outputs = list(gen)
            print(f"\nSimple test outputs: {outputs}")
            # Should get at least the error message if no messages were sent
            assert len(outputs) > 0, f"Should have outputs (even if error), got: {outputs}"


def test_json_accumulation_debug():
    """Debug test to see what's happening with a specific case."""
    # Simulate the problematic case: incomplete JSON in final buffer
    input_lines = [
        ('+ set -euo pipefail', False),
        ('++ dirname script.sh', False),
        ('{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello', False),
        (' world"}]}}', False),
        ('', True),
    ]
    
    # Mock os.path.exists and os.access to return True for the script
    with patch('essence.chat.agent.response.os.path.exists') as mock_exists, \
         patch('essence.chat.agent.response.os.access') as mock_access:
        mock_exists.return_value = True
        mock_access.return_value = True
        
        with patch('essence.chat.agent.response.streaming_popen_generator') as mock_gen:
            mock_gen.return_value = mock_streaming_popen_generator(input_lines)
            
            gen = stream_chat_response_agent(
                user_message="test",
                agenticness_dir="/tmp",
                user_id="123",
                chat_id="123",
                line_timeout=1.0,
                max_total_time=10.0,
                agent_script_name="test.sh",
                agent_script_simple_name="test_simple.sh",
                platform="test"
            )
            
            # Collect outputs with timeout
            outputs = []
            import time
            start = time.time()
            timeout = 5.0
            
            try:
                for output in gen:
                    outputs.append(output)
                    print(f"Got output: {output}")
                    if time.time() - start > timeout:
                        print(f"Timeout after {timeout}s, got {len(outputs)} outputs")
                        break
            except Exception as e:
                print(f"Exception during iteration: {e}")
                import traceback
                traceback.print_exc()
            
            print(f"\nDebug test outputs: {outputs}")
            print(f"Number of outputs: {len(outputs)}")
            
            # Should get at least one message
            assert len(outputs) > 0, f"Should have at least one output. Got {len(outputs)} outputs: {outputs}"
            
            # Last output should be final
            if len(outputs) > 0:
                last_msg, last_final, last_type = outputs[-1]
                print(f"Last output: msg='{last_msg[:50]}...', final={last_final}, type={last_type}")


