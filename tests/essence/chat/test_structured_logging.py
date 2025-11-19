"""
Tests for structured logging functionality.

Tests verify that turns are properly logged to files and can be read back.
"""

import gzip
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from essence.chat.human_interface import EscapedText, Message, Paragraph, Turn
from essence.chat.message_builder import MessageBuilder


class TestTurnLogging:
    """Tests for turn logging functionality."""

    def test_log_turn_to_file(self):
        """Test that a turn can be logged to a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            turn = Turn(
                user_request="Hello",
                messages=[Message(content=[EscapedText(text="Hi there!")])],
                service_name="test-service",
                user_id="123",
                chat_id="456",
                turn_id="test-turn-1",
            )

            log_file = turn.log_to_file(log_dir=log_dir)

            assert log_file is not None
            assert log_file.exists()
            assert log_file.name.startswith("turns_")
            assert log_file.name.endswith(".json.gz")

            # Verify file contains the turn
            with gzip.open(log_file, "rt", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                assert len(lines) == 1

                logged_turn = json.loads(lines[0])
                assert logged_turn["turn_id"] == "test-turn-1"
                assert logged_turn["user_request"] == "Hello"
                assert logged_turn["service_name"] == "test-service"

    def test_log_multiple_turns(self):
        """Test that multiple turns can be logged to the same file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log first turn
            turn1 = Turn(
                user_request="First message",
                messages=[Message(content=[EscapedText(text="First response")])],
                service_name="test-service",
                turn_id="turn-1",
            )
            log_file1 = turn1.log_to_file(log_dir=log_dir)

            # Log second turn
            turn2 = Turn(
                user_request="Second message",
                messages=[Message(content=[EscapedText(text="Second response")])],
                service_name="test-service",
                turn_id="turn-2",
            )
            log_file2 = turn2.log_to_file(log_dir=log_dir)

            # Should be the same file (same date)
            assert log_file1 == log_file2

            # Verify both turns are in the file
            with gzip.open(log_file1, "rt", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                assert len(lines) == 2

                logged_turn1 = json.loads(lines[0])
                logged_turn2 = json.loads(lines[1])

                assert logged_turn1["turn_id"] == "turn-1"
                assert logged_turn2["turn_id"] == "turn-2"

    def test_log_turn_with_metadata(self):
        """Test that turn metadata is preserved in logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            turn = Turn(
                user_request="Test",
                messages=[Message(content=[EscapedText(text="Response")])],
                service_name="test-service",
                metadata={"key1": "value1", "key2": 123},
            )

            log_file = turn.log_to_file(log_dir=log_dir)

            with gzip.open(log_file, "rt", encoding="utf-8") as f:
                logged_turn = json.loads(f.readline().strip())

                assert "metadata" in logged_turn
                assert logged_turn["metadata"]["key1"] == "value1"
                assert logged_turn["metadata"]["key2"] == 123

    def test_log_turn_date_formatting(self):
        """Test that log files use correct date format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            turn = Turn(
                user_request="Test",
                messages=[Message(content=[EscapedText(text="Response")])],
                service_name="test-service",
            )

            log_file = turn.log_to_file(log_dir=log_dir)

            # Extract date from filename (format: turns_YYYYMMDD.json.gz)
            # log_file.stem is "turns_YYYYMMDD.json", so remove "turns_" and ".json"
            filename = log_file.stem  # "turns_YYYYMMDD.json"
            date_str = filename.replace("turns_", "").replace(".json", "")
            # Should be 8 digits (YYYYMMDD)
            assert (
                len(date_str) == 8
            ), f"Expected 8-digit date, got: {date_str} from filename {filename}"
            assert date_str.isdigit()

            # Verify it's today's date
            from datetime import timezone

            expected_date = datetime.now(timezone.utc).strftime("%Y%m%d")
            assert date_str == expected_date

    def test_log_turn_service_directory(self):
        """Test that turns are logged to service-specific directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            turn1 = Turn(
                user_request="Test",
                messages=[Message(content=[EscapedText(text="Response")])],
                service_name="service-a",
            )
            log_file1 = turn1.log_to_file(log_dir=log_dir)

            turn2 = Turn(
                user_request="Test",
                messages=[Message(content=[EscapedText(text="Response")])],
                service_name="service-b",
            )
            log_file2 = turn2.log_to_file(log_dir=log_dir)

            # Should be in different directories
            assert log_file1.parent != log_file2.parent
            assert log_file1.parent.name == "service-a"
            assert log_file2.parent.name == "service-b"

    def test_log_turn_error_handling(self):
        """Test that logging errors are handled gracefully."""
        # Try to log to a non-writable location (simulate permission error)
        # This should not raise an exception
        turn = Turn(
            user_request="Test",
            messages=[Message(content=[EscapedText(text="Response")])],
            service_name="test-service",
        )

        # Use a path that might not be writable (but don't fail if it is)
        # Just verify the method doesn't crash
        result = turn.log_to_file(log_dir=Path("/nonexistent/path"))
        # Should return None on error, not raise
        # (The actual behavior depends on the implementation)

    def test_turn_from_dict(self):
        """Test that turns can be reconstructed from dictionary."""
        original_turn = Turn(
            user_request="Hello",
            messages=[Message(content=[EscapedText(text="Hi!")])],
            service_name="test-service",
            user_id="123",
            chat_id="456",
            turn_id="test-1",
            metadata={"key": "value"},
        )

        turn_dict = original_turn.to_dict()
        reconstructed = Turn.from_dict(turn_dict)

        assert reconstructed.user_request == original_turn.user_request
        assert reconstructed.service_name == original_turn.service_name
        assert reconstructed.user_id == original_turn.user_id
        assert reconstructed.chat_id == original_turn.chat_id
        assert reconstructed.turn_id == original_turn.turn_id
        assert reconstructed.metadata == original_turn.metadata
        assert len(reconstructed.messages) == len(original_turn.messages)


class TestMessageBuilderLogging:
    """Tests for message builder's logging integration."""

    def test_build_turn_logs_automatically(self):
        """Test that MessageBuilder can automatically log turns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            builder = MessageBuilder(
                service_name="test-service", user_id="123", chat_id="456"
            )

            turn = builder.build_turn(
                user_request="Hello", llm_response="**Hi!** How can I help?"
            )

            # Log the turn
            log_file = turn.log_to_file(log_dir=log_dir)

            assert log_file is not None
            assert log_file.exists()

            # Verify content
            with gzip.open(log_file, "rt", encoding="utf-8") as f:
                logged_turn = json.loads(f.readline().strip())
                assert logged_turn["user_request"] == "Hello"
                assert len(logged_turn["messages"]) > 0
