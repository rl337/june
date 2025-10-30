"""
Comprehensive test suite for Gateway service.
"""
import pytest
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import WebSocket
import httpx

from main import app, gateway_service, active_connections, rate_limiter
from shared import config
from jose import jwt

# Test configuration
TEST_JWT_SECRET = "test-secret-key"
TEST_USER_ID = "test-user-123"

@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)

@pytest.fixture
def auth_token():
    """Create test JWT token."""
    payload = {
        "user_id": TEST_USER_ID,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4())
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

@pytest.fixture
def mock_nats():
    """Mock NATS client."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    return mock_nats

@pytest.fixture
def mock_grpc_stubs():
    """Mock gRPC stubs."""
    return {
        "inference": AsyncMock(),
        "stt": AsyncMock(),
        "tts": AsyncMock()
    }

class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_health_check_healthy(self, client):
        """Test health check when all services are healthy."""
        with patch.object(gateway_service, '_check_nats_health', return_value=True), \
             patch.object(gateway_service, '_check_grpc_health', return_value=True):
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "checks" in data
            assert "timestamp" in data
    
    def test_health_check_unhealthy(self, client):
        """Test health check when services are unhealthy."""
        with patch.object(gateway_service, '_check_nats_health', return_value=False), \
             patch.object(gateway_service, '_check_grpc_health', return_value=True):
            response = client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
    
    def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "gateway_requests_total" in response.text
    
    def test_status_endpoint(self, client):
        """Test status endpoint."""
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "gateway"
        assert data["version"] == "0.2.0"
        assert "active_connections" in data
        assert "timestamp" in data

class TestAuthentication:
    """Test authentication endpoints."""
    
    def test_create_token_success(self, client):
        """Test successful token creation."""
        with patch.object(rate_limiter, 'is_allowed', return_value=True):
            response = client.post("/auth/token", params={"user_id": TEST_USER_ID})
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
    
    def test_create_token_rate_limited(self, client):
        """Test token creation with rate limiting."""
        with patch.object(rate_limiter, 'is_allowed', return_value=False):
            response = client.post("/auth/token", params={"user_id": TEST_USER_ID})
            assert response.status_code == 429
    
    def test_invalid_token(self, client):
        """Test request with invalid token."""
        headers = {"Authorization": "Bearer invalid-token"}
        response = client.post("/chat", json={"text": "test"}, headers=headers)
        assert response.status_code == 401
    
    def test_valid_token(self, client, auth_token):
        """Test request with valid token."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        with patch.object(rate_limiter, 'is_allowed', return_value=True):
            response = client.post("/chat", json={"text": "test"}, headers=headers)
            assert response.status_code == 200

class TestWebSocketConnection:
    """Test WebSocket functionality."""
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """Test WebSocket connection establishment."""
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{TEST_USER_ID}") as websocket:
                # Connection should be established
                assert len(active_connections) == 1
    
    @pytest.mark.asyncio
    async def test_websocket_message_processing(self):
        """Test WebSocket message processing."""
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{TEST_USER_ID}") as websocket:
                # Send text message
                message = {"type": "text", "text": "Hello"}
                websocket.send_text(json.dumps(message))
                
                # Receive response
                response = websocket.receive_text()
                data = json.loads(response)
                assert data["type"] == "response"
                assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_websocket_audio_message(self):
        """Test WebSocket audio message processing."""
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{TEST_USER_ID}") as websocket:
                # Send audio message
                message = {"type": "audio", "audio_data": "base64_encoded_audio"}
                websocket.send_text(json.dumps(message))
                
                # Receive response
                response = websocket.receive_text()
                data = json.loads(response)
                assert data["type"] == "transcription"
                assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_websocket_tts_request(self):
        """Test WebSocket TTS request processing."""
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{TEST_USER_ID}") as websocket:
                # Send TTS request
                message = {"type": "tts_request", "text": "Hello world"}
                websocket.send_text(json.dumps(message))
                
                # Receive response
                response = websocket.receive_text()
                data = json.loads(response)
                assert data["type"] == "audio_response"
                assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_websocket_invalid_message_type(self):
        """Test WebSocket with invalid message type."""
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{TEST_USER_ID}") as websocket:
                # Send invalid message
                message = {"type": "invalid_type", "data": "test"}
                websocket.send_text(json.dumps(message))
                
                # Receive error response
                response = websocket.receive_text()
                data = json.loads(response)
                assert data["type"] == "error"
                assert "Unknown message type" in data["message"]
    
    @pytest.mark.asyncio
    async def test_websocket_disconnect(self):
        """Test WebSocket disconnection cleanup."""
        initial_connections = len(active_connections)
        
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{TEST_USER_ID}") as websocket:
                assert len(active_connections) == initial_connections + 1
        
        # After disconnect, connection should be removed
        assert len(active_connections) == initial_connections

class TestChatEndpoint:
    """Test REST API chat endpoint."""
    
    def test_chat_with_valid_token(self, client, auth_token):
        """Test chat endpoint with valid token."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        with patch.object(rate_limiter, 'is_allowed', return_value=True):
            response = client.post(
                "/chat",
                json={"type": "text", "text": "Hello"},
                headers=headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["type"] == "response"
    
    def test_chat_rate_limited(self, client, auth_token):
        """Test chat endpoint with rate limiting."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        with patch.object(rate_limiter, 'is_allowed', return_value=False):
            response = client.post(
                "/chat",
                json={"type": "text", "text": "Hello"},
                headers=headers
            )
            assert response.status_code == 429
    
    def test_chat_audio_message(self, client, auth_token):
        """Test chat endpoint with audio message."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        with patch.object(rate_limiter, 'is_allowed', return_value=True):
            response = client.post(
                "/chat",
                json={"type": "audio", "audio_data": "base64_audio"},
                headers=headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["type"] == "transcription"

class TestServiceIntegration:
    """Test service integration and connection management."""
    
    @pytest.mark.asyncio
    async def test_nats_connection(self, mock_nats):
        """Test NATS connection."""
        with patch('nats.connect', return_value=mock_nats):
            await gateway_service.connect_services()
            assert gateway_service.nats_client is not None
    
    @pytest.mark.asyncio
    async def test_nats_health_check(self, mock_nats):
        """Test NATS health check."""
        gateway_service.nats_client = mock_nats
        is_healthy = await gateway_service._check_nats_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_nats_disconnected_health_check(self):
        """Test NATS health check when disconnected."""
        gateway_service.nats_client = None
        is_healthy = await gateway_service._check_nats_health()
        assert is_healthy is False
    
    @pytest.mark.asyncio
    async def test_grpc_health_check(self):
        """Test gRPC services health check."""
        is_healthy = await gateway_service._check_grpc_health()
        assert is_healthy is True  # Mock implementation returns True

class TestErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_websocket_json_error(self):
        """Test WebSocket with invalid JSON."""
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{TEST_USER_ID}") as websocket:
                # Send invalid JSON
                websocket.send_text("invalid json")
                
                # Should receive error response
                response = websocket.receive_text()
                data = json.loads(response)
                assert data["type"] == "error"
    
    def test_missing_authorization_header(self, client):
        """Test request without authorization header."""
        response = client.post("/chat", json={"text": "test"})
        assert response.status_code == 403  # FastAPI returns 403 for missing auth
    
    def test_expired_token(self, client):
        """Test request with expired token."""
        # Create expired token
        payload = {
            "user_id": TEST_USER_ID,
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired
            "iat": datetime.utcnow() - timedelta(hours=2),
            "jti": str(uuid.uuid4())
        }
        expired_token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = client.post("/chat", json={"text": "test"}, headers=headers)
        assert response.status_code == 401

class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limiter_allows_request(self):
        """Test rate limiter allows request within limit."""
        # Reset rate limiter
        rate_limiter.requests.clear()
        assert rate_limiter.is_allowed() is True
    
    def test_rate_limiter_blocks_request(self):
        """Test rate limiter blocks request when limit exceeded."""
        # Fill up rate limiter
        for _ in range(config.auth.rate_limit_per_minute + 1):
            rate_limiter.is_allowed()
        
        # Next request should be blocked
        assert rate_limiter.is_allowed() is False
    
    def test_rate_limiter_wait_time(self):
        """Test rate limiter wait time calculation."""
        # Fill up rate limiter
        for _ in range(config.auth.rate_limit_per_minute):
            rate_limiter.is_allowed()
        
        wait_time = rate_limiter.wait_time()
        assert wait_time > 0

class TestMessageProcessing:
    """Test message processing logic."""
    
    @pytest.mark.asyncio
    async def test_text_message_processing(self):
        """Test text message processing."""
        message = {"type": "text", "text": "Hello world"}
        response = await gateway_service._process_message(message, TEST_USER_ID, "test-connection")
        
        assert response["type"] == "response"
        assert "timestamp" in response
    
    @pytest.mark.asyncio
    async def test_audio_message_processing(self):
        """Test audio message processing."""
        message = {"type": "audio", "audio_data": "base64_audio"}
        response = await gateway_service._process_message(message, TEST_USER_ID, "test-connection")
        
        assert response["type"] == "transcription"
        assert "timestamp" in response
    
    @pytest.mark.asyncio
    async def test_tts_request_processing(self):
        """Test TTS request processing."""
        message = {"type": "tts_request", "text": "Hello world"}
        response = await gateway_service._process_message(message, TEST_USER_ID, "test-connection")
        
        assert response["type"] == "audio_response"
        assert "timestamp" in response

# Integration tests
class TestGatewayIntegration:
    """Integration tests for Gateway service."""
    
    @pytest.mark.asyncio
    async def test_full_websocket_flow(self):
        """Test complete WebSocket flow."""
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{TEST_USER_ID}") as websocket:
                # Test multiple message types
                messages = [
                    {"type": "text", "text": "Hello"},
                    {"type": "audio", "audio_data": "base64_audio"},
                    {"type": "tts_request", "text": "Goodbye"}
                ]
                
                for message in messages:
                    websocket.send_text(json.dumps(message))
                    response = websocket.receive_text()
                    data = json.loads(response)
                    assert "timestamp" in data
                    assert data["type"] in ["response", "transcription", "audio_response"]
    
    def test_full_rest_api_flow(self, client, auth_token):
        """Test complete REST API flow."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Test different message types
        messages = [
            {"type": "text", "text": "Hello"},
            {"type": "audio", "audio_data": "base64_audio"},
            {"type": "tts_request", "text": "Goodbye"}
        ]
        
        with patch.object(rate_limiter, 'is_allowed', return_value=True):
            for message in messages:
                response = client.post("/chat", json=message, headers=headers)
                assert response.status_code == 200
                data = response.json()
                assert "timestamp" in data

if __name__ == "__main__":
    pytest.main([__file__, "-v"])





