"""
Test streaming Popen implementation to verify granularity and responsiveness.

This test verifies that we can stream output from a subprocess in real-time
with proper granularity (quarter-second intervals).
"""
import sys
import time
import pytest
from pathlib import Path

from essence.chat.utils.streaming_popen import streaming_popen_generator


@pytest.fixture
def test_program_path(tmp_path):
    """Create a test program that outputs strings at intervals."""
    test_script = tmp_path / "test_stream_output.sh"
    test_script.write_text("""#!/bin/bash
# Test program that outputs predefined strings at intervals
# Usage: test_stream_output.sh "string1" "string2" "string3" ...

for arg in "$@"; do
    echo "$arg"
    sleep 0.25
done
""")
    test_script.chmod(0o755)
    return str(test_script)


def test_streaming_granularity(test_program_path):
    """Test that streaming captures output with quarter-second granularity."""
    test_strings = ["Hello", "World", "Test", "Streaming", "Output"]
    
    # Run the test program
    command = [test_program_path] + test_strings
    
    # Collect output with timestamps
    received_lines = []
    start_time = time.time()
    
    for line, is_final in streaming_popen_generator(command):
        received_lines.append((line, time.time() - start_time))
        if is_final:
            break
    
    # Verify we received all strings
    assert len(received_lines) == len(test_strings), \
        f"Expected {len(test_strings)} lines, got {len(received_lines)}"
    
    # Verify content matches
    for i, (line, _) in enumerate(received_lines):
        assert line == test_strings[i], \
            f"Line {i}: expected '{test_strings[i]}', got '{line}'"
    
    # Verify timing - each line should arrive roughly 0.25s after the previous
    # Allow some tolerance (0.1s) for system delays
    for i in range(1, len(received_lines)):
        time_diff = received_lines[i][1] - received_lines[i-1][1]
        assert 0.15 <= time_diff <= 0.35, \
            f"Line {i} arrived {time_diff:.3f}s after previous (expected ~0.25s)"


def test_streaming_immediate_output(test_program_path):
    """Test that first output arrives quickly (not buffered)."""
    test_strings = ["First", "Second"]
    
    command = [test_program_path] + test_strings
    
    received_lines = []
    start_time = time.time()
    first_line_time = None
    
    for line, is_final in streaming_popen_generator(command):
        if not received_lines:
            first_line_time = time.time() - start_time
        received_lines.append(line)
        if is_final:
            break
    
    # First line should arrive quickly (< 0.5s)
    assert first_line_time is not None, "No output received"
    assert first_line_time < 0.5, \
        f"First line took {first_line_time:.3f}s (expected < 0.5s)"


def test_streaming_complete_output(test_program_path):
    """Test that all output is captured, including final line."""
    test_strings = ["A", "B", "C", "D", "E"]
    
    command = [test_program_path] + test_strings
    
    received_lines = []
    for line, is_final in streaming_popen_generator(command):
        received_lines.append(line)
        if is_final:
            break
    
    assert len(received_lines) == len(test_strings)
    assert received_lines == test_strings


def test_streaming_empty_output():
    """Test handling of program with no output."""
    command = ["/bin/echo", ""]
    
    received_lines = []
    for line, is_final in streaming_popen_generator(command):
        if line:
            received_lines.append(line)
        if is_final:
            break
    
    # Empty echo should produce no lines (empty line is stripped)
    assert len(received_lines) == 0


def test_streaming_multiline_output():
    """Test handling of multiline output."""
    command = ["/bin/sh", "-c", "echo 'Line 1'; sleep 0.1; echo 'Line 2'; sleep 0.1; echo 'Line 3'"]
    
    received_lines = []
    for line, is_final in streaming_popen_generator(command):
        received_lines.append(line)
        if is_final:
            break
    
    assert len(received_lines) == 3
    assert received_lines[0] == "Line 1"
    assert received_lines[1] == "Line 2"
    assert received_lines[2] == "Line 3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

