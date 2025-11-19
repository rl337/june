"""
Comprehensive integration test suite for June Agent system.
"""
import asyncio
import json

# Import service modules
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from grpc import aio

sys.path.append("services/gateway")
sys.path.append("services/inference-api")
sys.path.append("services/stt")
sys.path.append("services/tts")

from gateway.main import app as gateway_app
from inference_api.main import InferenceAPIService
from stt.main import STTService
from tts.main import TTSService

# Import protobuf classes
sys.path.append("proto")
from asr_pb2 import AudioChunk, RecognitionConfig, RecognitionRequest
from llm_pb2 import Context, GenerationParameters, GenerationRequest
from tts_pb2 import SynthesisConfig, SynthesisRequest


@pytest.fixture
def gateway_client():
    """Create test client for gateway service."""
    return TestClient(gateway_app)


@pytest.fixture
def mock_inference_service():
    """Mock inference API service."""
    service = InferenceAPIService()
    service.model = MagicMock()
    service.tokenizer = MagicMock()
    service.db_engine = AsyncMock()
    service.minio_client = MagicMock()
    service.nats_client = AsyncMock()
    return service


@pytest.fixture
def mock_stt_service():
    """Mock STT service."""
    service = STTService()
    service.whisper_model = MagicMock()
    service.vad = MagicMock()
    service.nats_client = AsyncMock()
    return service


@pytest.fixture
def mock_tts_service():
    """Mock TTS service."""
    service = TTSService()
    service.tts_model = MagicMock()
    service.nats_client = AsyncMock()
    return service


class TestGatewayIntegration:
    """Test Gateway service integration."""

    def test_gateway_health_check(self, gateway_client):
        """Test gateway health check endpoint."""
        with patch(
            "gateway.main.gateway_service._check_nats_health", return_value=True
        ), patch("gateway.main.gateway_service._check_grpc_health", return_value=True):
            response = gateway_client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    def test_gateway_status(self, gateway_client):
        """Test gateway status endpoint."""
        response = gateway_client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "gateway"
        assert data["version"] == "0.2.0"

    def test_gateway_metrics(self, gateway_client):
        """Test gateway metrics endpoint."""
        response = gateway_client.get("/metrics")
        assert response.status_code == 200
        assert "gateway_requests_total" in response.text

    def test_gateway_auth_token_creation(self, gateway_client):
        """Test JWT token creation."""
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            response = gateway_client.post(
                "/auth/token", params={"user_id": "test_user"}
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_gateway_chat_endpoint(self, gateway_client):
        """Test gateway chat endpoint."""
        # Create token first
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            token_response = gateway_client.post(
                "/auth/token", params={"user_id": "test_user"}
            )
            token = token_response.json()["access_token"]

        # Test chat endpoint
        headers = {"Authorization": f"Bearer {token}"}
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            response = gateway_client.post(
                "/chat", json={"type": "text", "text": "Hello"}, headers=headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["type"] == "response"


class TestInferenceAPIIntegration:
    """Test Inference API service integration."""

    @pytest.mark.asyncio
    async def test_inference_generation(self, mock_inference_service):
        """Test inference API text generation."""
        request = GenerationRequest(
            prompt="Write a short story about a robot.",
            params=GenerationParameters(max_tokens=100, temperature=0.8, top_p=0.9),
            context=Context(
                user_id="test_user", session_id="test_session", enable_tools=True
            ),
        )

        # Mock model generation
        mock_output = MagicMock()
        mock_output.sequences = MagicMock()
        mock_output.sequences.shape = [1, 10]
        mock_inference_service.model.generate.return_value = mock_output
        mock_inference_service.tokenizer.decode.return_value = "Write a short story about a robot. Once upon a time, there was a robot named Robo."

        response = await mock_inference_service.Generate(request, None)

        assert response.text == "Once upon a time, there was a robot named Robo."
        assert response.tokens_generated > 0
        assert response.finish_reason == 0  # STOP

    @pytest.mark.asyncio
    async def test_inference_chat(self, mock_inference_service):
        """Test inference API chat functionality."""
        from llm_pb2 import ChatMessage, ChatRequest

        messages = [
            ChatMessage(role="user", content="What is 2+2?"),
            ChatMessage(role="assistant", content="2+2 equals 4."),
            ChatMessage(role="user", content="What about 3+3?"),
        ]

        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session"),
        )

        # Mock model generation
        mock_output = MagicMock()
        mock_output.sequences = MagicMock()
        mock_output.sequences.shape = [1, 8]
        mock_inference_service.model.generate.return_value = mock_output
        mock_inference_service.tokenizer.decode.return_value = "Human: What is 2+2?\n\nAssistant: 2+2 equals 4.\n\nHuman: What about 3+3?\n\nAssistant: 3+3 equals 6."

        response = await mock_inference_service.Chat(request, None)

        assert response.message.role == "assistant"
        assert response.message.content == "3+3 equals 6."
        assert response.tokens_generated > 0

    @pytest.mark.asyncio
    async def test_inference_embeddings(self, mock_inference_service):
        """Test inference API embedding generation."""
        from llm_pb2 import EmbeddingRequest

        request = EmbeddingRequest(
            texts=["Hello world", "Test text"], model="test-model"
        )

        # Mock embedding generation
        mock_embeddings = MagicMock()
        mock_embeddings.cpu.return_value.numpy.return_value = np.random.rand(2, 384)
        mock_inference_service.embedding_model.return_value = MagicMock(
            last_hidden_state=mock_embeddings
        )

        response = await mock_inference_service.Embed(request, None)

        assert len(response.embeddings) == 2 * 384
        assert response.dimension == 384


class TestSTTIntegration:
    """Test STT service integration."""

    @pytest.mark.asyncio
    async def test_stt_recognition(self, mock_stt_service):
        """Test STT recognition functionality."""
        # Generate test audio data
        audio_data = np.random.randint(-32768, 32767, 16000, dtype=np.int16).tobytes()

        request = RecognitionRequest(
            audio_data=audio_data,
            sample_rate=16000,
            encoding="pcm",
            config=RecognitionConfig(
                language="en",
                interim_results=False,
                enable_vad=True,
                enable_diarization=False,
                enable_timestamps=True,
            ),
        )

        # Mock Whisper transcription
        mock_stt_service.whisper_model.transcribe.return_value = {
            "text": "Hello world",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "words": [
                        {
                            "word": "Hello",
                            "start": 0.0,
                            "end": 0.5,
                            "probability": 0.95,
                        },
                        {
                            "word": "world",
                            "start": 0.5,
                            "end": 1.0,
                            "probability": 0.90,
                        },
                    ],
                }
            ],
        }

        response = await mock_stt_service.Recognize(request, None)

        assert len(response.results) == 1
        assert response.results[0].transcript == "Hello world"
        assert response.results[0].is_final is True
        assert len(response.results[0].words) == 2

    @pytest.mark.asyncio
    async def test_stt_streaming(self, mock_stt_service):
        """Test STT streaming recognition."""
        # Create audio chunks
        chunk_size = 1600  # 100ms at 16kHz
        audio_data = np.random.randint(-32768, 32767, chunk_size * 4, dtype=np.int16)

        chunks = []
        for i in range(4):
            chunk = AudioChunk(
                audio_data=audio_data[i * chunk_size : (i + 1) * chunk_size].tobytes(),
                sample_rate=16000,
                channels=1,
                encoding="pcm",
                timestamp_us=i * 100000,  # 100ms apart
            )
            chunks.append(chunk)

        async def chunk_generator():
            for chunk in chunks:
                yield chunk

        # Mock Whisper transcription
        mock_stt_service.whisper_model.transcribe.return_value = {
            "text": "Hello world",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "words": [
                        {
                            "word": "Hello",
                            "start": 0.0,
                            "end": 0.5,
                            "probability": 0.95,
                        },
                        {
                            "word": "world",
                            "start": 0.5,
                            "end": 1.0,
                            "probability": 0.90,
                        },
                    ],
                }
            ],
        }

        results = []
        async for result in mock_stt_service.RecognizeStream(chunk_generator(), None):
            results.append(result)

        assert len(results) > 0
        assert results[-1].is_final is True
        assert results[-1].transcript == "Hello world"


class TestTTSIntegration:
    """Test TTS service integration."""

    @pytest.mark.asyncio
    async def test_tts_synthesis(self, mock_tts_service):
        """Test TTS synthesis functionality."""
        request = SynthesisRequest(
            text="Hello world",
            voice_id="default",
            language="en",
            config=SynthesisConfig(speed=1.0, pitch=0.0, energy=1.0, prosody="neutral"),
            stream=False,
        )

        # Mock TTS generation
        mock_tts_service.tts_model.tts.return_value = np.array(
            [0.1, 0.2, 0.3, 0.4, 0.5]
        )

        response = await mock_tts_service.Synthesize(request, None)

        assert len(response.audio_data) > 0
        assert response.sample_rate == mock_tts_service.sample_rate
        assert response.encoding == "pcm16"
        assert response.duration_ms > 0

    @pytest.mark.asyncio
    async def test_tts_streaming(self, mock_tts_service):
        """Test TTS streaming synthesis."""
        requests = [
            SynthesisRequest(
                text="Hello",
                voice_id="default",
                language="en",
                config=SynthesisConfig(),
                stream=True,
            ),
            SynthesisRequest(
                text="world",
                voice_id="default",
                language="en",
                config=SynthesisConfig(),
                stream=True,
            ),
        ]

        async def request_generator():
            for request in requests:
                yield request

        # Mock TTS generation
        mock_tts_service.tts_model.tts.return_value = np.array(
            [0.1, 0.2, 0.3, 0.4, 0.5]
        )

        chunks = []
        async for chunk in mock_tts_service.SynthesizeStream(request_generator(), None):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        assert chunks[-1].sample_rate == mock_tts_service.sample_rate


class TestEndToEndIntegration:
    """Test end-to-end system integration."""

    @pytest.mark.asyncio
    async def test_voice_to_text_to_voice_flow(
        self, gateway_client, mock_stt_service, mock_tts_service
    ):
        """Test complete voice-to-text-to-voice flow."""
        # Step 1: Create authentication token
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            token_response = gateway_client.post(
                "/auth/token", params={"user_id": "test_user"}
            )
            token = token_response.json()["access_token"]

        # Step 2: Send audio message (simulated)
        headers = {"Authorization": f"Bearer {token}"}
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            audio_response = gateway_client.post(
                "/chat",
                json={"type": "audio", "audio_data": "base64_encoded_audio"},
                headers=headers,
            )
            assert audio_response.status_code == 200
            data = audio_response.json()
            assert data["type"] == "transcription"

        # Step 3: Send text message
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            text_response = gateway_client.post(
                "/chat",
                json={"type": "text", "text": "Hello, how are you?"},
                headers=headers,
            )
            assert text_response.status_code == 200
            data = text_response.json()
            assert data["type"] == "response"

        # Step 4: Request TTS
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            tts_response = gateway_client.post(
                "/chat",
                json={"type": "tts_request", "text": "I'm doing well, thank you!"},
                headers=headers,
            )
            assert tts_response.status_code == 200
            data = tts_response.json()
            assert data["type"] == "audio_response"

    @pytest.mark.asyncio
    async def test_websocket_conversation_flow(self, gateway_client):
        """Test WebSocket conversation flow."""
        with gateway_client.websocket_connect("/ws/test_user") as websocket:
            # Send text message
            websocket.send_text(
                json.dumps({"type": "text", "text": "Hello, I'm June!"})
            )

            response = websocket.receive_text()
            data = json.loads(response)
            assert data["type"] == "response"
            assert "timestamp" in data

            # Send audio message
            websocket.send_text(
                json.dumps({"type": "audio", "audio_data": "base64_encoded_audio"})
            )

            response = websocket.receive_text()
            data = json.loads(response)
            assert data["type"] == "transcription"
            assert "timestamp" in data

            # Send TTS request
            websocket.send_text(
                json.dumps({"type": "tts_request", "text": "Nice to meet you!"})
            )

            response = websocket.receive_text()
            data = json.loads(response)
            assert data["type"] == "audio_response"
            assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_error_handling_flow(self, gateway_client):
        """Test error handling in the system."""
        # Test invalid message type
        with gateway_client.websocket_connect("/ws/test_user") as websocket:
            websocket.send_text(json.dumps({"type": "invalid_type", "data": "test"}))

            response = websocket.receive_text()
            data = json.loads(response)
            assert data["type"] == "error"
            assert "Unknown message type" in data["message"]

        # Test invalid JSON
        with gateway_client.websocket_connect("/ws/test_user") as websocket:
            websocket.send_text("invalid json")

            response = websocket.receive_text()
            data = json.loads(response)
            assert data["type"] == "error"


class TestPerformanceIntegration:
    """Test performance and scalability integration."""

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, gateway_client):
        """Test handling of concurrent requests."""
        # Create multiple tokens
        tokens = []
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            for i in range(5):
                response = gateway_client.post(
                    "/auth/token", params={"user_id": f"user_{i}"}
                )
                tokens.append(response.json()["access_token"])

        # Send concurrent requests
        async def send_request(token, user_id):
            headers = {"Authorization": f"Bearer {token}"}
            with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
                response = gateway_client.post(
                    "/chat",
                    json={"type": "text", "text": f"Hello from {user_id}"},
                    headers=headers,
                )
                return response.status_code == 200

        # Execute concurrent requests
        tasks = [send_request(token, f"user_{i}") for i, token in enumerate(tokens)]
        results = await asyncio.gather(*tasks)

        assert all(results)

    @pytest.mark.asyncio
    async def test_rate_limiting(self, gateway_client):
        """Test rate limiting functionality."""
        # Create token
        with patch("gateway.main.rate_limiter.is_allowed", return_value=True):
            token_response = gateway_client.post(
                "/auth/token", params={"user_id": "test_user"}
            )
            token = token_response.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}

        # Send requests until rate limited
        with patch("gateway.main.rate_limiter.is_allowed", return_value=False):
            response = gateway_client.post(
                "/chat", json={"type": "text", "text": "Hello"}, headers=headers
            )
            assert response.status_code == 429


class TestMonitoringIntegration:
    """Test monitoring and observability integration."""

    def test_metrics_collection(self, gateway_client):
        """Test metrics collection across services."""
        # Make requests to generate metrics
        gateway_client.get("/health")
        gateway_client.get("/status")

        # Check metrics endpoint
        response = gateway_client.get("/metrics")
        assert response.status_code == 200

        # Verify specific metrics are present
        metrics_text = response.text
        assert "gateway_requests_total" in metrics_text
        assert "gateway_request_duration_seconds" in metrics_text

    def test_health_check_cascade(self, gateway_client):
        """Test health check cascade through services."""
        # Test individual service health
        with patch(
            "gateway.main.gateway_service._check_nats_health", return_value=True
        ), patch("gateway.main.gateway_service._check_grpc_health", return_value=True):
            response = gateway_client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "checks" in data

        # Test unhealthy services
        with patch(
            "gateway.main.gateway_service._check_nats_health", return_value=False
        ), patch("gateway.main.gateway_service._check_grpc_health", return_value=True):
            response = gateway_client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"


class TestConfigurationIntegration:
    """Test configuration and environment integration."""

    def test_environment_variables(self):
        """Test environment variable handling."""
        import os

        from inference_core.config import config

        # Test that configuration loads properly
        assert config.model.name is not None
        assert config.stt.model_name is not None
        assert config.tts.model_name is not None
        assert config.database.url is not None
        assert config.nats.url is not None

    def test_service_discovery(self):
        """Test service discovery and connection."""
        # This would test actual service connections in a real deployment
        # For now, we'll test the configuration
        from inference_core.config import config

        assert config.inference_api_url is not None
        assert config.stt_url is not None
        assert config.tts_url is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
