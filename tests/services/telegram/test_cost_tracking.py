"""
Tests for cost tracking functionality.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from essence.services.telegram.cost_tracking import (
    calculate_stt_cost,
    calculate_tts_cost,
    calculate_llm_cost,
    record_cost,
    get_user_costs,
    get_conversation_costs,
    generate_billing_report,
    get_conversation_id_from_user_chat,
    get_pricing,
)


class TestCostCalculation:
    """Tests for cost calculation functions."""

    def test_calculate_stt_cost(self):
        """Test STT cost calculation."""
        # 1 minute of audio
        cost = calculate_stt_cost(60.0)
        assert cost > 0
        assert isinstance(cost, float)

        # 30 seconds of audio
        cost_30s = calculate_stt_cost(30.0)
        assert cost_30s == cost / 2  # Should be half the cost

    def test_calculate_tts_cost(self):
        """Test TTS cost calculation."""
        # 1 minute of audio
        cost = calculate_tts_cost(60.0)
        assert cost > 0
        assert isinstance(cost, float)

        # 30 seconds of audio
        cost_30s = calculate_tts_cost(30.0)
        assert cost_30s == cost / 2  # Should be half the cost

    def test_calculate_llm_cost_with_tokens(self):
        """Test LLM cost calculation with tokens."""
        # 1000 input tokens, 500 output tokens
        cost = calculate_llm_cost(input_tokens=1000, output_tokens=500)
        assert cost > 0
        assert isinstance(cost, float)

    def test_calculate_llm_cost_with_characters(self):
        """Test LLM cost calculation with characters (fallback)."""
        # 4000 input characters (~1000 tokens), 2000 output characters (~500 tokens)
        cost = calculate_llm_cost(input_characters=4000, output_characters=2000)
        assert cost > 0
        assert isinstance(cost, float)

    def test_calculate_llm_cost_mixed(self):
        """Test LLM cost calculation with tokens and characters."""
        # Tokens take precedence
        cost_tokens = calculate_llm_cost(input_tokens=1000, output_tokens=500)
        cost_chars = calculate_llm_cost(input_characters=4000, output_characters=2000)
        # Should be similar (within reasonable range)
        assert abs(cost_tokens - cost_chars) < 0.01


class TestCostRecording:
    """Tests for cost recording functions."""

    @patch("essence.services.telegram.cost_tracking.get_db_connection")
    def test_record_cost(self, mock_get_conn):
        """Test recording a cost entry."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Record cost
        result = record_cost(
            service="stt",
            user_id="user123",
            conversation_id="conv456",
            cost=0.001,
            metadata={"duration": 10.0},
        )

        assert result is True
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("essence.services.telegram.cost_tracking.get_db_connection")
    def test_record_cost_without_conversation(self, mock_get_conn):
        """Test recording cost without conversation_id."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Record cost
        result = record_cost(service="llm", user_id="user123", cost=0.002)

        assert result is True
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


class TestCostQueries:
    """Tests for cost query functions."""

    @patch("essence.services.telegram.cost_tracking.get_db_connection")
    def test_get_user_costs(self, mock_get_conn):
        """Test getting user costs."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock(cursor_factory=None)
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Mock query results
        service_costs = [
            {
                "service": "stt",
                "usage_count": 10,
                "total_cost": 0.01,
                "avg_cost": 0.001,
            },
            {"service": "llm", "usage_count": 5, "total_cost": 0.02, "avg_cost": 0.004},
        ]
        mock_cursor.fetchall.side_effect = [
            service_costs,  # Service costs query
            [{"total_cost": 0.03}],  # Total cost query
        ]

        costs = get_user_costs("user123")

        assert costs["user_id"] == "user123"
        assert costs["total_cost"] == 0.03
        assert "stt" in costs["services"]
        assert "llm" in costs["services"]
        assert costs["services"]["stt"]["usage_count"] == 10

    @patch("essence.services.telegram.cost_tracking.get_db_connection")
    def test_get_conversation_costs(self, mock_get_conn):
        """Test getting conversation costs."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock(cursor_factory=None)
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Mock query results
        service_costs = [
            {"service": "stt", "usage_count": 2, "total_cost": 0.002, "avg_cost": 0.001}
        ]
        mock_cursor.fetchall.side_effect = [
            service_costs,  # Service costs query
            [{"total_cost": 0.002}],  # Total cost query
        ]

        costs = get_conversation_costs("conv456")

        assert costs["conversation_id"] == "conv456"
        assert costs["total_cost"] == 0.002
        assert "stt" in costs["services"]

    @patch("essence.services.telegram.cost_tracking.get_db_connection")
    def test_generate_billing_report(self, mock_get_conn):
        """Test generating billing report."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock(cursor_factory=None)
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Mock query results
        entries = [
            {
                "id": "entry1",
                "service": "stt",
                "conversation_id": "conv1",
                "cost": 0.001,
                "metadata": {"duration": 10.0},
                "created_at": datetime.now(),
            }
        ]
        service_summary = [
            {
                "service": "stt",
                "usage_count": 1,
                "total_cost": 0.001,
                "min_cost": 0.001,
                "max_cost": 0.001,
                "avg_cost": 0.001,
            }
        ]
        mock_cursor.fetchall.side_effect = [
            entries,  # Detailed entries
            service_summary,  # Service summary
            [{"total_cost": 0.001}],  # Total cost
        ]

        report = generate_billing_report("user123")

        assert report["user_id"] == "user123"
        assert report["total_cost"] == 0.001
        assert "stt" in report["service_breakdown"]
        assert len(report["entries"]) == 1


class TestConversationID:
    """Tests for conversation ID helper function."""

    @patch("essence.services.telegram.cost_tracking.get_db_connection")
    def test_get_conversation_id_from_user_chat(self, mock_get_conn):
        """Test getting conversation ID from user_id and chat_id."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Mock query result
        mock_cursor.fetchone.return_value = ("conv-uuid-123",)

        conv_id = get_conversation_id_from_user_chat("user123", "chat456")

        assert conv_id == "conv-uuid-123"
        mock_cursor.execute.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("essence.services.telegram.cost_tracking.get_db_connection")
    def test_get_conversation_id_not_found(self, mock_get_conn):
        """Test getting conversation ID when not found."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Mock query result - no conversation found
        mock_cursor.fetchone.return_value = None

        conv_id = get_conversation_id_from_user_chat("user123", "chat456")

        assert conv_id is None


class TestPricing:
    """Tests for pricing functions."""

    def test_get_pricing_default(self):
        """Test getting default pricing."""
        pricing = get_pricing("stt")
        assert "per_minute" in pricing
        assert pricing["per_minute"] > 0

    @patch.dict("os.environ", {"STT_PRICING": '{"per_minute": 0.01}'})
    def test_get_pricing_from_env(self):
        """Test getting pricing from environment variable."""
        pricing = get_pricing("stt")
        assert pricing["per_minute"] == 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
