"""
STT Transcription Quality Metrics Storage.

Tracks transcription metrics including:
- Audio format and properties
- Transcription quality metrics
- Problematic audio formats/lengths
- Confidence scores
"""
import sqlite3
import logging
import json
from typing import Optional, Dict, List, Any
from datetime import datetime
from pathlib import Path
import os

logger = logging.getLogger(__name__)


class STTMetricsStorage:
    """Storage for STT transcription quality metrics."""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize metrics storage.
        
        Args:
            db_path: Path to SQLite database. Defaults to stt_metrics.db in service directory.
        """
        if db_path is None:
            # Default to stt_metrics.db in the STT service directory
            service_dir = Path(__file__).parent
            db_path = str(service_dir / "stt_metrics.db")
        
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize the metrics database schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcription_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    audio_format TEXT,
                    audio_duration_seconds REAL,
                    audio_size_bytes INTEGER,
                    sample_rate INTEGER,
                    transcript_length INTEGER,
                    confidence REAL,
                    processing_time_ms INTEGER,
                    source TEXT,
                    error_message TEXT,
                    metadata TEXT
                )
            """)
            
            # Indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON transcription_metrics(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audio_format 
                ON transcription_metrics(audio_format)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_confidence 
                ON transcription_metrics(confidence)
            """)
            
            conn.commit()
            logger.info(f"Metrics database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize metrics database: {e}")
            raise
        finally:
            conn.close()
    
    def record_transcription(
        self,
        audio_format: str,
        audio_duration_seconds: float,
        audio_size_bytes: int,
        sample_rate: int,
        transcript_length: int,
        confidence: float,
        processing_time_ms: int,
        source: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Record a transcription metric.
        
        Args:
            audio_format: Audio format (e.g., 'ogg', 'wav', 'pcm')
            audio_duration_seconds: Audio duration in seconds
            audio_size_bytes: Audio file size in bytes
            sample_rate: Audio sample rate in Hz
            transcript_length: Length of transcript in characters
            confidence: Transcription confidence (0.0-1.0)
            processing_time_ms: Processing time in milliseconds
            source: Source service (e.g., 'telegram', 'gateway')
            error_message: Error message if transcription failed
            metadata: Additional metadata dictionary
            
        Returns:
            ID of the recorded metric
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            metadata_json = json.dumps(metadata) if metadata else None
            
            cursor.execute("""
                INSERT INTO transcription_metrics (
                    audio_format, audio_duration_seconds, audio_size_bytes,
                    sample_rate, transcript_length, confidence, processing_time_ms,
                    source, error_message, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                audio_format,
                audio_duration_seconds,
                audio_size_bytes,
                sample_rate,
                transcript_length,
                confidence,
                processing_time_ms,
                source,
                error_message,
                metadata_json
            ))
            metric_id = cursor.lastrowid
            conn.commit()
            logger.debug(f"Recorded transcription metric {metric_id}")
            return metric_id
        except Exception as e:
            logger.error(f"Failed to record transcription metric: {e}")
            raise
        finally:
            conn.close()
    
    def get_metrics_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        audio_format: Optional[str] = None,
        source: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get summary statistics for transcription metrics.
        
        Args:
            start_date: Start date filter
            end_date: End date filter
            audio_format: Filter by audio format
            source: Filter by source service
            
        Returns:
            Dictionary with summary statistics
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            # Build WHERE clause
            conditions = []
            params = []
            
            if start_date:
                conditions.append("timestamp >= ?")
                params.append(start_date.isoformat())
            
            if end_date:
                conditions.append("timestamp <= ?")
                params.append(end_date.isoformat())
            
            if audio_format:
                conditions.append("audio_format = ?")
                params.append(audio_format)
            
            if source:
                conditions.append("source = ?")
                params.append(source)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Get overall statistics
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_transcriptions,
                    AVG(confidence) as avg_confidence,
                    MIN(confidence) as min_confidence,
                    MAX(confidence) as max_confidence,
                    AVG(audio_duration_seconds) as avg_duration,
                    AVG(processing_time_ms) as avg_processing_time_ms,
                    SUM(CASE WHEN error_message IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM transcription_metrics
                {where_clause}
            """, params)
            
            row = cursor.fetchone()
            total, avg_conf, min_conf, max_conf, avg_dur, avg_proc, error_count = row
            
            # Get format distribution
            cursor.execute(f"""
                SELECT audio_format, COUNT(*) as count
                FROM transcription_metrics
                {where_clause}
                GROUP BY audio_format
                ORDER BY count DESC
            """, params)
            
            format_distribution = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Get duration distribution
            cursor.execute(f"""
                SELECT 
                    CASE 
                        WHEN audio_duration_seconds < 5 THEN '< 5s'
                        WHEN audio_duration_seconds < 10 THEN '5-10s'
                        WHEN audio_duration_seconds < 30 THEN '10-30s'
                        WHEN audio_duration_seconds < 60 THEN '30-60s'
                        ELSE '> 60s'
                    END as duration_range,
                    COUNT(*) as count,
                    AVG(confidence) as avg_confidence
                FROM transcription_metrics
                {where_clause} AND error_message IS NULL
                GROUP BY duration_range
                ORDER BY count DESC
            """, params)
            
            duration_distribution = [
                {"range": row[0], "count": row[1], "avg_confidence": row[2]}
                for row in cursor.fetchall()
            ]
            
            # Get problematic formats (low confidence or high error rate)
            cursor.execute(f"""
                SELECT 
                    audio_format,
                    COUNT(*) as total,
                    AVG(confidence) as avg_confidence,
                    SUM(CASE WHEN error_message IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as error_rate
                FROM transcription_metrics
                {where_clause}
                GROUP BY audio_format
                HAVING avg_confidence < 0.7 OR error_rate > 10
                ORDER BY error_rate DESC, avg_confidence ASC
            """, params)
            
            problematic_formats = [
                {
                    "format": row[0],
                    "total": row[1],
                    "avg_confidence": row[2],
                    "error_rate": row[3]
                }
                for row in cursor.fetchall()
            ]
            
            return {
                "summary": {
                    "total_transcriptions": total or 0,
                    "avg_confidence": round(avg_conf or 0.0, 3),
                    "min_confidence": round(min_conf or 0.0, 3),
                    "max_confidence": round(max_conf or 0.0, 3),
                    "avg_duration_seconds": round(avg_dur or 0.0, 2),
                    "avg_processing_time_ms": round(avg_proc or 0.0, 2),
                    "error_count": error_count or 0,
                    "error_rate": round((error_count or 0) * 100.0 / (total or 1), 2)
                },
                "format_distribution": format_distribution,
                "duration_distribution": duration_distribution,
                "problematic_formats": problematic_formats,
                "filters": {
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "audio_format": audio_format,
                    "source": source
                }
            }
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            raise
        finally:
            conn.close()
    
    def get_recent_metrics(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent transcription metrics.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of metric records
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id, timestamp, audio_format, audio_duration_seconds,
                    audio_size_bytes, sample_rate, transcript_length, confidence,
                    processing_time_ms, source, error_message, metadata
                FROM transcription_metrics
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "timestamp": row[1],
                    "audio_format": row[2],
                    "audio_duration_seconds": row[3],
                    "audio_size_bytes": row[4],
                    "sample_rate": row[5],
                    "transcript_length": row[6],
                    "confidence": row[7],
                    "processing_time_ms": row[8],
                    "source": row[9],
                    "error_message": row[10],
                    "metadata": json.loads(row[11]) if row[11] else None
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get recent metrics: {e}")
            raise
        finally:
            conn.close()


# Global metrics storage instance
_metrics_storage: Optional[STTMetricsStorage] = None


def get_metrics_storage() -> STTMetricsStorage:
    """Get or create the global metrics storage instance."""
    global _metrics_storage
    if _metrics_storage is None:
        db_path = os.getenv("STT_METRICS_DB_PATH")
        _metrics_storage = STTMetricsStorage(db_path=db_path)
    return _metrics_storage
