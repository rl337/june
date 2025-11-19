"""
Detailed timing test to verify streaming granularity.

This test provides detailed timing information to verify that streaming
captures output with the expected granularity (quarter-second intervals).
"""
import sys
import time
from pathlib import Path

import pytest

# Add chat-service-base to path for imports
# Path: services/telegram/tests/test_stream_timing.py -> services/telegram/tests -> services/telegram -> services -> chat-service-base
base_dir = Path(__file__).parent.parent.parent / "chat-service-base"
sys.path.insert(0, str(base_dir))

from utils.streaming_popen import streaming_popen_generator


@pytest.fixture
def test_program_path(tmp_path):
    """Create a test program that outputs strings at intervals."""
    test_script = tmp_path / "test_stream_output.sh"
    test_script.write_text(
        """#!/bin/bash
# Test program that outputs predefined strings at intervals
for arg in "$@"; do
    echo "$arg"
    sleep 0.25
done
"""
    )
    test_script.chmod(0o755)
    return str(test_script)


def test_detailed_timing_analysis(test_program_path, capsys):
    """Test with detailed timing analysis printed to stdout."""
    test_strings = ["Message1", "Message2", "Message3", "Message4", "Message5"]

    command = [test_program_path] + test_strings

    received_lines = []
    start_time = time.time()
    last_time = start_time

    print("\n=== Streaming Timing Analysis ===")
    print(f"Expected interval: 0.25 seconds")
    print(f"Test strings: {test_strings}\n")

    for line, is_final in streaming_popen_generator(command):
        current_time = time.time()
        elapsed = current_time - start_time
        interval = current_time - last_time

        received_lines.append((line, elapsed, interval))

        print(f"Line {len(received_lines)}: '{line}'")
        print(f"  Total elapsed: {elapsed:.3f}s")
        print(f"  Since previous: {interval:.3f}s")

        last_time = current_time

        if is_final:
            break

    print(f"\n=== Summary ===")
    print(f"Total lines received: {len(received_lines)}")
    print(f"Total time: {time.time() - start_time:.3f}s")

    if len(received_lines) > 1:
        intervals = [r[2] for r in received_lines[1:]]
        avg_interval = sum(intervals) / len(intervals)
        min_interval = min(intervals)
        max_interval = max(intervals)

        print(f"Average interval: {avg_interval:.3f}s")
        print(f"Min interval: {min_interval:.3f}s")
        print(f"Max interval: {max_interval:.3f}s")

        # Verify intervals are reasonable (0.15-0.35s range)
        assert all(
            0.15 <= i <= 0.35 for i in intervals
        ), f"Some intervals outside expected range: {intervals}"

    # Verify we got all messages
    assert len(received_lines) == len(test_strings)
    assert [r[0] for r in received_lines] == test_strings


def test_streaming_performance(test_program_path):
    """Test streaming performance with many messages."""
    # Generate 20 test strings
    test_strings = [f"Message{i:02d}" for i in range(1, 21)]

    command = [test_program_path] + test_strings

    received_lines = []
    start_time = time.time()

    for line, is_final in streaming_popen_generator(command):
        received_lines.append(line)
        if is_final:
            break

    total_time = time.time() - start_time
    expected_time = len(test_strings) * 0.25

    # Verify all messages received
    assert len(received_lines) == len(test_strings)

    # Total time should be approximately expected (with some overhead)
    assert (
        total_time >= expected_time * 0.9
    ), f"Total time {total_time:.3f}s is less than expected {expected_time:.3f}s"
    assert (
        total_time <= expected_time * 1.5
    ), f"Total time {total_time:.3f}s is much more than expected {expected_time:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to show print output
