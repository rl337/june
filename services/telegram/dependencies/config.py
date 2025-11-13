"""Service configuration and dependency setup."""
import os
import sys
from pathlib import Path

from inference_core import config


def get_service_config():
    """Get Telegram service configuration."""
    return config.telegram


def get_stt_address():
    """Get STT service address."""
    return os.getenv("STT_URL", "stt:50052").replace("grpc://", "")


def get_tts_address():
    """Get TTS service address."""
    return os.getenv("TTS_URL", "tts:50053").replace("grpc://", "")


def get_llm_address():
    """Get LLM service address."""
    return os.getenv("LLM_URL", "inference-api:50051").replace("grpc://", "")


def get_metrics_storage():
    """Get metrics storage instance."""
    # Add parent directory to path to import stt_metrics
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from stt.stt_metrics import get_metrics_storage
    return get_metrics_storage()
