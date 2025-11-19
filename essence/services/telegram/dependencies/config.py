"""Service configuration and dependency setup."""
import os
import sys
from pathlib import Path
from typing import Any

from inference_core import config


def get_service_config() -> Any:
    """
    Get Telegram service configuration.
    
    Returns:
        TelegramConfig instance from inference_core.config
    """
    return config.telegram


def get_stt_address() -> str:
    """
    Get STT service address.
    
    Returns:
        STT service address as a string (host:port format)
    """
    return os.getenv("STT_URL", "stt:50052").replace("grpc://", "")


def get_tts_address() -> str:
    """
    Get TTS service address.
    
    Returns:
        TTS service address as a string (host:port format)
    """
    return os.getenv("TTS_URL", "tts:50053").replace("grpc://", "")


def get_llm_address() -> str:
    """
    Get LLM service address.
    
    Returns:
        LLM service address as a string (host:port format)
        
    Note:
        Defaults to TensorRT-LLM service (tensorrt-llm:8000) for optimized GPU inference.
        Can be overridden via LLM_URL environment variable.
        Legacy inference-api service (inference-api:50051) can be used by setting LLM_URL.
    """
    return os.getenv("LLM_URL", "tensorrt-llm:8000").replace("grpc://", "")


def get_metrics_storage() -> Any:
    """
    Get metrics storage instance.
    
    Returns:
        STTMetricsStorage instance from stt.stt_metrics
    """
    # Add parent directory to path to import stt_metrics
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from stt.stt_metrics import get_metrics_storage
    return get_metrics_storage()
