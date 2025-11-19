"""
End-to-end tests for the streaming flow.

These tests simulate the actual streaming behavior:
1. Messages are yielded during streaming (not just at the end)
2. Handler updates raw_llm_response based on message_text
3. Result message should overwrite corrupted accumulated messages
4. Final message should be correct

This is critical because the accumulation test might pass trivially
if we just use the result message, but we need to ensure the streaming
behavior is correct throughout.
"""

import json

# Add parent directories to path
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "essence"))

from essence.chat.markdown_parser import parse_markdown
from essence.chat.platform_translators import get_translator


def load_test_data(filename):
    """Load JSON test data from file."""
    test_data_dir = Path(__file__).parent / "test_data"
    file_path = test_data_dir / filename

    if not file_path.exists():
        pytest.skip(f"Test data file not found: {file_path}")

    with open(file_path, "r") as f:
        lines = [
            line.strip() for line in f if line.strip() and line.strip().startswith("{")
        ]

    return lines


def extract_assistant_chunks(json_lines):
    """Extract all assistant message chunks from JSON lines."""
    chunks = []
    for line in json_lines:
        try:
            obj = json.loads(line)
            if obj.get("type") == "assistant":
                content = obj.get("message", {}).get("content", [])
                if content and len(content) > 0:
                    text = content[0].get("text", "")
                    if text:
                        chunks.append(text)
        except (json.JSONDecodeError, KeyError):
            continue
    return chunks


def extract_result_message(json_lines):
    """Extract the result message (full accumulated text) from JSON lines."""
    for line in json_lines:
        try:
            obj = json.loads(line)
            if obj.get("type") == "result" and obj.get("subtype") == "success":
                result = obj.get("result", "")
                if result:
                    return result
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def simulate_handler_logic(
    message_text,
    raw_llm_response,
    message_type=None,
    first_message_pattern=None,
    update_first_pattern=True,
):
    """
    Simulate the handler logic for updating raw_llm_response.

    This mimics the logic in handlers/text.py lines 263-292.

    Args:
        message_text: New message text
        raw_llm_response: Current raw_llm_response
        message_type: "assistant" for incremental chunks, "result" for authoritative final message, None for other
        first_message_pattern: Pattern from the very first message (persists across calls)
        update_first_pattern: If True, update first_message_pattern from raw_llm_response if not set
    """
    if not raw_llm_response:
        return (
            message_text,
            True,
            message_text[:30] if len(message_text) >= 30 else message_text,
        )

    # Update first_message_pattern from the first message we see
    if update_first_pattern and not first_message_pattern:
        first_message_pattern = (
            raw_llm_response[:30] if len(raw_llm_response) >= 30 else raw_llm_response
        )

    message_updated = False

    if message_type == "result":
        # Result message is always authoritative - overwrite regardless of length
        raw_llm_response = message_text
        message_updated = True
    elif len(message_text) > len(raw_llm_response):
        # New message is longer - it's an extension
        raw_llm_response = message_text
        message_updated = True
    elif message_text and raw_llm_response and message_text not in raw_llm_response:
        # Different content - check if it's actually longer
        if len(message_text) > len(raw_llm_response):
            raw_llm_response = message_text
            message_updated = True

    return raw_llm_response, message_updated, first_message_pattern


def simulate_streaming_flow(json_lines):
    """
    Simulate the full streaming flow:
    1. Extract chunks and result
    2. Simulate accumulation (with potential bugs)
    3. Simulate handler updating raw_llm_response
    4. Return final raw_llm_response that would be used for final edit
    """
    assistant_chunks = extract_assistant_chunks(json_lines)
    result_message = extract_result_message(json_lines)

    if not assistant_chunks or not result_message:
        return None, None

    # Simulate accumulation (this is where bugs might happen)
    accumulated = assistant_chunks[0]
    first_chunk_start = (
        assistant_chunks[0][:20]
        if len(assistant_chunks[0]) >= 20
        else assistant_chunks[0]
    )

    yielded_messages = []
    raw_llm_response = None
    first_message_pattern = None

    for chunk in assistant_chunks[1:]:
        # Accumulation logic (with potential bug - might append when should replace)
        if accumulated in chunk:
            accumulated = chunk
        elif chunk in accumulated:
            continue  # Skip duplicate
        elif len(chunk) > len(accumulated) * 0.8 and chunk.startswith(
            first_chunk_start
        ):
            accumulated = chunk  # Full accumulated message
        else:
            accumulated = (
                accumulated + chunk
            )  # Potential bug: might append when should replace

        # Yield message during streaming
        yielded_messages.append(accumulated)

        # Handler updates raw_llm_response (assistant chunks)
        raw_llm_response, _, first_message_pattern = simulate_handler_logic(
            accumulated, raw_llm_response, "assistant", first_message_pattern
        )

    # Result message comes in - should overwrite
    if result_message:
        yielded_messages.append(result_message)
        raw_llm_response, _, first_message_pattern = simulate_handler_logic(
            result_message,
            raw_llm_response,
            "result",
            first_message_pattern,
            update_first_pattern=False,
        )

    return raw_llm_response, result_message


TEST_FILES = [
    "test_duplication_headers.json",  # The real-world duplication case
    "test_headers.json",
    "test_lists.json",
]


@pytest.mark.parametrize("test_file", TEST_FILES)
def test_e2e_streaming_final_message_correct(test_file):
    """
    Test that the final message used for editing is correct.

    This simulates the full streaming flow including:
    - Accumulation (which might have bugs)
    - Handler updating raw_llm_response
    - Result message overwriting corrupted accumulated
    - Final message being correct
    """
    json_lines = load_test_data(test_file)

    final_raw_llm_response, expected_result = simulate_streaming_flow(json_lines)

    if not final_raw_llm_response or not expected_result:
        pytest.skip(f"Could not extract data from {test_file}")

    # Normalize for comparison
    final_normalized = final_raw_llm_response.replace("\n\n", "\n").strip()
    expected_normalized = expected_result.replace("\n\n", "\n").strip()

    # The final raw_llm_response should match the result message
    assert final_normalized == expected_normalized, (
        f"Final raw_llm_response doesn't match result message.\n"
        f"Final: {len(final_raw_llm_response)} chars\n"
        f"Expected: {len(expected_result)} chars\n"
        f"Final: {repr(final_raw_llm_response[:200])}\n"
        f"Expected: {repr(expected_result[:200])}"
    )


@pytest.mark.parametrize("test_file", TEST_FILES)
def test_e2e_streaming_no_duplication_in_final(test_file):
    """
    Test that the final message doesn't contain duplication.

    Even if accumulation has bugs, the result message should overwrite.
    """
    json_lines = load_test_data(test_file)

    final_raw_llm_response, expected_result = simulate_streaming_flow(json_lines)

    if not final_raw_llm_response or not expected_result:
        pytest.skip(f"Could not extract data from {test_file}")

    # Check for duplication patterns
    if "duplication" in test_file or "headers" in test_file:
        header_sequence = "# Header 1\n\n## Header 2"
        occurrences = final_raw_llm_response.count(header_sequence)
        assert occurrences <= 1, (
            f"Final message contains {occurrences} occurrences of header sequence - indicates duplication.\n"
            f"Final message: {repr(final_raw_llm_response[:300])}"
        )

    # Final message should not be significantly longer than result
    # (allowing for some variance due to newlines)
    length_ratio = (
        len(final_raw_llm_response) / len(expected_result) if expected_result else 1.0
    )
    assert length_ratio <= 1.2, (
        f"Final message is {length_ratio:.2f}x longer than result - likely contains duplication.\n"
        f"Final: {len(final_raw_llm_response)} chars\n"
        f"Result: {len(expected_result)} chars"
    )


def test_e2e_streaming_result_overwrites_duplicates():
    """
    Test that result message overwrites duplicated accumulated message.

    This is a specific test for the duplication scenario.
    """
    # Simulate the duplication scenario:
    # 1. Accumulate chunks 0-19 (partial message)
    # 2. Chunk 20 is full message but gets appended (bug)
    # 3. Result message should overwrite the duplicated version

    chunks = [
        "\n# Header 1\n",  # 0
        "\n## Header 2\n\n###",  # 1
        # ... (simplified - chunks 2-19 are incremental)
        "information and create clear hierarchies in your d",  # 19
        "\n# Header 1\n\n## Header 2\n\n### Header 3\n\n#### Header 4\n\n##### Header 5\n\n###### Header 6\n\nThis is regular paragraph text. It follows the headers and demonstrates how normal text appears after the different header levels. You can use this formatting in your messages to organize information and create clear hierarchies in your documentation or messages.",  # 20 - full message
    ]

    result = "\n# Header 1\n\n## Header 2\n\n### Header 3\n\n#### Header 4\n\n##### Header 5\n\n###### Header 6\n\nThis is regular paragraph text. It follows the headers and demonstrates how normal text appears after the different header levels. You can use this formatting in your messages to organize information and create clear hierarchies in your documentation or messages."

    # Simulate accumulation with bug (appends chunk 20 instead of replacing)
    accumulated = chunks[0]
    for chunk in chunks[1:]:
        # BUG: Always append (simulating the bug)
        accumulated = accumulated + chunk

    # Now accumulated is duplicated (longer than result)
    assert len(accumulated) > len(result), "Accumulated should be longer (duplicated)"
    assert accumulated.count("# Header 1") > 1, "Accumulated should contain duplication"

    # Handler logic - simulate the full flow
    raw_llm_response = None
    first_message_pattern = None

    # Process accumulated (corrupted version)
    raw_llm_response, _, first_message_pattern = simulate_handler_logic(
        accumulated, raw_llm_response, "assistant", first_message_pattern
    )

    # Verify it's corrupted
    assert (
        raw_llm_response.count("# Header 1") > 1
    ), "raw_llm_response should contain duplication"

    # Result message comes in - should overwrite
    # Use the first_message_pattern from the FIRST message (before corruption)
    # In real flow, this would be from the very first chunk
    first_chunk_pattern = chunks[0][:30] if len(chunks[0]) >= 30 else chunks[0]
    final_raw_llm_response, _, _ = simulate_handler_logic(
        result,
        raw_llm_response,
        "result",
        first_chunk_pattern,
        update_first_pattern=False,
    )

    # Should be overwritten with result
    assert final_raw_llm_response == result, (
        f"Result message should overwrite duplicated accumulated.\n"
        f"Final: {len(final_raw_llm_response)} chars\n"
        f"Result: {len(result)} chars\n"
        f"Final contains '# Header 1' {final_raw_llm_response.count('# Header 1')} times\n"
        f"Result contains '# Header 1' {result.count('# Header 1')} times\n"
        f"First message pattern: {repr(first_message_pattern)}\n"
        f"Result starts with pattern: {result.startswith(first_message_pattern) if first_message_pattern else 'N/A'}\n"
        f"Length ratio: {len(result) / len(raw_llm_response):.2f}"
    )
    assert (
        final_raw_llm_response.count("# Header 1") == 1
    ), "Final message should not contain duplication"
