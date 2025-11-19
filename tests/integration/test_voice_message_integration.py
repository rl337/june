"""
Integration tests for voice message flow with real services.

Tests the complete end-to-end voice message flow:
- Audio → STT → Transcript → LLM → TTS → Audio Response

Uses real services (STT, TTS, TensorRT-LLM or Inference API) - not mocks.
Tests error scenarios and concurrent requests.
"""
import pytest
import asyncio
import os
import grpc
import httpx
import numpy as np
import struct
import base64
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

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
SAMPLE_RATE = 16000


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
            logger.info(f"? {service_type} service reachable at {address}")
            return True
    except Exception as e:
        logger.warning(f"??  {service_type} service not reachable at {address}: {e}")
        return False


async def check_gateway_health(url: str) -> bool:
    """Check if Gateway HTTP service is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                logger.info(f"? Gateway service reachable at {url}")
                return True
            else:
                logger.warning(f"??  Gateway service unhealthy: {response.status_code}")
                return False
    except Exception as e:
        logger.warning(f"??  Gateway service not reachable at {url}: {e}")
        return False


@pytest.fixture(scope="session")
async def services_available():
    """Check if all required services are available."""
    logger.info("Checking service availability...")

    stt_available = await check_service_health(STT_ADDRESS, "STT")
    tts_available = await check_service_health(TTS_ADDRESS, "TTS")
    service_name = (
        "TensorRT-LLM"
        if "tensorrt-llm" in INFERENCE_ADDRESS or "8000" in INFERENCE_ADDRESS
        else "Inference API"
    )
    inference_available = await check_service_health(INFERENCE_ADDRESS, service_name)
    gateway_available = await check_gateway_health(GATEWAY_URL)

    all_available = (
        stt_available and tts_available and inference_available and gateway_available
    )

    if not all_available:
        logger.warning("??  Some services are not available. Tests may fail.")
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

    return {
        "stt": stt_available,
        "tts": tts_available,
        "inference": inference_available,
        "gateway": gateway_available,
        "all": all_available,
    }


class TestVoiceMessageFlow:
    """Test end-to-end voice message flow."""

    @pytest.mark.asyncio
    async def test_stt_service_transcription(self, services_available):
        """Test STT service can transcribe audio."""
        if not services_available["stt"]:
            pytest.skip("STT service not available")

        # Generate test audio
        audio_data = generate_test_audio("Hello world", duration_seconds=1.0)
        wav_data = create_wav_file(audio_data)

        # Send to STT service
        async with grpc.aio.insecure_channel(STT_ADDRESS) as channel:
            client = asr_shim.SpeechToTextClient(channel)
            cfg = asr_shim.RecognitionConfig(language="en", interim_results=False)
            result = await client.recognize(
                wav_data, sample_rate=SAMPLE_RATE, encoding="wav", config=cfg
            )

            assert result.transcript is not None
            assert len(result.transcript) > 0
            logger.info(f"STT transcribed: '{result.transcript}'")

    @pytest.mark.asyncio
    async def test_tts_service_synthesis(self, services_available):
        """Test TTS service can synthesize audio from text."""
        if not services_available["tts"]:
            pytest.skip("TTS service not available")

        text = "Hello, this is a test message."

        # Send to TTS service
        async with grpc.aio.insecure_channel(TTS_ADDRESS) as channel:
            client = tts_shim.TextToSpeechClient(channel)
            cfg = tts_shim.SynthesisConfig(
                sample_rate=SAMPLE_RATE, speed=1.0, pitch=0.0
            )
            audio = await client.synthesize(
                text=text, voice_id="default", language="en", config=cfg
            )

            assert len(audio) > 0
            logger.info(f"TTS generated {len(audio)} bytes of audio")

    @pytest.mark.asyncio
    async def test_inference_api_generation(self, services_available):
        """Test Inference API can generate text."""
        if not services_available["inference"]:
            pytest.skip("Inference API not available")

        prompt = "Say hello in one sentence."

        # Send to Inference API
        async with grpc.aio.insecure_channel(INFERENCE_ADDRESS) as channel:
            client = llm_shim.LLMClient(channel)
            response = await client.generate(prompt)

            assert response is not None
            assert len(response) > 0
            logger.info(f"Inference API generated: '{response[:100]}...'")

    @pytest.mark.asyncio
    async def test_gateway_audio_transcribe_simple(self, services_available):
        """Test Gateway audio transcribe endpoint (simple transcription only)."""
        if not services_available["gateway"] or not services_available["stt"]:
            pytest.skip("Gateway or STT service not available")

        # Generate test audio
        audio_data = generate_test_audio("Test message", duration_seconds=1.0)
        wav_data = create_wav_file(audio_data)

        # Send to Gateway
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"audio": ("audio.wav", wav_data, "audio/wav")}
            data = {"full_round_trip": "false"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
            )

            assert response.status_code == 200
            result = response.json()
            assert "transcript" in result
            logger.info(f"Gateway transcription: '{result['transcript']}'")

    @pytest.mark.asyncio
    async def test_gateway_audio_full_round_trip(self, services_available):
        """Test Gateway full round-trip: Audio ? STT ? LLM ? TTS ? Audio."""
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

        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"audio": ("audio.wav", wav_data, "audio/wav")}
            data = {"full_round_trip": "true"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
            )

            assert response.status_code == 200
            result = response.json()

            # Verify response contains all expected fields
            assert "transcript" in result
            assert "llm_response" in result
            assert "audio_data" in result
            assert "sample_rate" in result

            # Verify audio response is base64 encoded
            response_audio = base64.b64decode(result["audio_data"])
            assert len(response_audio) > 0

            logger.info(f"Full round-trip completed:")
            logger.info(f"  Input transcript: '{result['transcript']}'")
            logger.info(f"  LLM response: '{result['llm_response'][:100]}...'")
            logger.info(f"  Response audio: {len(response_audio)} bytes")


class TestErrorScenarios:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_audio_format(self, services_available):
        """Test Gateway handles invalid audio format gracefully."""
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
            assert response.status_code in [400, 500, 422]
            logger.info(
                f"Invalid audio format handled with status {response.status_code}"
            )

    @pytest.mark.asyncio
    async def test_empty_audio_file(self, services_available):
        """Test Gateway handles empty audio file gracefully."""
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
            assert response.status_code in [400, 422, 500]
            logger.info(f"Empty audio file handled with status {response.status_code}")

    @pytest.mark.asyncio
    async def test_missing_audio_file(self, services_available):
        """Test Gateway handles missing audio file gracefully."""
        if not services_available["gateway"]:
            pytest.skip("Gateway not available")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Send request without audio file
            data = {"full_round_trip": "false"}

            response = await client.post(
                f"{GATEWAY_URL}/api/v1/audio/transcribe", data=data
            )

            # Should return error (422 or 400)
            assert response.status_code in [400, 422]
            logger.info(
                f"Missing audio file handled with status {response.status_code}"
            )

    @pytest.mark.asyncio
    async def test_service_unavailable_handling(self, services_available):
        """Test that services handle connection failures gracefully."""
        if not services_available["stt"]:
            pytest.skip("STT service not available for test")

        # Try to connect to non-existent service
        invalid_address = "localhost:99999"

        try:
            async with grpc.aio.insecure_channel(invalid_address) as channel:
                client = asr_shim.SpeechToTextClient(channel)
                cfg = asr_shim.RecognitionConfig(language="en", interim_results=False)

                # This should fail
                with pytest.raises(Exception):
                    await asyncio.wait_for(
                        client.recognize(
                            b"test", sample_rate=16000, encoding="wav", config=cfg
                        ),
                        timeout=5.0,
                    )
        except Exception as e:
            # Expected to fail
            logger.info(f"Service unavailable handling works: {type(e).__name__}")


class TestConcurrentRequests:
    """Test concurrent request handling."""

    @pytest.mark.asyncio
    async def test_concurrent_stt_requests(self, services_available):
        """Test multiple concurrent STT requests."""
        if not services_available["stt"]:
            pytest.skip("STT service not available")

        num_requests = 5
        audio_data = generate_test_audio("Concurrent test", duration_seconds=0.5)
        wav_data = create_wav_file(audio_data)

        async def send_stt_request(request_id: int):
            try:
                async with grpc.aio.insecure_channel(STT_ADDRESS) as channel:
                    client = asr_shim.SpeechToTextClient(channel)
                    cfg = asr_shim.RecognitionConfig(
                        language="en", interim_results=False
                    )
                    result = await client.recognize(
                        wav_data, sample_rate=SAMPLE_RATE, encoding="wav", config=cfg
                    )
                    return request_id, result.transcript
            except Exception as e:
                return request_id, f"Error: {str(e)}"

        # Send concurrent requests
        tasks = [send_stt_request(i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks)

        # Verify all requests completed
        assert len(results) == num_requests
        successful = sum(
            1 for _, transcript in results if not transcript.startswith("Error")
        )
        logger.info(f"Concurrent STT requests: {successful}/{num_requests} successful")
        assert successful > 0  # At least some should succeed

    @pytest.mark.asyncio
    async def test_concurrent_gateway_requests(self, services_available):
        """Test multiple concurrent Gateway requests."""
        if not services_available["gateway"] or not services_available["stt"]:
            pytest.skip("Gateway or STT service not available")

        num_requests = 5
        audio_data = generate_test_audio(
            "Gateway concurrent test", duration_seconds=0.5
        )
        wav_data = create_wav_file(audio_data)

        async def send_gateway_request(request_id: int):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    files = {"audio": ("audio.wav", wav_data, "audio/wav")}
                    data = {"full_round_trip": "false"}

                    response = await client.post(
                        f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
                    )
                    return request_id, response.status_code
            except Exception as e:
                return request_id, f"Error: {str(e)}"

        # Send concurrent requests
        tasks = [send_gateway_request(i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks)

        # Verify all requests completed
        assert len(results) == num_requests
        successful = sum(1 for _, status in results if status == 200)
        logger.info(
            f"Concurrent Gateway requests: {successful}/{num_requests} successful"
        )
        assert successful > 0  # At least some should succeed

    @pytest.mark.asyncio
    async def test_concurrent_full_round_trip_requests(self, services_available):
        """Test multiple concurrent full round-trip requests."""
        if not services_available["all"]:
            pytest.skip("Not all services available")

        num_requests = 3  # Fewer for full round-trip due to complexity
        test_text = "Hello"

        # Generate audio for each request
        async def send_round_trip_request(request_id: int):
            try:
                # Generate input audio
                async with grpc.aio.insecure_channel(TTS_ADDRESS) as channel:
                    tts_client = tts_shim.TextToSpeechClient(channel)
                    tts_cfg = tts_shim.SynthesisConfig(
                        sample_rate=SAMPLE_RATE, speed=1.0, pitch=0.0
                    )
                    input_audio = await tts_client.synthesize(
                        text=f"{test_text} request {request_id}",
                        voice_id="default",
                        language="en",
                        config=tts_cfg,
                    )

                wav_data = create_wav_file(input_audio)

                # Send to Gateway
                async with httpx.AsyncClient(timeout=60.0) as client:
                    files = {"audio": ("audio.wav", wav_data, "audio/wav")}
                    data = {"full_round_trip": "true"}

                    response = await client.post(
                        f"{GATEWAY_URL}/api/v1/audio/transcribe", files=files, data=data
                    )

                    if response.status_code == 200:
                        result = response.json()
                        return request_id, result.get("llm_response", "")
                    else:
                        return request_id, f"Status {response.status_code}"
            except Exception as e:
                return request_id, f"Error: {str(e)}"

        # Send concurrent requests
        tasks = [send_round_trip_request(i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks)

        # Verify all requests completed
        assert len(results) == num_requests
        successful = sum(
            1
            for _, result in results
            if not result.startswith("Error") and not result.startswith("Status")
        )
        logger.info(
            f"Concurrent full round-trip requests: {successful}/{num_requests} successful"
        )
        assert successful > 0  # At least some should succeed


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
