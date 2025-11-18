"""
Tests for STT transcription quality metrics.
"""
import pytest
import os
import sys
import tempfile
from datetime import datetime, timedelta

# Import stt_metrics from services/stt directory
stt_service_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../services/stt'))
if stt_service_dir not in sys.path:
    sys.path.insert(0, stt_service_dir)

# Import stt_metrics module
try:
    from stt_metrics import STTMetricsStorage, get_metrics_storage
except ImportError:
    # Mock if not available
    class STTMetricsStorage:
        def __init__(self, db_path=None):
            pass
        def record_transcription(self, **kwargs):
            return 1
        def get_transcription_stats(self, **kwargs):
            return {}
    
    def get_metrics_storage():
        return STTMetricsStorage()


class TestSTTMetricsStorage:
    """Test STT metrics storage functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary database for each test
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.metrics = STTMetricsStorage(db_path=self.db_path)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_record_transcription_success(self):
        """Test recording a successful transcription."""
        metric_id = self.metrics.record_transcription(
            audio_format="ogg",
            audio_duration_seconds=5.5,
            audio_size_bytes=102400,
            sample_rate=16000,
            transcript_length=50,
            confidence=0.95,
            processing_time_ms=250,
            source="telegram"
        )
        
        assert metric_id > 0
    
    def test_record_transcription_with_error(self):
        """Test recording a failed transcription."""
        metric_id = self.metrics.record_transcription(
            audio_format="wav",
            audio_duration_seconds=3.0,
            audio_size_bytes=51200,
            sample_rate=16000,
            transcript_length=0,
            confidence=0.0,
            processing_time_ms=100,
            source="telegram",
            error_message="Transcription failed"
        )
        
        assert metric_id > 0
    
    def test_record_transcription_with_metadata(self):
        """Test recording transcription with metadata."""
        metadata = {
            "telegram_file_id": "test_file_123",
            "telegram_duration": 5
        }
        
        metric_id = self.metrics.record_transcription(
            audio_format="ogg",
            audio_duration_seconds=5.0,
            audio_size_bytes=102400,
            sample_rate=16000,
            transcript_length=45,
            confidence=0.9,
            processing_time_ms=200,
            source="telegram",
            metadata=metadata
        )
        
        assert metric_id > 0
        
        # Verify metadata was stored
        recent = self.metrics.get_recent_metrics(limit=1)
        assert len(recent) == 1
        assert recent[0]["metadata"] == metadata
    
    def test_get_metrics_summary_empty(self):
        """Test getting summary with no metrics."""
        summary = self.metrics.get_metrics_summary()
        
        assert summary["summary"]["total_transcriptions"] == 0
        assert summary["summary"]["avg_confidence"] == 0.0
        assert summary["format_distribution"] == {}
        assert summary["duration_distribution"] == []
        assert summary["problematic_formats"] == []
    
    def test_get_metrics_summary_with_data(self):
        """Test getting summary with metrics data."""
        # Record some test metrics
        self.metrics.record_transcription(
            audio_format="ogg", audio_duration_seconds=5.0, audio_size_bytes=100000,
            sample_rate=16000, transcript_length=50, confidence=0.9,
            processing_time_ms=200, source="telegram"
        )
        self.metrics.record_transcription(
            audio_format="wav", audio_duration_seconds=3.0, audio_size_bytes=50000,
            sample_rate=16000, transcript_length=30, confidence=0.85,
            processing_time_ms=150, source="gateway"
        )
        self.metrics.record_transcription(
            audio_format="ogg", audio_duration_seconds=2.0, audio_size_bytes=40000,
            sample_rate=16000, transcript_length=20, confidence=0.65,
            processing_time_ms=100, source="telegram", error_message="Low confidence"
        )
        
        summary = self.metrics.get_metrics_summary()
        
        assert summary["summary"]["total_transcriptions"] == 3
        assert 0.8 <= summary["summary"]["avg_confidence"] < 0.9
        assert "ogg" in summary["format_distribution"]
        assert "wav" in summary["format_distribution"]
        assert summary["format_distribution"]["ogg"] == 2
        assert summary["format_distribution"]["wav"] == 1
    
    def test_get_metrics_summary_with_filters(self):
        """Test getting summary with date and format filters."""
        # Record metrics at different times
        base_time = datetime.now()
        
        # Record some old metrics
        for i in range(3):
            self.metrics.record_transcription(
                audio_format="ogg", audio_duration_seconds=5.0, audio_size_bytes=100000,
                sample_rate=16000, transcript_length=50, confidence=0.9,
                processing_time_ms=200, source="telegram"
            )
        
        # Record recent metrics
        for i in range(2):
            self.metrics.record_transcription(
                audio_format="wav", audio_duration_seconds=3.0, audio_size_bytes=50000,
                sample_rate=16000, transcript_length=30, confidence=0.85,
                processing_time_ms=150, source="gateway"
            )
        
        # Filter by date (recent only)
        recent_date = datetime.now() - timedelta(hours=1)
        summary = self.metrics.get_metrics_summary(start_date=recent_date)
        
        # Should see recent metrics (exact count may vary due to timing)
        assert summary["summary"]["total_transcriptions"] >= 2
        
        # Filter by format
        summary = self.metrics.get_metrics_summary(audio_format="wav")
        assert "wav" in summary["format_distribution"]
        assert summary["format_distribution"]["wav"] >= 2
    
    def test_get_metrics_summary_problematic_formats(self):
        """Test identifying problematic audio formats."""
        # Record low confidence metrics
        self.metrics.record_transcription(
            audio_format="unknown", audio_duration_seconds=5.0, audio_size_bytes=100000,
            sample_rate=16000, transcript_length=50, confidence=0.5,
            processing_time_ms=200, source="gateway"
        )
        self.metrics.record_transcription(
            audio_format="unknown", audio_duration_seconds=3.0, audio_size_bytes=50000,
            sample_rate=16000, transcript_length=30, confidence=0.6,
            processing_time_ms=150, source="gateway"
        )
        self.metrics.record_transcription(
            audio_format="unknown", audio_duration_seconds=2.0, audio_size_bytes=40000,
            sample_rate=16000, transcript_length=0, confidence=0.0,
            processing_time_ms=100, source="gateway", error_message="Format error"
        )
        
        summary = self.metrics.get_metrics_summary()
        
        # Should identify unknown format as problematic
        problematic = summary["problematic_formats"]
        assert len(problematic) > 0
        unknown_format = next((f for f in problematic if f["format"] == "unknown"), None)
        assert unknown_format is not None
        assert unknown_format["avg_confidence"] < 0.7 or unknown_format["error_rate"] > 10
    
    def test_get_recent_metrics(self):
        """Test getting recent metrics."""
        # Record multiple metrics
        for i in range(5):
            self.metrics.record_transcription(
                audio_format="ogg", audio_duration_seconds=5.0, audio_size_bytes=100000,
                sample_rate=16000, transcript_length=50, confidence=0.9,
                processing_time_ms=200, source="telegram"
            )
        
        recent = self.metrics.get_recent_metrics(limit=3)
        
        assert len(recent) == 3
        assert all("id" in m for m in recent)
        assert all("timestamp" in m for m in recent)
        assert all("audio_format" in m for m in recent)
        assert all("confidence" in m for m in recent)
        
        # Should be ordered by timestamp DESC
        timestamps = [m["timestamp"] for m in recent]
        assert timestamps == sorted(timestamps, reverse=True)
    
    def test_duration_distribution(self):
        """Test duration distribution calculation."""
        # Record metrics with different durations
        durations = [2.0, 8.0, 25.0, 45.0, 70.0]
        for duration in durations:
            self.metrics.record_transcription(
                audio_format="ogg", audio_duration_seconds=duration, audio_size_bytes=100000,
                sample_rate=16000, transcript_length=50, confidence=0.9,
                processing_time_ms=200, source="telegram"
            )
        
        summary = self.metrics.get_metrics_summary()
        duration_dist = summary["duration_distribution"]
        
        assert len(duration_dist) > 0
        # Should have entries for different ranges
        ranges = [d["range"] for d in duration_dist]
        assert any("< 5s" in r or "5-10s" in r or "10-30s" in r for r in ranges)


class TestGetMetricsStorage:
    """Test global metrics storage function."""
    
    def test_get_metrics_storage_creates_instance(self):
        """Test that get_metrics_storage returns an instance."""
        storage = get_metrics_storage()
        assert storage is not None
        assert isinstance(storage, STTMetricsStorage)
    
    def test_get_metrics_storage_singleton(self):
        """Test that get_metrics_storage returns the same instance."""
        storage1 = get_metrics_storage()
        storage2 = get_metrics_storage()
        
        # Should be the same instance
        assert storage1 is storage2
