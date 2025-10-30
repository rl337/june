"""
Gateway Service - Entry point for June Agent with auth, rate limiting, and streaming.
"""
import asyncio
import json
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import grpc
import nats
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from jose import JWTError, jwt
import httpx

from shared import config, setup_logging, Timer, RateLimiter, HealthChecker, CircularBuffer
from june_grpc_api import asr_pb2, asr_pb2_grpc, tts_pb2, tts_pb2_grpc, llm_pb2, llm_pb2_grpc

from june_grpc_api import asr_pb2, asr_pb2_grpc

# Setup logging
setup_logging(config.monitoring.log_level, "gateway")
logger = logging.getLogger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('gateway_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('gateway_request_duration_seconds', 'Request duration')
ACTIVE_CONNECTIONS = Gauge('gateway_active_connections', 'Active WebSocket connections')
RATE_LIMIT_HITS = Counter('gateway_rate_limit_hits_total', 'Rate limit hits')

# Security
security = HTTPBearer()

# Global state
active_connections: Dict[str, WebSocket] = {}
rate_limiter = RateLimiter(config.auth.rate_limit_per_minute)
health_checker = HealthChecker()
message_buffer = CircularBuffer(1000)

class GatewayService:
    """Main gateway service class."""
    
    def __init__(self):
        self.app = FastAPI(
            title="June Agent Gateway",
            description="Entry point for June Agent with auth, rate limiting, and streaming",
            version="0.2.0"
        )
        self.nats_client: Optional[nats.NATS] = None
        self.inference_stub = None
        self.stt_stub = None
        self.tts_stub = None
        self._setup_middleware()
        self._setup_routes()
    
    def _setup_middleware(self):
        """Setup middleware."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.middleware("http")
        async def metrics_middleware(request, call_next):
            """Prometheus metrics middleware."""
            start_time = datetime.now()
            response = await call_next(request)
            duration = (datetime.now() - start_time).total_seconds()
            
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).inc()
            REQUEST_DURATION.observe(duration)
            
            return response
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            is_healthy = await health_checker.check_all()
            status_code = 200 if all(is_healthy.values()) else 503
            return JSONResponse(
                status_code=status_code,
                content={
                    "status": "healthy" if status_code == 200 else "unhealthy",
                    "checks": is_healthy,
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        @self.app.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            return generate_latest()
        
        @self.app.get("/status")
        async def status():
            """Service status endpoint."""
            return {
                "service": "gateway",
                "version": "0.2.0",
                "active_connections": len(active_connections),
                "uptime": "N/A",  # TODO: Implement uptime tracking
                "timestamp": datetime.now().isoformat()
            }

        @self.app.post("/api/v1/audio/transcribe")
        async def transcribe_audio(audio: UploadFile = File(...)):
            data = await audio.read()
            stt_url = os.getenv("STT_URL", "grpc://stt:50052").replace("grpc://", "")
            async with grpc.aio.insecure_channel(stt_url) as channel:
                stub = asr_pb2_grpc.SpeechToTextStub(channel)
                cfg = asr_pb2.RecognitionConfig(language="en", interim_results=False)
                req = asr_pb2.RecognitionRequest(audio_data=data, sample_rate=16000, encoding="wav", config=cfg)
                resp = await stub.Recognize(req, timeout=30.0)
                transcript = resp.results[0].transcript if resp.results else ""
                return {"transcript": transcript}

        @self.app.post("/api/v1/llm/generate")
        async def llm_generate(payload: Dict[str, Any]):
            text = payload.get("prompt", "")
            llm_url = os.getenv("INFERENCE_API_URL", "grpc://inference-api:50051").replace("grpc://", "")
            async with grpc.aio.insecure_channel(llm_url) as channel:
                stub = llm_pb2_grpc.LLMServiceStub(channel)
                req = llm_pb2.GenerateRequest(prompt=text)
                resp = await stub.Generate(req, timeout=30.0)
                return {"text": resp.text}

        @self.app.post("/api/v1/tts/speak")
        async def tts_speak(payload: Dict[str, Any]):
            text = payload.get("text", "")
            tts_url = os.getenv("TTS_URL", "grpc://tts:50053").replace("grpc://", "")
            async with grpc.aio.insecure_channel(tts_url) as channel:
                stub = tts_pb2_grpc.TextToSpeechStub(channel)
                cfg = tts_pb2.SynthesisConfig(sample_rate=16000, speed=1.0, pitch=0.0)
                req = tts_pb2.SynthesisRequest(text=text, config=cfg, voice_id="default", language="en")
                resp = await stub.Synthesize(req, timeout=30.0)
                import base64
                b64 = base64.b64encode(resp.audio_data).decode("ascii")
                return {"audio_b64": b64, "sample_rate": 16000}
        
        @self.app.post("/auth/token")
        async def create_token(user_id: str = "default"):
            """Create JWT token for authentication."""
            if not rate_limiter.is_allowed():
                RATE_LIMIT_HITS.inc()
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded"
                )
            
            payload = {
                "user_id": user_id,
                "exp": datetime.utcnow() + timedelta(hours=config.auth.jwt_expiration_hours),
                "iat": datetime.utcnow(),
                "jti": str(uuid.uuid4())
            }
            
            token = jwt.encode(payload, config.auth.jwt_secret, algorithm=config.auth.jwt_algorithm)
            return {"access_token": token, "token_type": "bearer"}
        
        @self.app.websocket("/ws/{user_id}")
        async def websocket_endpoint(websocket: WebSocket, user_id: str):
            """WebSocket endpoint for real-time communication."""
            await websocket.accept()
            connection_id = str(uuid.uuid4())
            active_connections[connection_id] = websocket
            ACTIVE_CONNECTIONS.inc()
            
            logger.info(f"WebSocket connection established for user {user_id}: {connection_id}")
            
            try:
                while True:
                    # Receive message from client
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    
                    # Process message
                    response = await self._process_message(message, user_id, connection_id)
                    
                    # Send response back to client
                    await websocket.send_text(json.dumps(response))
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected: {connection_id}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                }))
            finally:
                if connection_id in active_connections:
                    del active_connections[connection_id]
                ACTIVE_CONNECTIONS.dec()
        
        @self.app.post("/chat")
        async def chat_endpoint(
            message: Dict[str, Any],
            credentials: HTTPAuthorizationCredentials = Depends(security)
        ):
            """REST API chat endpoint."""
            # Verify JWT token
            try:
                payload = jwt.decode(
                    credentials.credentials,
                    config.auth.jwt_secret,
                    algorithms=[config.auth.jwt_algorithm]
                )
                user_id = payload["user_id"]
            except JWTError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials"
                )
            
            # Rate limiting
            if not rate_limiter.is_allowed():
                RATE_LIMIT_HITS.inc()
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded"
                )
            
            # Process message
            response = await self._process_message(message, user_id, "rest")
            return response
    
    async def _process_message(self, message: Dict[str, Any], user_id: str, connection_id: str) -> Dict[str, Any]:
        """Process incoming message and route to appropriate service."""
        with Timer("message_processing"):
            message_type = message.get("type", "text")
            
            if message_type == "audio":
                # Route to STT service
                return await self._handle_audio_message(message, user_id)
            elif message_type == "text":
                # Route to inference API
                return await self._handle_text_message(message, user_id)
            elif message_type == "tts_request":
                # Route to TTS service
                return await self._handle_tts_request(message, user_id)
            else:
                return {
                    "type": "error",
                    "message": f"Unknown message type: {message_type}",
                    "timestamp": datetime.now().isoformat()
                }
    
    async def _handle_audio_message(self, message: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Handle audio message - route to STT service."""
        try:
            # TODO: Implement gRPC call to STT service
            # For now, return mock response
            return {
                "type": "transcription",
                "text": "Mock transcription from audio",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"STT processing error: {e}")
            return {
                "type": "error",
                "message": f"STT processing failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    async def _handle_text_message(self, message: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Handle text message - route to inference API."""
        try:
            # TODO: Implement gRPC call to inference API
            # For now, return mock response
            return {
                "type": "response",
                "text": f"Mock response to: {message.get('text', '')}",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Inference processing error: {e}")
            return {
                "type": "error",
                "message": f"Inference processing failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    async def _handle_tts_request(self, message: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Handle TTS request - route to TTS service."""
        try:
            # TODO: Implement gRPC call to TTS service
            # For now, return mock response
            return {
                "type": "audio_response",
                "audio_url": "mock_audio_url",
                "duration": 2.5,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"TTS processing error: {e}")
            return {
                "type": "error",
                "message": f"TTS processing failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    async def connect_services(self):
        """Connect to external services."""
        try:
            # Connect to NATS
            self.nats_client = await nats.connect(config.nats.url)
            logger.info("Connected to NATS")
            
            # TODO: Setup gRPC connections to other services
            # self.inference_stub = ...
            # self.stt_stub = ...
            # self.tts_stub = ...
            
            # Add health checks
            health_checker.add_check("nats", self._check_nats_health)
            health_checker.add_check("grpc_services", self._check_grpc_health)
            
        except Exception as e:
            logger.error(f"Failed to connect to services: {e}")
            raise
    
    async def _check_nats_health(self) -> bool:
        """Check NATS connection health."""
        return self.nats_client is not None and self.nats_client.is_connected
    
    async def _check_grpc_health(self) -> bool:
        """Check gRPC services health."""
        # TODO: Implement actual gRPC health checks
        return True
    
    async def disconnect_services(self):
        """Disconnect from external services."""
        if self.nats_client:
            await self.nats_client.close()
            logger.info("Disconnected from NATS")

# Global service instance
gateway_service = GatewayService()

# Startup and shutdown events
@gateway_service.app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Starting Gateway service...")
    await gateway_service.connect_services()
    logger.info("Gateway service started successfully")

@gateway_service.app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Shutting down Gateway service...")
    await gateway_service.disconnect_services()
    logger.info("Gateway service shut down")

# Export the FastAPI app
app = gateway_service.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
        port=int(os.getenv("GATEWAY_PORT", "8000")),
        reload=True,
        log_level=config.monitoring.log_level.lower()
    )


