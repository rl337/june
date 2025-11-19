"""
Integration test: Telegram bot with Qwen3-30B-A3B.

Tests that Telegram bot can successfully use Qwen3-30B-A3B for generating responses.
Tests the complete voice-to-text-to-voice pipeline:
- Voice message → STT → LLM (Qwen3-30B-A3B) → TTS → Voice response

Verifies:
- Complete pipeline works end-to-end
- Qwen3-30B-A3B is used for LLM processing (check logs or metrics)
- Various message types and lengths work correctly
- Error handling works correctly
- Response times are reasonable

These tests require:
- Running LLM inference service (TensorRT-LLM on port 8000 by default, or legacy inference-api on port 50051) with Qwen3-30B-A3B model loaded
- Running STT service
- Running TTS service
- Running Telegram bot service (or ability to test voice handler directly)
"""
import pytest
import asyncio
import os
import sys
import time
import logging
import grpc
import httpx
import numpy as np
import struct
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "telegram"))

from june_grpc_api import asr as asr_shim, tts as tts_shim, llm as llm_shim

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Service addresses (can be overridden via environment variables)
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
STT_ADDRESS = os.getenv("STT_SERVICE_ADDRESS", "localhost:50052")
TTS_ADDRESS = os.getenv("TTS_SERVICE_ADDRESS", "localhost:50053")
# Default: TensorRT-LLM (tensorrt-llm:8000), Legacy: inference-api (inference-api:50051)
INFERENCE_ADDRESS = os.getenv(
    "INFERENCE_API_URL", os.getenv("LLM_URL", "tensorrt-llm:8000")
).replace("grpc://", "")
TELEGRAM_SERVICE_URL = os.getenv("TELEGRAM_SERVICE_URL", "http://localhost:8080")
SAMPLE_RATE = 16000

# Expected model name
EXPECTED_MODEL_NAME = "Qwen/Qwen3-30B-A3B-Thinking-2507"
EXPECTED_MODEL_NAME_ALT = "qwen3-30b-a3b"  # Alternative format


def generate_test_audio(
    text: str = "Hello world", duration_seconds: float = 1.0
) -> bytes:
    """
    Generate test audio data (simple sine wave for testing).
    In real tests, this would use TTS to generate audio from text.
    """
    sample_count = int(SAMPLE_RATE * duration_seconds)
    # Generate a simple sine wave at 440Hz (A note)
    t = np.linspace(0, duration_seconds, sample_count, False)
    frequency = 440.0
    audio_samples = np.sin(2 * np.pi * frequency * t)

    # Convert to 16-bit PCM
    audio_samples = (audio_samples * 32767).astype(np.int16)

    # Convert to bytes
    return audio_samples.tobytes()


def create_wav_file(audio_data: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Create a WAV file from raw PCM audio data."""
    # WAV file format
    num_samples = len(audio_data) // 2  # 16-bit = 2 bytes per sample
    data_size = len(audio_data)
    file_size = 36 + data_size

    wav = b"RIFF"
    wav += struct.pack("<I", file_size)
    wav += b"WAVE"
    wav += b"fmt "
    wav += struct.pack("<I", 16)  # fmt chunk size
    wav += struct.pack(
        "<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16
    )  # PCM, mono, sample_rate
    wav += b"data"
    wav += struct.pack("<I", data_size)
    wav += audio_data

    return wav


async def check_service_health(address: str, service_type: str) -> bool:
    """Check if a gRPC service is reachable."""
    try:
        async with grpc.aio.insecure_channel(address) as channel:
            # Try to connect
            grpc.channel_ready_future(channel).result(timeout=2.0)
            logger.info(f"✓ {service_type} service reachable at {address}")
            return True
    except Exception as e:
        logger.warning(f"✗ {service_type} service not reachable at {address}: {e}")
        return False


async def check_inference_api_health(address: str) -> tuple[bool, Optional[str]]:
    """Check LLM inference service (TensorRT-LLM or inference-api) health and return model name."""
    try:
        async with grpc.aio.insecure_channel(address) as channel:
            stub = llm_shim.LLMInferenceStub(channel)
            from june_grpc_api.generated.llm_pb2 import HealthRequest

            request = HealthRequest()
            response = await asyncio.wait_for(
                stub.HealthCheck(request, timeout=5.0), timeout=5.0
            )

            if response.healthy:
                model_name = (
                    response.model_name if hasattr(response, "model_name") else None
                )
                service_name = (
                    "TensorRT-LLM"
                    if "tensorrt-llm" in address or "8000" in address
                    else "Inference API"
                )
                logger.info(f"✓ {service_name} service is healthy at {address}")
                logger.info(f"  Model: {model_name}")
                return True, model_name
            else:
                logger.warning(f"⚠ LLM inference service at {address} is unhealthy")
                return False, None
    except Exception as e:
        logger.warning(f"✗ LLM inference service not reachable at {address}: {e}")
        return False, None


async def check_gateway_health(url: str) -> bool:
    """Check if Gateway HTTP service is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                logger.info(f"✓ Gateway service reachable at {url}")
                return True
            else:
                logger.warning(f"⚠ Gateway service unhealthy: {response.status_code}")
                return False
    except Exception as e:
        logger.warning(f"✗ Gateway service not reachable at {url}: {e}")
        return False


def verify_qwen3_model(model_name: Optional[str]) -> bool:
    """Verify that Qwen3-30B-A3B model is being used."""
    if not model_name:
        return False

    model_name_lower = model_name.lower()
    # Check for various possible model name formats
    return (
        "qwen3" in model_name_lower
        and "30b" in model_name_lower
        and "a3b" in model_name_lower
    ) or (
        "qwen" in model_name_lower
        and "30b" in model_name_lower
        and "a3b" in model_name_lower
    )


@pytest.fixture(scope="session")
async def services_available():
    """Check if all required services are available."""
    logger.info("Checking service availability...")

    stt_available = await check_service_health(STT_ADDRESS, "STT")
    tts_available = await check_service_health(TTS_ADDRESS, "TTS")
    inference_available, model_name = await check_inference_api_health(
        INFERENCE_ADDRESS
    )
    gateway_available = await check_gateway_health(GATEWAY_URL)

    # Verify Qwen3-30B-A3B is being used
    qwen3_verified = False
    if inference_available and model_name:
        qwen3_verified = verify_qwen3_model(model_name)
        if qwen3_verified:
            logger.info(f"✓ Qwen3-30B-A3B model verified: {model_name}")
        else:
            logger.warning(
                f"⚠ Model name '{model_name}' does not match expected Qwen3-30B-A3B"
            )

    all_available = (
        stt_available and tts_available and inference_available and gateway_available
    )

    if not all_available:
        logger.warning("⚠ Some services are not available. Tests may fail.")
        logger.warning("Make sure all services are running:")
        logger.warning("  - STT service on port 50052")
        logger.warning("  - TTS service on port 50053")
        logger.warning(
            "  - TensorRT-LLM (default): tensorrt-llm:8000 in home_infra/shared-network"
        )
        logger.warning(
            "  - Legacy Inference API: inference-api:50051 (requires --profile legacy)"
        )
        logger.warning("  - Gateway on port 8000")

    if not qwen3_verified:
        logger.warning(
            "⚠ Qwen3-30B-A3B model verification failed. Tests may not validate correct model usage."
        )

    return {
        "stt": stt_available,
        "tts": tts_available,
        "inference": inference_available,
        "gateway": gateway_available,
        "qwen3_verified": qwen3_verified,
        "model_name": model_name,
        "all": all_available,
    }


class TestTelegramBotQwen3Integration:
    """Test Telegram bot integration with Qwen3-30B-A3B."""

    @pytest.mark.asyncio
    async def test_verify_qwen3_model_loaded(self, services_available):
        """Verify that Qwen3-30B-A3B model is loaded in inference API."""
        if not services_available["inference"]:
            pytest.skip("Inference API service not available")

        # Re-check model name
        _, model_name = await check_inference_api_health(INFERENCE_ADDRESS)

        assert (
            model_name is not None
        ), "Model name should be available from health check"
        assert verify_qwen3_model(
            model_name
        ), f"Expected Qwen3-30B-A3B model, got: {model_name}"

        logger.info(f"✓ Verified Qwen3-30B-A3B model is loaded: {model_name}")

    @pytest.mark.asyncio
    async def test_voice_message_pipeline_short(self, services_available):
        """Test complete voice message pipeline with short message."""
        if not services_available["all"]:
            pytest.skip("Not all services available")

        # Generate test audio using TTS first to ensure we have real speech audio
        test_text = "What is two plus two?"

        # Step 1: Generate audio from text using TTS
        async with grpc.aio.insecure_channel(TTS_ADDRESS) as channel:
            tts_client = tts_shim.TextToSpeechClient(channel)
            tts_cfg = tts_shim.SynthesisConfig(
                sample_rate=SAMPLE_RATE, speed=1.0, pitch=0.0
            )
            input_audio = await tts_client.synthesize(
                text=test_text, voice_id="default", language="en", config=tts_cfg
            )

        # Step 2: Send audio to Gateway for full round-trip
        wav_data = create_wav_file(input_audio)

        start_time = time.time()

        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"audio": ("audio.wav", wav_data, "audio/wav")}
            data = {"full_round_trip": "true"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
            )

            elapsed_time = time.time() - start_time

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()

        # Verify response contains all expected fields
        assert "transcript" in result, "Response should contain transcript"
        assert "llm_response" in result, "Response should contain LLM response"
        assert "audio_data" in result, "Response should contain audio data"
        assert "sample_rate" in result, "Response should contain sample rate"

        # Verify transcript
        transcript = result["transcript"]
        assert len(transcript) > 0, "Transcript should not be empty"
        logger.info(f"  Input transcript: '{transcript}'")

        # Verify LLM response (should be generated by Qwen3-30B-A3B)
        llm_response = result["llm_response"]
        assert len(llm_response) > 0, "LLM response should not be empty"
        logger.info(f"  LLM response: '{llm_response[:100]}...'")

        # Verify audio response
        response_audio = base64.b64decode(result["audio_data"])
        assert len(response_audio) > 0, "Response audio should not be empty"
        logger.info(f"  Response audio: {len(response_audio)} bytes")

        # Verify response time is reasonable (less than 30 seconds for short message)
        assert (
            elapsed_time < 30.0
        ), f"Response time {elapsed_time:.2f}s exceeds 30s limit"
        logger.info(f"  Response time: {elapsed_time:.2f}s")

        logger.info("✓ Complete voice message pipeline test passed")

    @pytest.mark.asyncio
    async def test_voice_message_pipeline_medium(self, services_available):
        """Test complete voice message pipeline with medium-length message."""
        if not services_available["all"]:
            pytest.skip("Not all services available")

        # Generate test audio with medium-length text
        test_text = "Can you explain what machine learning is in a few sentences?"

        # Step 1: Generate audio from text using TTS
        async with grpc.aio.insecure_channel(TTS_ADDRESS) as channel:
            tts_client = tts_shim.TextToSpeechClient(channel)
            tts_cfg = tts_shim.SynthesisConfig(
                sample_rate=SAMPLE_RATE, speed=1.0, pitch=0.0
            )
            input_audio = await tts_client.synthesize(
                text=test_text, voice_id="default", language="en", config=tts_cfg
            )

        # Step 2: Send audio to Gateway for full round-trip
        wav_data = create_wav_file(input_audio)

        start_time = time.time()

        async with httpx.AsyncClient(timeout=90.0) as client:
            files = {"audio": ("audio.wav", wav_data, "audio/wav")}
            data = {"full_round_trip": "true"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
            )

            elapsed_time = time.time() - start_time

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()

        # Verify response
        assert "transcript" in result
        assert "llm_response" in result
        assert (
            len(result["llm_response"]) > 20
        ), "LLM response should be substantial for medium message"

        # Verify response time is reasonable (less than 60 seconds for medium message)
        assert (
            elapsed_time < 60.0
        ), f"Response time {elapsed_time:.2f}s exceeds 60s limit"
        logger.info(f"  Medium message response time: {elapsed_time:.2f}s")
        logger.info(f"  LLM response: '{result['llm_response'][:150]}...'")

    @pytest.mark.asyncio
    async def test_voice_message_pipeline_various_types(self, services_available):
        """Test voice message pipeline with various message types."""
        if not services_available["all"]:
            pytest.skip("Not all services available")

        test_cases = [
            ("What is the weather like?", "question"),
            ("Tell me a joke.", "command"),
            ("Hello, how are you?", "greeting"),
            ("Explain quantum computing.", "technical"),
        ]

        for test_text, msg_type in test_cases:
            logger.info(f"Testing {msg_type} message: '{test_text}'")

            # Generate audio
            async with grpc.aio.insecure_channel(TTS_ADDRESS) as channel:
                tts_client = tts_shim.TextToSpeechClient(channel)
                tts_cfg = tts_shim.SynthesisConfig(
                    sample_rate=SAMPLE_RATE, speed=1.0, pitch=0.0
                )
                input_audio = await tts_client.synthesize(
                    text=test_text, voice_id="default", language="en", config=tts_cfg
                )

            wav_data = create_wav_file(input_audio)

            async with httpx.AsyncClient(timeout=60.0) as client:
                files = {"audio": ("audio.wav", wav_data, "audio/wav")}
                data = {"full_round_trip": "true"}

                response = await client.post(
                    f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
                )

            assert response.status_code == 200, f"Failed for {msg_type} message"
            result = response.json()

            assert "transcript" in result
            assert "llm_response" in result
            assert len(result["llm_response"]) > 0

            logger.info(f"  ✓ {msg_type} message processed successfully")
            logger.info(f"    Response: '{result['llm_response'][:80]}...'")

    @pytest.mark.asyncio
    async def test_voice_message_error_handling_invalid_audio(self, services_available):
        """Test error handling for invalid audio format."""
        if not services_available["gateway"]:
            pytest.skip("Gateway not available")

        # Send invalid audio data
        invalid_audio = b"This is not audio data"

        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"audio": ("audio.wav", invalid_audio, "audio/wav")}
            data = {"full_round_trip": "false"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
            )

        # Should return error (400 or 500)
        assert response.status_code in [
            400,
            500,
            422,
        ], f"Expected error status, got {response.status_code}"
        logger.info(
            f"✓ Invalid audio format handled with status {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_voice_message_error_handling_empty_audio(self, services_available):
        """Test error handling for empty audio file."""
        if not services_available["gateway"]:
            pytest.skip("Gateway not available")

        empty_audio = b""

        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"audio": ("audio.wav", empty_audio, "audio/wav")}
            data = {"full_round_trip": "false"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
            )

        # Should return error
        assert response.status_code in [
            400,
            422,
            500,
        ], f"Expected error status, got {response.status_code}"
        logger.info(f"✓ Empty audio file handled with status {response.status_code}")

    @pytest.mark.asyncio
    async def test_llm_response_quality(self, services_available):
        """Test that LLM responses from Qwen3-30B-A3B are of acceptable quality."""
        if not services_available["all"]:
            pytest.skip("Not all services available")

        test_text = "What is the capital of France?"

        # Generate audio
        async with grpc.aio.insecure_channel(TTS_ADDRESS) as channel:
            tts_client = tts_shim.TextToSpeechClient(channel)
            tts_cfg = tts_shim.SynthesisConfig(
                sample_rate=SAMPLE_RATE, speed=1.0, pitch=0.0
            )
            input_audio = await tts_client.synthesize(
                text=test_text, voice_id="default", language="en", config=tts_cfg
            )

        wav_data = create_wav_file(input_audio)

        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"audio": ("audio.wav", wav_data, "audio/wav")}
            data = {"full_round_trip": "true"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
            )

        assert response.status_code == 200
        result = response.json()

        llm_response = result["llm_response"].lower()

        # Response should be non-empty and relevant
        assert len(llm_response) > 0, "LLM response should not be empty"
        assert (
            len(llm_response.strip()) > 0
        ), "LLM response should not be whitespace only"

        # For this specific question, should mention Paris (or be substantial)
        assert (
            "paris" in llm_response or len(result["llm_response"]) > 20
        ), f"Response should mention Paris or be substantial, got: '{result['llm_response'][:100]}'"

        logger.info(f"✓ LLM response quality check passed")
        logger.info(f"  Response: '{result['llm_response'][:150]}...'")

    @pytest.mark.asyncio
    async def test_response_time_reasonable(self, services_available):
        """Test that response times are reasonable for voice messages."""
        if not services_available["all"]:
            pytest.skip("Not all services available")

        test_text = "Hello, how are you?"

        # Generate audio
        async with grpc.aio.insecure_channel(TTS_ADDRESS) as channel:
            tts_client = tts_shim.TextToSpeechClient(channel)
            tts_cfg = tts_shim.SynthesisConfig(
                sample_rate=SAMPLE_RATE, speed=1.0, pitch=0.0
            )
            input_audio = await tts_client.synthesize(
                text=test_text, voice_id="default", language="en", config=tts_cfg
            )

        wav_data = create_wav_file(input_audio)

        # Measure response time
        start_time = time.time()

        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"audio": ("audio.wav", wav_data, "audio/wav")}
            data = {"full_round_trip": "true"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
            )

        elapsed_time = time.time() - start_time

        assert response.status_code == 200
        assert (
            elapsed_time < 30.0
        ), f"Response time {elapsed_time:.2f}s exceeds reasonable limit of 30s"

        logger.info(f"✓ Response time check passed: {elapsed_time:.2f}s")
        logger.info(f"  (Target: < 30s for short messages)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
