"""
Test Mode Configuration
Defines different operational modes for June Agent services.
"""
import os
from enum import Enum
from typing import Optional

class ServiceMode(Enum):
    """Service operational modes."""
    MOCK = "mock"  # Full pass-through mode for connectivity testing
    REAL = "real"  # Real model implementation mode

class TestMode:
    """Test mode configuration."""
    
    # Mode selection
    MODE = os.getenv("JUNE_TEST_MODE", "mock")  # "mock" or "stt_tts_roundtrip"
    
    # Service mode overrides
    GATEWAY_MODE = os.getenv("GATEWAY_MODE", MODE)
    INFERENCE_MODE = os.getenv("INFERENCE_MODE", MODE)
    STT_MODE = os.getenv("STT_MODE", MODE)
    TTS_MODE = os.getenv("TTS_MODE", MODE)
    
    @classmethod
    def is_mock_mode(cls) -> bool:
        """Check if we're in full mock mode."""
        return cls.MODE == "mock"
    
    @classmethod
    def is_roundtrip_mode(cls) -> bool:
        """Check if we're in STT/TTS round-trip mode."""
        return cls.MODE == "stt_tts_roundtrip"
    
    @classmethod
    def get_service_mode(cls, service_name: str) -> ServiceMode:
        """Get the mode for a specific service."""
        mode_map = {
            "gateway": cls.GATEWAY_MODE,
            "inference": cls.INFERENCE_MODE,
            "stt": cls.STT_MODE,
            "tts": cls.TTS_MODE
        }
        
        service_mode = mode_map.get(service_name.lower(), cls.MODE)
        
        if service_mode == "real" or (cls.is_roundtrip_mode() and service_name.lower() in ["stt", "tts"]):
            return ServiceMode.REAL
        else:
            return ServiceMode.MOCK
    
    @classmethod
    def get_config_summary(cls) -> dict:
        """Get a summary of the current configuration."""
        return {
            "test_mode": cls.MODE,
            "gateway_mode": cls.get_service_mode("gateway").value,
            "inference_mode": cls.get_service_mode("inference").value,
            "stt_mode": cls.get_service_mode("stt").value,
            "tts_mode": cls.get_service_mode("tts").value
        }

# Predefined configurations
CONFIGURATIONS = {
    "mock": {
        "description": "Full mock mode - all services pass-through for connectivity testing",
        "JUNE_TEST_MODE": "mock",
        "GATEWAY_MODE": "mock",
        "INFERENCE_MODE": "mock",
        "STT_MODE": "mock",
        "TTS_MODE": "mock"
    },
    "stt_tts_roundtrip": {
        "description": "STT/TTS round-trip mode - real TTS and STT for audio validation",
        "JUNE_TEST_MODE": "stt_tts_roundtrip",
        "GATEWAY_MODE": "mock",
        "INFERENCE_MODE": "mock",
        "STT_MODE": "real",
        "TTS_MODE": "real"
    }
}

def get_configuration(config_name: str) -> Optional[dict]:
    """Get a predefined configuration."""
    return CONFIGURATIONS.get(config_name)




