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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status, UploadFile, File, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
import grpc
import nats
from jose import JWTError, jwt
import httpx

# Import new authentication module
sys.path.insert(0, str(Path(__file__).parent))
from auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    revoke_refresh_token,
    check_permission,
    check_role,
    AuthenticationError,
    AuthorizationError
)
from auth_dependencies import (
    get_current_user,
    require_admin,
    require_permission,
    require_any_permission
)

from inference_core import config, setup_logging, Timer, HealthChecker, CircularBuffer
from june_grpc_api import asr as asr_shim, tts as tts_shim, llm as llm_shim
import sys
from pathlib import Path
# Add services directory to path to import stt_metrics
sys.path.insert(0, str(Path(__file__).parent.parent))
from stt.stt_metrics import get_metrics_storage

# Setup logging first
setup_logging(config.monitoring.log_level, "gateway")
logger = logging.getLogger(__name__)

# Import caching
try:
    from june_cache import CacheManager, CacheConfig, CacheType, CacheMetrics
    CACHE_AVAILABLE = True
except ImportError:
    logger.warning("june-cache package not available, caching disabled")
    CACHE_AVAILABLE = False
    CacheManager = None
    CacheConfig = None
    CacheType = None
    CacheMetrics = None

# Import rate limiting
try:
    from june_rate_limit import RateLimitMiddleware, RateLimitConfig, RateLimiter
    RATE_LIMIT_AVAILABLE = True
except ImportError:
    logger.warning("june-rate-limit package not available, using basic rate limiting")
    RATE_LIMIT_AVAILABLE = False
    RateLimitMiddleware = None
    RateLimitConfig = None
    RateLimiter = None
# Import user management
sys.path.insert(0, str(Path(__file__).parent))
from user_management import (
    get_users, get_user, create_user, update_user_status, 
    delete_user, get_user_statistics
)
from conversation_management import (
    get_conversations, get_conversation, search_conversations,
    delete_conversation, get_conversation_statistics
)
from bot_management import (
    get_bot_config, update_bot_config, get_bot_status,
    get_bot_statistics, get_bot_commands, create_bot_command,
    update_bot_command, delete_bot_command
)
from system_monitoring import (
    get_all_services_health, get_all_metrics, get_recent_errors,
    get_service_uptime, get_service_metrics
)
from analytics_management import (
    get_user_analytics, get_conversation_analytics,
    get_bot_performance_analytics, get_system_usage_analytics
)
from system_config import (
    get_system_config, update_system_config, get_config_history, validate_config
)
from input_validation import (
    LLMGenerateRequest, TTSSpeakRequest, LoginRequest, RefreshTokenRequest, LogoutRequest,
    CreateUserRequest, UpdateUserRequest, validate_audio_file_upload, validate_query_string,
    validate_user_id, validate_conversation_id, validate_date_string
)

# Prometheus metrics (guard against duplicate registration under dev servers)
REGISTRY = CollectorRegistry()
REQUEST_COUNT = Counter('gateway_requests_total', 'Total requests', ['method', 'endpoint', 'status'], registry=REGISTRY)
REQUEST_DURATION = Histogram('gateway_request_duration_seconds', 'Request duration', registry=REGISTRY)
ACTIVE_CONNECTIONS = Gauge('gateway_active_connections', 'Active WebSocket connections', registry=REGISTRY)
RATE_LIMIT_HITS = Counter('gateway_rate_limit_hits_total', 'Rate limit hits', registry=REGISTRY)

# Cache metrics (if caching is available)
CACHE_METRICS = None
if CACHE_AVAILABLE:
    CACHE_METRICS = CacheMetrics(registry=REGISTRY)

# Security (kept for backward compatibility, but auth_dependencies provides the new security)
security = HTTPBearer()

# Global state
active_connections: Dict[str, WebSocket] = {}
health_checker = HealthChecker()
message_buffer = CircularBuffer(1000)

# Rate limiting configuration
rate_limit_config = None
if RATE_LIMIT_AVAILABLE:
    # Configure endpoint-specific limits (stricter for expensive operations)
    endpoint_limits = {
        '/api/v1/llm/generate': {
            'per_minute': int(os.getenv("RATE_LIMIT_LLM_PER_MINUTE", "10")),
            'per_hour': int(os.getenv("RATE_LIMIT_LLM_PER_HOUR", "100")),
        },
        '/api/v1/tts/speak': {
            'per_minute': int(os.getenv("RATE_LIMIT_TTS_PER_MINUTE", "20")),
            'per_hour': int(os.getenv("RATE_LIMIT_TTS_PER_HOUR", "200")),
        },
        '/api/v1/audio/transcribe': {
            'per_minute': int(os.getenv("RATE_LIMIT_STT_PER_MINUTE", "20")),
            'per_hour': int(os.getenv("RATE_LIMIT_STT_PER_HOUR", "200")),
        },
        '/chat': {
            'per_minute': int(os.getenv("RATE_LIMIT_CHAT_PER_MINUTE", "30")),
            'per_hour': int(os.getenv("RATE_LIMIT_CHAT_PER_HOUR", "500")),
        },
    }
    
    rate_limit_config = RateLimitConfig(
        default_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")),
        default_per_hour=int(os.getenv("RATE_LIMIT_PER_HOUR", "1000")),
        default_per_day=int(os.getenv("RATE_LIMIT_PER_DAY", "10000")),
        endpoint_limits=endpoint_limits,
    )

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
        self.cache_manager = None
        if CACHE_AVAILABLE:
            cache_config = CacheConfig()
            self.cache_manager = CacheManager(config=cache_config, metrics=CACHE_METRICS)
        self._setup_middleware()
        self._setup_routes()
    
    def _setup_middleware(self):
        """Setup middleware."""
        # Get CORS origins from environment variable, default to allow all for development
        cors_origins = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]
        
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            allow_headers=["*"],
            expose_headers=["*"],
        )
        
        # Add rate limiting middleware if available
        if RATE_LIMIT_AVAILABLE and rate_limit_config:
            def identifier_extractor(request: Request) -> str:
                """Extract identifier from request (user ID or IP)."""
                # Try to get user ID from request state (set by auth middleware)
                user_id = getattr(request.state, 'user_id', None)
                if user_id:
                    return f"user:{user_id}"
                
                # Fallback to IP address
                client_ip = request.client.host if request.client else "unknown"
                # Handle forwarded IP from proxy
                forwarded_for = request.headers.get("X-Forwarded-For")
                if forwarded_for:
                    client_ip = forwarded_for.split(",")[0].strip()
                
                return f"ip:{client_ip}"
            
            self.app.add_middleware(
                RateLimitMiddleware,
                config=rate_limit_config,
                identifier_extractor=identifier_extractor,
                skip_paths=['/health', '/metrics', '/docs', '/openapi.json'],
            )
    
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.middleware("http")
        async def security_headers_middleware(request, call_next):
            """Add security headers to all HTTP responses."""
            response = await call_next(request)
            
            # Get security header configuration from environment variables
            # Content-Security-Policy - restrict resource loading
            csp = os.getenv(
                "CSP_HEADER",
                "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'self';"
            )
            
            # Strict-Transport-Security - enforce HTTPS (only in production)
            hsts_max_age = os.getenv("HSTS_MAX_AGE", "31536000")  # 1 year default
            include_subdomains = os.getenv("HSTS_INCLUDE_SUBDOMAINS", "true").lower() == "true"
            hsts = f"max-age={hsts_max_age}"
            if include_subdomains:
                hsts += "; includeSubDomains"
            if os.getenv("HSTS_PRELOAD", "false").lower() == "true":
                hsts += "; preload"
            
            # Add security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
            response.headers["Content-Security-Policy"] = csp
            
            # Only add HSTS if we're in production (HTTPS)
            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                response.headers["Strict-Transport-Security"] = hsts
            
            return response
        
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
            return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
        
        @self.app.get("/api/v1/stt/analytics")
        async def stt_analytics(
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
            audio_format: Optional[str] = Query(None, description="Filter by audio format"),
            source: Optional[str] = Query(None, description="Filter by source service")
        ):
            """
            Get STT transcription quality analytics.
            
            Query parameters:
            - start_date: Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            - end_date: End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            - audio_format: Filter by audio format (e.g., 'ogg', 'wav', 'pcm')
            - source: Filter by source service (e.g., 'telegram', 'gateway', 'stt_service')
            """
            try:
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        # Try just date format
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        # Try just date format
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                # Get metrics summary
                metrics_storage = get_metrics_storage()
                summary = metrics_storage.get_metrics_summary(
                    start_date=parsed_start_date,
                    end_date=parsed_end_date,
                    audio_format=audio_format,
                    source=source
                )
                
                return summary
                
            except Exception as e:
                logger.error(f"Failed to get STT analytics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve analytics: {str(e)}"
                )
        
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
        async def transcribe_audio(
            audio: UploadFile = File(...), 
            full_round_trip: str = "false",
            language: Optional[str] = Query(None, description="Language code for STT and TTS (ISO 639-1, e.g., 'en', 'es', 'fr'). Defaults to 'en' if not provided.")
        ):
            """Transcribe audio and optionally return audio response via round-trip.
            
            If full_round_trip=True:
            Audio → STT → Transcript → LLM → Text → TTS → Audio Response
            Otherwise:
            Audio → STT → Transcript
            
            Parameters:
            - audio: Audio file to transcribe
            - full_round_trip: If "true", perform full round-trip (STT → LLM → TTS)
            - language: Language code for STT and TTS (ISO 639-1). Defaults to "en" if not provided.
            """
            # Validate language parameter
            if language:
                language = validate_query_string(language, "language", max_length=10)
                # Validate language code format
                import re
                if not re.match(r'^[a-z]{2}(-[A-Z]{2})?$', language):
                    raise HTTPException(
                        status_code=400,
                        detail="Language must be a valid ISO 639-1 code (e.g., 'en', 'es', 'fr')"
                    )
            
            # Use provided language or default to "en"
            detected_language = language if language else "en"
            
            # Read and validate audio file
            data = await audio.read()
            
            # Validate audio file upload
            try:
                validated_data, validated_filename, validated_mime_type = validate_audio_file_upload(
                    file_content=data,
                    filename=audio.filename,
                    content_type=audio.content_type
                )
                data = validated_data  # Use validated data
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid audio file: {str(e)}"
                )
            
            # Generate cache key from audio data
            cache_key = None
            if self.cache_manager:
                import hashlib
                cache_key = hashlib.sha256(data).hexdigest()
                
                # Try to get from cache
                cached_transcript = await self.cache_manager.get(CacheType.STT_TRANSCRIPTION, cache_key)
                if cached_transcript is not None:
                    transcript = cached_transcript
                else:
                    # Use gRPC connection pool for STT
                    from grpc_pool import get_grpc_pool
                    grpc_pool = get_grpc_pool()
                    async with grpc_pool.get_stt_channel() as channel:
                        client = asr_shim.SpeechToTextClient(channel)
                        cfg = asr_shim.RecognitionConfig(language=detected_language, interim_results=False)
                        result = await client.recognize(data, sample_rate=16000, encoding="wav", config=cfg)
                        transcript = result.transcript
                    
                    # Cache the transcript
                    if cache_key:
                        await self.cache_manager.set(CacheType.STT_TRANSCRIPTION, cache_key, transcript)
            else:
                # Use gRPC connection pool for STT
                from grpc_pool import get_grpc_pool
                grpc_pool = get_grpc_pool()
                async with grpc_pool.get_stt_channel() as channel:
                    client = asr_shim.SpeechToTextClient(channel)
                    cfg = asr_shim.RecognitionConfig(language=detected_language, interim_results=False)
                    result = await client.recognize(data, sample_rate=16000, encoding="wav", config=cfg)
                    transcript = result.transcript
                
                # If STT service returns detected language, use it
                stt_detected_language = getattr(result, "detected_language", None)
                if stt_detected_language:
                    detected_language = stt_detected_language
                
            # Parse full_round_trip from string
            do_round_trip = full_round_trip.lower() in ("true", "1", "yes", "on")
            if not do_round_trip:
                return {"transcript": transcript, "detected_language": detected_language}
            
            # Full round-trip: STT → LLM → TTS
            # Step 2: Send transcript to LLM (with caching)
            from grpc_pool import get_grpc_pool
            grpc_pool = get_grpc_pool()
            
            llm_cache_key = None
            if self.cache_manager:
                import hashlib
                llm_cache_key = hashlib.sha256(transcript.encode()).hexdigest()
                cached_llm_response = await self.cache_manager.get(CacheType.LLM_RESPONSE, llm_cache_key)
                if cached_llm_response is not None:
                    llm_text = cached_llm_response
                else:
                    async with grpc_pool.get_llm_channel() as channel:
                        llm_client = llm_shim.LLMClient(channel)
                        llm_text = await llm_client.generate(transcript)
                    if llm_cache_key:
                        await self.cache_manager.set(CacheType.LLM_RESPONSE, llm_cache_key, llm_text)
            else:
                async with grpc_pool.get_llm_channel() as channel:
                    llm_client = llm_shim.LLMClient(channel)
                    llm_text = await llm_client.generate(transcript)
            
            # Step 3: Convert LLM response to audio via TTS (with caching)
            tts_cache_key = None
            if self.cache_manager:
                import hashlib
                tts_cache_key = hashlib.sha256(f"{llm_text}:{detected_language}:default".encode()).hexdigest()
                cached_audio = await self.cache_manager.get(CacheType.TTS_SYNTHESIS, tts_cache_key)
                if cached_audio is not None:
                    import base64
                    response_audio = cached_audio if isinstance(cached_audio, bytes) else base64.b64decode(cached_audio)
                else:
                    async with grpc_pool.get_tts_channel() as channel:
                        tts_client = tts_shim.TextToSpeechClient(channel)
                        tts_cfg = tts_shim.SynthesisConfig(sample_rate=16000, speed=1.0, pitch=0.0)
                        response_audio = await tts_client.synthesize(text=llm_text, voice_id="default", language=detected_language, config=tts_cfg)
                    if tts_cache_key:
                        # Store as base64 for JSON serialization
                        import base64
                        await self.cache_manager.set(CacheType.TTS_SYNTHESIS, tts_cache_key, base64.b64encode(response_audio).decode('ascii'))
            else:
                async with grpc_pool.get_tts_channel() as channel:
                    tts_client = tts_shim.TextToSpeechClient(channel)
                    tts_cfg = tts_shim.SynthesisConfig(sample_rate=16000, speed=1.0, pitch=0.0)
                    response_audio = await tts_client.synthesize(text=llm_text, voice_id="default", language=detected_language, config=tts_cfg)
            
            # Return both transcript and audio response
            import base64
            return {
                "transcript": transcript,
                "llm_response": llm_text,
                "audio_data": base64.b64encode(response_audio).decode("ascii"),
                "sample_rate": 16000,
                "detected_language": detected_language
            }

        @self.app.post("/api/v1/llm/generate")
        async def llm_generate(request: LLMGenerateRequest):
            """Generate text using LLM with input validation."""
            text = request.prompt
            
            # Generate cache key from prompt
            cache_key = None
            if self.cache_manager:
                import hashlib
                cache_key = hashlib.sha256(text.encode()).hexdigest()
                
                # Try to get from cache
                cached_response = await self.cache_manager.get(CacheType.LLM_RESPONSE, cache_key)
                if cached_response is not None:
                    return {"text": cached_response}
            
            # Generate response
            from grpc_pool import get_grpc_pool
            grpc_pool = get_grpc_pool()
            async with grpc_pool.get_llm_channel() as channel:
                client = llm_shim.LLMClient(channel)
                out = await client.generate(text)
                
                # Cache the response
                if self.cache_manager and cache_key:
                    await self.cache_manager.set(CacheType.LLM_RESPONSE, cache_key, out)
                
                return {"text": out}

        @self.app.post("/api/v1/tts/speak")
        async def tts_speak(request: TTSSpeakRequest):
            """Synthesize text to speech with input validation."""
            text = request.text
            language = request.language
            voice_id = request.voice_id
            
            # Generate cache key
            cache_key = None
            if self.cache_manager:
                import hashlib
                cache_key = hashlib.sha256(f"{text}:{language}:{voice_id}".encode()).hexdigest()
                
                # Try to get from cache
                cached_audio_b64 = await self.cache_manager.get(CacheType.TTS_SYNTHESIS, cache_key)
                if cached_audio_b64 is not None:
                    return {"audio_b64": cached_audio_b64, "sample_rate": 16000}
            
            # Generate audio
            from grpc_pool import get_grpc_pool
            grpc_pool = get_grpc_pool()
            async with grpc_pool.get_tts_channel() as channel:
                client = tts_shim.TextToSpeechClient(channel)
                cfg = tts_shim.SynthesisConfig(sample_rate=16000, speed=1.0, pitch=0.0)
                audio = await client.synthesize(text=text, voice_id=voice_id, language=language, config=cfg)
                import base64
                b64 = base64.b64encode(audio).decode("ascii")
                
                # Cache the result
                if self.cache_manager and cache_key:
                    await self.cache_manager.set(CacheType.TTS_SYNTHESIS, cache_key, b64)
                
                return {"audio_b64": b64, "sample_rate": 16000}
        
        @self.app.get("/conversations/analytics/metrics")
        async def get_conversation_analytics(
            user_id: str = Query(..., description="User ID"),
            chat_id: str = Query(..., description="Chat ID (session_id)")
        ):
            """
            Get analytics metrics for a specific conversation.
            
            Returns:
            - Message counts (total, user, assistant)
            - Average response time
            - User engagement score
            - First and last message timestamps
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                analytics = ConversationStorage.get_conversation_analytics(user_id, chat_id)
                return analytics
                
            except Exception as e:
                logger.error(f"Failed to get conversation analytics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve conversation analytics: {str(e)}"
                )
        
        @self.app.get("/conversations/analytics/dashboard")
        async def get_dashboard_analytics(
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)")
        ):
            """
            Get aggregated analytics across all conversations (dashboard view).
            
            Query parameters:
            - start_date: Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            - end_date: End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            
            Returns:
            - Total conversations
            - Total messages (user and assistant)
            - Average response time
            - Active users
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        # Try just date format
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        # Try just date format
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                analytics = ConversationStorage.get_dashboard_analytics(
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                return analytics
                
            except Exception as e:
                logger.error(f"Failed to get dashboard analytics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve dashboard analytics: {str(e)}"
                )
        
        @self.app.get("/conversations/analytics/report")
        async def generate_analytics_report(
            format: str = Query("json", description="Report format: 'json' or 'csv'"),
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)")
        ):
            """
            Generate analytics report in JSON or CSV format.
            
            Query parameters:
            - format: Report format - "json" or "csv" (default: "json")
            - start_date: Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            - end_date: End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            
            Returns:
            - JSON or CSV formatted report with analytics data
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        # Try just date format
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        # Try just date format
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                report = ConversationStorage.generate_analytics_report(
                    format=format,
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                
                # Set appropriate content type
                if format.lower() == "csv":
                    return Response(
                        content=report,
                        media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=analytics_report.csv"}
                    )
                else:
                    return Response(
                        content=report,
                        media_type="application/json"
                    )
                
            except Exception as e:
                logger.error(f"Failed to generate analytics report: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate analytics report: {str(e)}"
                )
        
        @self.app.post("/voice/quality")
        async def voice_quality(audio: UploadFile = File(...)):
            """
            Analyze voice message quality and provide feedback.
            
            Accepts audio file uploads (WAV, FLAC, OGG, etc.) and returns:
            - Quality scores (overall, volume, clarity, noise)
            - Textual feedback
            - Improvement suggestions
            """
            # Read and validate audio file
            data = await audio.read()
            
            # Validate audio file upload
            try:
                validated_data, validated_filename, validated_mime_type = validate_audio_file_upload(
                    file_content=data,
                    filename=audio.filename,
                    content_type=audio.content_type
                )
                data = validated_data  # Use validated data
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid audio file: {str(e)}"
                )
            try:
                # Import voice quality scorer
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from voice_quality import VoiceQualityScorer, VoiceQualityError
                
                # Read audio data
                audio_data = await audio.read()
                audio_format = audio.filename.split('.')[-1].lower() if audio.filename else None
                
                # Score the voice message
                scorer = VoiceQualityScorer()
                result = scorer.score_voice_message(audio_data, audio_format=audio_format)
                
                return result
                
            except Exception as e:
                logger.error(f"Voice quality analysis failed: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to analyze voice quality: {str(e)}"
                )
        
        # ==================== Cost Tracking Endpoints ====================
        
        @self.app.get("/costs/user/{user_id}")
        async def get_user_costs(
            user_id: str,
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)")
        ):
            """
            Get cost summary for a user.
            
            Query parameters:
            - start_date: Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            - end_date: End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            
            Returns:
            - Total cost
            - Cost breakdown by service (STT, TTS, LLM)
            - Usage counts per service
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from cost_tracking import get_user_costs
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                costs = get_user_costs(
                    user_id=user_id,
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                
                return costs
                
            except Exception as e:
                logger.error(f"Failed to get user costs: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve user costs: {str(e)}"
                )
        
        @self.app.get("/costs/conversation/{conversation_id}")
        async def get_conversation_costs(
            conversation_id: str,
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)")
        ):
            """
            Get cost summary for a conversation.
            
            Query parameters:
            - start_date: Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            - end_date: End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            
            Returns:
            - Total cost for the conversation
            - Cost breakdown by service (STT, TTS, LLM)
            - Usage counts per service
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from cost_tracking import get_conversation_costs
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                costs = get_conversation_costs(
                    conversation_id=conversation_id,
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                
                return costs
                
            except Exception as e:
                logger.error(f"Failed to get conversation costs: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve conversation costs: {str(e)}"
                )
        
        @self.app.get("/costs/user/{user_id}/report")
        async def get_user_billing_report(
            user_id: str,
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)")
        ):
            """
            Generate a detailed billing report for a user.
            
            Query parameters:
            - start_date: Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            - end_date: End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            
            Returns:
            - Total cost
            - Service breakdown with min/max/avg costs
            - Detailed cost entries
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from cost_tracking import generate_billing_report
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                report = generate_billing_report(
                    user_id=user_id,
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                
                return report
                
            except Exception as e:
                logger.error(f"Failed to generate billing report: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate billing report: {str(e)}"
                )
        
        # Prompt Template REST API endpoints
        @self.app.post("/prompt-templates")
        async def create_prompt_template(payload: Dict[str, Any]):
            """
            Create a new prompt template.
            
            Request body:
            - name: Template name (required)
            - template_text: Template content with {variable} placeholders (required)
            - user_id: Optional user ID for per-user templates
            - conversation_id: Optional conversation ID for per-conversation templates (requires user_id)
            - description: Optional description
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                name = payload.get("name")
                template_text = payload.get("template_text")
                user_id = payload.get("user_id")
                conversation_id = payload.get("conversation_id")
                description = payload.get("description")
                
                if not name or not template_text:
                    raise HTTPException(
                        status_code=400,
                        detail="name and template_text are required"
                    )
                
                template_id = ConversationStorage.create_prompt_template(
                    name=name,
                    template_text=template_text,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    description=description
                )
                
                if not template_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to create template (check validation or constraints)"
                    )
                
                template = ConversationStorage.get_prompt_template(template_id)
                return template
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to create prompt template: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create prompt template: {str(e)}"
                )
        
        @self.app.get("/prompt-templates/{template_id}")
        async def get_prompt_template(template_id: str):
            """Get a prompt template by ID."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                template = ConversationStorage.get_prompt_template(template_id)
                
                if not template:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Template not found: {template_id}"
                    )
                
                return template
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to get prompt template: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get prompt template: {str(e)}"
                )
        
        @self.app.get("/prompt-templates")
        async def list_prompt_templates(
            user_id: Optional[str] = Query(None),
            conversation_id: Optional[str] = Query(None),
            is_active: Optional[bool] = Query(None)
        ):
            """
            List prompt templates with optional filters.
            
            Query parameters:
            - user_id: Filter by user ID
            - conversation_id: Filter by conversation ID
            - is_active: Filter by active status (true/false)
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                templates = ConversationStorage.list_prompt_templates(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    is_active=is_active
                )
                
                return {"templates": templates, "count": len(templates)}
                
            except Exception as e:
                logger.error(f"Failed to list prompt templates: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to list prompt templates: {str(e)}"
                )
        
        @self.app.get("/prompt-templates/user/{user_id}")
        async def get_user_prompt_template(
            user_id: str,
            name: Optional[str] = Query(None)
        ):
            """Get a user-specific prompt template."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                template = ConversationStorage.get_prompt_template_for_user(user_id, name)
                
                if not template:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Template not found for user: {user_id}"
                    )
                
                return template
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to get user prompt template: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get user prompt template: {str(e)}"
                )
        
        @self.app.get("/prompt-templates/conversation/{user_id}/{chat_id}")
        async def get_conversation_prompt_template(
            user_id: str,
            chat_id: str,
            name: Optional[str] = Query(None)
        ):
            """Get a conversation-specific prompt template (with fallback to user template)."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                template = ConversationStorage.get_prompt_template_for_conversation(user_id, chat_id, name)
                
                if not template:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Template not found for conversation: {user_id}/{chat_id}"
                    )
                
                return template
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to get conversation prompt template: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get conversation prompt template: {str(e)}"
                )
        
        @self.app.put("/prompt-templates/{template_id}")
        async def update_prompt_template(template_id: str, payload: Dict[str, Any]):
            """
            Update a prompt template.
            
            Request body (all optional):
            - template_text: New template text
            - description: New description
            - is_active: New active status
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                template_text = payload.get("template_text")
                description = payload.get("description")
                is_active = payload.get("is_active")
                
                success = ConversationStorage.update_prompt_template(
                    template_id=template_id,
                    template_text=template_text,
                    description=description,
                    is_active=is_active
                )
                
                if not success:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Template not found or update failed: {template_id}"
                    )
                
                template = ConversationStorage.get_prompt_template(template_id)
                return template
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to update prompt template: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update prompt template: {str(e)}"
                )
        
        @self.app.delete("/prompt-templates/{template_id}")
        async def delete_prompt_template(template_id: str):
            """Delete a prompt template."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                success = ConversationStorage.delete_prompt_template(template_id)
                
                if not success:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Template not found: {template_id}"
                    )
                
                return {"message": f"Template {template_id} deleted successfully"}
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to delete prompt template: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete prompt template: {str(e)}"
                )
        
        @self.app.get("/conversations/{user_id}/{chat_id}/export")
        async def export_conversation(
            user_id: str,
            chat_id: str,
            format: str = Query("json", description="Export format: 'json', 'txt', or 'pdf'"),
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)")
        ):
            """
            Export conversation to JSON, TXT, or PDF format.
            
            Query parameters:
            - format: Export format - "json", "txt", or "pdf" (default: "json")
            - start_date: Start date filter for messages (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            - end_date: End date filter for messages (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            
            Returns:
            - Exported conversation file in the requested format
            """
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        # Try just date format
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        # Try just date format
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                # Validate format
                if format.lower() not in ["json", "txt", "pdf"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported format: {format}. Supported formats: json, txt, pdf"
                    )
                
                # Export conversation
                export_data = ConversationStorage.export_conversation(
                    user_id=user_id,
                    chat_id=chat_id,
                    format=format.lower(),
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                
                # Set appropriate content type and filename
                content_type_map = {
                    "json": "application/json",
                    "txt": "text/plain",
                    "pdf": "application/pdf"
                }
                extension_map = {
                    "json": "json",
                    "txt": "txt",
                    "pdf": "pdf"
                }
                
                content_type = content_type_map.get(format.lower(), "application/octet-stream")
                extension = extension_map.get(format.lower(), "bin")
                filename = f"conversation_{user_id}_{chat_id}.{extension}"
                
                return Response(
                    content=export_data,
                    media_type=content_type,
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
                
            except ValueError as e:
                raise HTTPException(
                    status_code=404,
                    detail=str(e)
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to export conversation: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to export conversation: {str(e)}"
                )
        
        # ==================== A/B Testing Endpoints ====================
        
        @self.app.post("/ab-tests")
        async def create_ab_test(payload: Dict[str, Any]):
            """Create a new A/B test."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                name = payload.get("name")
                variants = payload.get("variants")
                description = payload.get("description")
                traffic_split = payload.get("traffic_split", 1.0)
                
                if not name or not variants:
                    raise HTTPException(
                        status_code=400,
                        detail="name and variants are required"
                    )
                
                test_id = ConversationStorage.create_ab_test(
                    name=name,
                    variants=variants,
                    description=description,
                    traffic_split=traffic_split
                )
                
                if not test_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to create A/B test (name may already exist)"
                    )
                
                return {"test_id": test_id, "name": name}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to create A/B test: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create A/B test: {str(e)}"
                )
        
        @self.app.get("/ab-tests")
        async def list_ab_tests(active_only: bool = Query(False)):
            """List all A/B tests."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                tests = ConversationStorage.list_ab_tests(active_only=active_only)
                return {"tests": tests, "count": len(tests)}
            except Exception as e:
                logger.error(f"Failed to list A/B tests: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to list A/B tests: {str(e)}"
                )
        
        @self.app.get("/ab-tests/{test_id}")
        async def get_ab_test(test_id: str):
            """Get A/B test details."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                test = ConversationStorage.get_ab_test(test_id)
                if not test:
                    raise HTTPException(
                        status_code=404,
                        detail=f"A/B test {test_id} not found"
                    )
                return test
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to get A/B test: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get A/B test: {str(e)}"
                )
        
        @self.app.put("/ab-tests/{test_id}")
        async def update_ab_test(test_id: str, payload: Dict[str, Any]):
            """Update an A/B test."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                description = payload.get("description")
                variants = payload.get("variants")
                traffic_split = payload.get("traffic_split")
                is_active = payload.get("is_active")
                
                success = ConversationStorage.update_ab_test(
                    test_id=test_id,
                    description=description,
                    variants=variants,
                    traffic_split=traffic_split,
                    is_active=is_active
                )
                
                if not success:
                    raise HTTPException(
                        status_code=404,
                        detail=f"A/B test {test_id} not found"
                    )
                
                return {"success": True, "test_id": test_id}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to update A/B test: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update A/B test: {str(e)}"
                )
        
        @self.app.post("/ab-tests/{test_id}/deactivate")
        async def deactivate_ab_test(test_id: str):
            """Deactivate an A/B test."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                success = ConversationStorage.deactivate_ab_test(test_id)
                
                if not success:
                    raise HTTPException(
                        status_code=404,
                        detail=f"A/B test {test_id} not found"
                    )
                
                return {"success": True, "test_id": test_id}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to deactivate A/B test: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to deactivate A/B test: {str(e)}"
                )
        
        @self.app.get("/ab-tests/{test_id}/metrics")
        async def get_ab_test_metrics(
            test_id: str,
            variant_name: Optional[str] = Query(None),
            metric_type: Optional[str] = Query(None),
            start_date: Optional[str] = Query(None),
            end_date: Optional[str] = Query(None)
        ):
            """Get metrics for an A/B test."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                metrics = ConversationStorage.get_ab_metrics(
                    test_id=test_id,
                    variant_name=variant_name,
                    metric_type=metric_type,
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                
                return {"metrics": metrics, "count": len(metrics)}
            except Exception as e:
                logger.error(f"Failed to get A/B test metrics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get A/B test metrics: {str(e)}"
                )
        
        @self.app.get("/ab-tests/{test_id}/statistics")
        async def get_ab_test_statistics(test_id: str):
            """Get statistical analysis for an A/B test."""
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from conversation_storage import ConversationStorage
                
                statistics = ConversationStorage.get_ab_statistics(test_id)
                
                if "error" in statistics:
                    raise HTTPException(
                        status_code=404 if "not found" in statistics.get("error", "").lower() else 500,
                        detail=statistics["error"]
                    )
                
                return statistics
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to get A/B test statistics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get A/B test statistics: {str(e)}"
                )
        
        # ==================== Admin Authentication Endpoints ====================
        
        # ==================== Authentication Endpoints ====================
        
        @self.app.post("/auth/login")
        async def login(login_request: LoginRequest, request: Request = None):
            """
            User login endpoint - validates credentials and returns JWT access token and refresh token.
            Supports both username/password and user_id (external auth) authentication.
            """
            payload = {
                "username": login_request.username,
                "password": login_request.password,
                "user_id": login_request.user_id
            }
            username = payload.get("username")
            password = payload.get("password")
            user_id = payload.get("user_id")  # For external auth (e.g., Telegram)
            
            if not ((username and password) or user_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either (username and password) or user_id is required"
                )
            
            # Authenticate user
            user_data = authenticate_user(
                username=username,
                password=password,
                user_id=user_id
            )
            
            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            # Create access token
            access_token = create_access_token(
                user_id=user_data["user_id"],
                roles=user_data.get("roles", []),
                permissions=user_data.get("permissions", [])
            )
            
            # Create refresh token
            device_info = request.headers.get("User-Agent", "") if request else None
            ip_address = request.client.host if request else None
            refresh_token, _ = create_refresh_token(
                user_id=user_data["user_id"],
                device_info=device_info,
                ip_address=ip_address
            )
            
            # Log login (if audit logging available)
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="user_login",
                    actor_user_id=user_data["user_id"],
                    details={"username": username or user_id}
                )
            except Exception as e:
                logger.warning(f"Failed to log audit action: {e}")
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user_id": user_data["user_id"],
                "username": user_data.get("username"),
                "roles": user_data.get("roles", [])
            }
        
        @self.app.post("/auth/refresh")
        async def refresh_token(request: RefreshTokenRequest):
            """
            Refresh access token using refresh token.
            """
            refresh_token_value = request.refresh_token
            
            if not refresh_token_value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="refresh_token is required"
                )
            
            # Verify refresh token
            user_data = verify_refresh_token(refresh_token_value)
            
            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token"
                )
            
            # Create new access token
            access_token = create_access_token(
                user_id=user_data["user_id"],
                roles=user_data.get("roles", []),
                permissions=user_data.get("permissions", [])
            )
            
            return {
                "access_token": access_token,
                "token_type": "bearer"
            }
        
        @self.app.post("/auth/logout")
        async def logout(request: LogoutRequest, user: dict = Depends(get_current_user)):
            """
            Logout endpoint - revokes refresh token.
            """
            refresh_token_value = request.refresh_token
            
            if refresh_token_value:
                revoke_refresh_token(refresh_token_value)
            else:
                # Revoke all refresh tokens for the user
                revoke_all_user_refresh_tokens(user["user_id"])
            
            return {"message": "Logged out successfully"}
        
        @self.app.post("/admin/auth/login")
        async def admin_login(payload: Dict[str, Any], request: Request = None):
            """
            Admin login endpoint (backward compatibility) - validates credentials and returns JWT token.
            This endpoint is kept for backward compatibility but uses the new authentication system.
            """
            username = payload.get("username")
            password = payload.get("password")
            
            if not username or not password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username and password are required"
                )
            
            # Authenticate user
            user_data = authenticate_user(username=username, password=password)
            
            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password"
                )
            
            # Check if user has admin role
            if "admin" not in user_data.get("roles", []):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin access required"
                )
            
            # Create access token
            access_token = create_access_token(
                user_id=user_data["user_id"],
                roles=user_data.get("roles", []),
                permissions=user_data.get("permissions", [])
            )
            
            # Create refresh token
            device_info = request.headers.get("User-Agent", "") if request else None
            ip_address = request.client.host if request else None
            refresh_token, _ = create_refresh_token(
                user_id=user_data["user_id"],
                device_info=device_info,
                ip_address=ip_address
            )
            
            # Log admin login
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="admin_login",
                    actor_user_id=user_data["user_id"],
                    details={"username": username}
                )
            except Exception as e:
                logger.warning(f"Failed to log audit action: {e}")
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user_id": user_data["user_id"],
                "username": user_data.get("username"),
                "role": "admin"
            }
        
        # ==================== Admin User Management Endpoints ====================
        
        async def verify_admin(user: dict = Depends(require_admin)) -> str:
            """Verify JWT token and check if user is admin (using new auth system)."""
            return user["user_id"]
        
        @self.app.get("/admin/users")
        async def list_users(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
            search: Optional[str] = Query(None),
            status: Optional[str] = Query(None, regex="^(active|blocked|admin)$"),
            admin_user_id: str = Depends(verify_admin)
        ):
            """List users with pagination, search, and filtering."""
            try:
                result = get_users(page=page, page_size=page_size, search=search, status=status)
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="users_listed",
                    actor_user_id=admin_user_id,
                    details={"page": page, "page_size": page_size, "search": search, "status": status}
                )
                
                return result
            except Exception as e:
                logger.error(f"Failed to list users: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to list users: {str(e)}"
                )
        
        @self.app.get("/admin/users/stats")
        async def get_users_stats(admin_user_id: str = Depends(verify_admin)):
            """Get user statistics."""
            try:
                stats = get_user_statistics()
                return stats
            except Exception as e:
                logger.error(f"Failed to get user statistics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get user statistics: {str(e)}"
                )
        
        @self.app.get("/admin/users/{user_id}")
        async def get_user_detail(
            user_id: str,
            admin_user_id: str = Depends(verify_admin)
        ):
            """Get detailed information about a user."""
            try:
                user = get_user(user_id)
                if not user:
                    raise HTTPException(
                        status_code=404,
                        detail=f"User not found: {user_id}"
                    )
                return user
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to get user {user_id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get user: {str(e)}"
                )
        
        @self.app.post("/admin/users")
        async def create_user_endpoint(
            payload: Dict[str, Any],
            admin_user_id: str = Depends(verify_admin)
        ):
            """Create a new user."""
            try:
                user_id = payload.get("user_id")
                if not user_id:
                    raise HTTPException(
                        status_code=400,
                        detail="user_id is required"
                    )
                
                metadata = payload.get("metadata")
                success = create_user(user_id, metadata)
                
                if not success:
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to create user (may already exist)"
                    )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="user_created",
                    actor_user_id=admin_user_id,
                    target_user_id=user_id,
                    details=metadata
                )
                
                user = get_user(user_id)
                return user
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to create user: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create user: {str(e)}"
                )
        
        @self.app.put("/admin/users/{user_id}")
        async def update_user(
            user_id: str,
            payload: Dict[str, Any],
            admin_user_id: str = Depends(verify_admin)
        ):
            """Update user information (primarily status)."""
            try:
                status = payload.get("status")
                reason = payload.get("reason")
                
                if not status:
                    raise HTTPException(
                        status_code=400,
                        detail="status is required"
                    )
                
                if status not in ["active", "blocked", "suspended"]:
                    raise HTTPException(
                        status_code=400,
                        detail="status must be 'active', 'blocked', or 'suspended'"
                    )
                
                success = update_user_status(user_id, status, admin_user_id, reason)
                
                if not success:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to update user status"
                    )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="user_updated",
                    actor_user_id=admin_user_id,
                    target_user_id=user_id,
                    details={"status": status, "reason": reason}
                )
                
                user = get_user(user_id)
                return user
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to update user {user_id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update user: {str(e)}"
                )
        
        @self.app.delete("/admin/users/{user_id}")
        async def delete_user_endpoint(
            user_id: str,
            admin_user_id: str = Depends(verify_admin)
        ):
            """Delete a user and all their data."""
            try:
                # Prevent self-deletion
                if user_id == admin_user_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot delete yourself"
                    )
                
                success = delete_user(user_id, admin_user_id)
                
                if not success:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to delete user"
                    )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="user_deleted",
                    actor_user_id=admin_user_id,
                    target_user_id=user_id
                )
                
                return {"message": f"User {user_id} deleted successfully"}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to delete user {user_id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete user: {str(e)}"
                )
        
        # ==================== Admin Conversation Management Endpoints ====================
        
        @self.app.get("/admin/conversations")
        async def list_conversations(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
            user_id: Optional[str] = Query(None),
            search: Optional[str] = Query(None),
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
            admin_user_id: str = Depends(verify_admin)
        ):
            """List conversations with pagination, search, and filtering."""
            try:
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                result = get_conversations(
                    page=page,
                    page_size=page_size,
                    user_id=user_id,
                    search=search,
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="conversations_listed",
                    actor_user_id=admin_user_id,
                    details={"page": page, "page_size": page_size, "user_id": user_id, "search": search}
                )
                
                return result
            except Exception as e:
                logger.error(f"Failed to list conversations: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to list conversations: {str(e)}"
                )
        
        @self.app.get("/admin/conversations/stats")
        async def get_conversations_stats(admin_user_id: str = Depends(verify_admin)):
            """Get conversation statistics."""
            try:
                stats = get_conversation_statistics()
                return stats
            except Exception as e:
                logger.error(f"Failed to get conversation statistics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get conversation statistics: {str(e)}"
                )
        
        @self.app.get("/admin/conversations/{conversation_id}")
        async def get_conversation_detail(
            conversation_id: str,
            admin_user_id: str = Depends(verify_admin)
        ):
            """Get detailed information about a conversation including all messages."""
            try:
                conversation = get_conversation(conversation_id)
                if not conversation:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Conversation not found: {conversation_id}"
                    )
                return conversation
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to get conversation {conversation_id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get conversation: {str(e)}"
                )
        
        @self.app.get("/admin/conversations/search")
        async def search_conversations_endpoint(
            q: str = Query(..., description="Search query"),
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
            user_id: Optional[str] = Query(None),
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
            admin_user_id: str = Depends(verify_admin)
        ):
            """Search conversations by user, message content, or date."""
            try:
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                result = search_conversations(
                    query=q,
                    page=page,
                    page_size=page_size,
                    user_id=user_id,
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="conversations_searched",
                    actor_user_id=admin_user_id,
                    details={"query": q, "page": page, "user_id": user_id}
                )
                
                return result
            except Exception as e:
                logger.error(f"Failed to search conversations: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to search conversations: {str(e)}"
                )
        
        @self.app.delete("/admin/conversations/{conversation_id}")
        async def delete_conversation_endpoint(
            conversation_id: str,
            admin_user_id: str = Depends(verify_admin)
        ):
            """Delete a conversation and all its messages."""
            try:
                success = delete_conversation(conversation_id, admin_user_id)
                
                if not success:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Conversation not found: {conversation_id}"
                    )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="conversation_deleted",
                    actor_user_id=admin_user_id,
                    target_conversation_id=conversation_id
                )
                
                return {"message": f"Conversation {conversation_id} deleted successfully"}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to delete conversation {conversation_id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete conversation: {str(e)}"
                )
        
        # ==================== Admin Bot Management Endpoints ====================
        
        @self.app.get("/admin/bot/config")
        async def get_bot_config_endpoint(admin_user_id: str = Depends(verify_admin)):
            """Get bot configuration."""
            try:
                config = get_bot_config()
                return config
            except Exception as e:
                logger.error(f"Failed to get bot config: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve bot config: {str(e)}"
                )
        
        @self.app.put("/admin/bot/config")
        async def update_bot_config_endpoint(
            payload: Dict[str, Any],
            admin_user_id: str = Depends(verify_admin)
        ):
            """Update bot configuration."""
            try:
                bot_token = payload.get("bot_token")
                webhook_url = payload.get("webhook_url")
                max_file_size_mb = payload.get("max_file_size_mb")
                max_duration_seconds = payload.get("max_duration_seconds")
                is_active = payload.get("is_active")
                
                success = update_bot_config(
                    bot_token=bot_token,
                    webhook_url=webhook_url,
                    max_file_size_mb=max_file_size_mb,
                    max_duration_seconds=max_duration_seconds,
                    is_active=is_active
                )
                
                if not success:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to update bot config"
                    )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="bot_config_updated",
                    actor_user_id=admin_user_id,
                    details={
                        "max_file_size_mb": max_file_size_mb,
                        "max_duration_seconds": max_duration_seconds,
                        "is_active": is_active
                    }
                )
                
                config = get_bot_config()
                return config
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to update bot config: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update bot config: {str(e)}"
                )
        
        @self.app.get("/admin/bot/status")
        async def get_bot_status_endpoint(admin_user_id: str = Depends(verify_admin)):
            """Get bot status (online/offline, last activity)."""
            try:
                status = get_bot_status()
                return status
            except Exception as e:
                logger.error(f"Failed to get bot status: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve bot status: {str(e)}"
                )
        
        @self.app.get("/admin/bot/stats")
        async def get_bot_stats_endpoint(admin_user_id: str = Depends(verify_admin)):
            """Get bot statistics (total messages, active conversations, error rate)."""
            try:
                stats = get_bot_statistics()
                return stats
            except Exception as e:
                logger.error(f"Failed to get bot stats: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve bot stats: {str(e)}"
                )
        
        @self.app.get("/admin/bot/commands")
        async def list_bot_commands_endpoint(admin_user_id: str = Depends(verify_admin)):
            """List all bot commands."""
            try:
                commands = get_bot_commands()
                return {"commands": commands, "count": len(commands)}
            except Exception as e:
                logger.error(f"Failed to list bot commands: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to list bot commands: {str(e)}"
                )
        
        @self.app.post("/admin/bot/commands")
        async def create_bot_command_endpoint(
            payload: Dict[str, Any],
            admin_user_id: str = Depends(verify_admin)
        ):
            """Create a new bot command."""
            try:
                command = payload.get("command")
                description = payload.get("description")
                
                if not command or not description:
                    raise HTTPException(
                        status_code=400,
                        detail="command and description are required"
                    )
                
                command_id = create_bot_command(command, description)
                
                if not command_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to create bot command (may already exist)"
                    )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="bot_command_created",
                    actor_user_id=admin_user_id,
                    details={"command": command, "description": description}
                )
                
                commands = get_bot_commands()
                return {"message": f"Command '{command}' created successfully", "commands": commands}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to create bot command: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create bot command: {str(e)}"
                )
        
        @self.app.put("/admin/bot/commands/{command_id}")
        async def update_bot_command_endpoint(
            command_id: str,
            payload: Dict[str, Any],
            admin_user_id: str = Depends(verify_admin)
        ):
            """Update a bot command."""
            try:
                description = payload.get("description")
                is_active = payload.get("is_active")
                
                success = update_bot_command(
                    command_id=command_id,
                    description=description,
                    is_active=is_active
                )
                
                if not success:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Bot command not found: {command_id}"
                    )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="bot_command_updated",
                    actor_user_id=admin_user_id,
                    details={"command_id": command_id, "description": description, "is_active": is_active}
                )
                
                commands = get_bot_commands()
                return {"message": f"Command updated successfully", "commands": commands}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to update bot command: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update bot command: {str(e)}"
                )
        
        @self.app.delete("/admin/bot/commands/{command_id}")
        async def delete_bot_command_endpoint(
            command_id: str,
            admin_user_id: str = Depends(verify_admin)
        ):
            """Delete a bot command."""
            try:
                success = delete_bot_command(command_id)
                
                if not success:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Bot command not found: {command_id}"
                    )
                
                # Log audit action
                sys.path.insert(0, str(Path(__file__).parent.parent / "telegram"))
                from admin_db import log_audit_action
                log_audit_action(
                    action="bot_command_deleted",
                    actor_user_id=admin_user_id,
                    details={"command_id": command_id}
                )
                
                return {"message": f"Command deleted successfully"}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to delete bot command: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete bot command: {str(e)}"
                )
        
        # ==================== Admin System Monitoring Endpoints ====================
        
        @self.app.get("/admin/monitoring/services")
        async def get_monitoring_services(admin_user_id: str = Depends(verify_admin)):
            """Get health status for all services."""
            try:
                services_health = get_all_services_health()
                return services_health
            except Exception as e:
                logger.error(f"Failed to get services health: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve services health: {str(e)}"
                )
        
        @self.app.get("/admin/monitoring/metrics")
        async def get_monitoring_metrics(admin_user_id: str = Depends(verify_admin)):
            """Get metrics for all services."""
            try:
                metrics = get_all_metrics()
                return metrics
            except Exception as e:
                logger.error(f"Failed to get metrics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve metrics: {str(e)}"
                )
        
        @self.app.get("/admin/monitoring/health")
        async def get_monitoring_health(admin_user_id: str = Depends(verify_admin)):
            """Get comprehensive health check including services, metrics, and alerts."""
            try:
                services_health = get_all_services_health()
                metrics = get_all_metrics()
                recent_errors = get_recent_errors()
                
                # Determine overall system health
                unhealthy_services = [s for s in services_health["services"] if s["status"] != "healthy"]
                overall_status = "healthy" if len(unhealthy_services) == 0 else "degraded" if len(unhealthy_services) < len(services_health["services"]) / 2 else "unhealthy"
                
                return {
                    "overall_status": overall_status,
                    "services": services_health,
                    "metrics": metrics,
                    "recent_errors": recent_errors,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Failed to get monitoring health: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve monitoring health: {str(e)}"
                )
        
        # ==================== Admin Analytics Endpoints ====================
        
        @self.app.get("/admin/analytics/users")
        async def get_user_analytics_endpoint(
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
            admin_user_id: str = Depends(verify_admin)
        ):
            """Get user analytics including user growth, active users, and retention."""
            try:
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                analytics = get_user_analytics(
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                return analytics
            except Exception as e:
                logger.error(f"Failed to get user analytics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve user analytics: {str(e)}"
                )
        
        @self.app.get("/admin/analytics/conversations")
        async def get_conversation_analytics_endpoint(
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
            admin_user_id: str = Depends(verify_admin)
        ):
            """Get conversation analytics including total conversations, average length, and peak usage."""
            try:
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                analytics = get_conversation_analytics(
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                return analytics
            except Exception as e:
                logger.error(f"Failed to get conversation analytics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve conversation analytics: {str(e)}"
                )
        
        @self.app.get("/admin/analytics/bot")
        async def get_bot_analytics_endpoint(
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
            admin_user_id: str = Depends(verify_admin)
        ):
            """Get bot performance analytics including response times, error rates, and success rates."""
            try:
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                analytics = get_bot_performance_analytics(
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                return analytics
            except Exception as e:
                logger.error(f"Failed to get bot analytics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve bot analytics: {str(e)}"
                )
        
        @self.app.get("/admin/analytics/system")
        async def get_system_analytics_endpoint(
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
            admin_user_id: str = Depends(verify_admin)
        ):
            """Get system usage analytics including API calls, service usage, and resource utilization."""
            try:
                from datetime import datetime
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                analytics = get_system_usage_analytics(
                    start_date=parsed_start_date,
                    end_date=parsed_end_date
                )
                return analytics
            except Exception as e:
                logger.error(f"Failed to get system analytics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve system analytics: {str(e)}"
                )
        
        @self.app.get("/admin/analytics/export")
        async def export_analytics_endpoint(
            format: str = Query("json", description="Export format: 'json' or 'csv'"),
            start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
            end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
            admin_user_id: str = Depends(verify_admin)
        ):
            """Export analytics data in JSON or CSV format."""
            try:
                from datetime import datetime
                import csv
                import io
                
                # Parse dates if provided
                parsed_start_date = None
                parsed_end_date = None
                
                if start_date:
                    try:
                        parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_start_date = datetime.fromisoformat(f"{start_date}T00:00:00")
                
                if end_date:
                    try:
                        parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        parsed_end_date = datetime.fromisoformat(f"{end_date}T23:59:59")
                
                # Get all analytics data
                user_analytics = get_user_analytics(parsed_start_date, parsed_end_date)
                conversation_analytics = get_conversation_analytics(parsed_start_date, parsed_end_date)
                bot_analytics = get_bot_performance_analytics(parsed_start_date, parsed_end_date)
                system_analytics = get_system_usage_analytics(parsed_start_date, parsed_end_date)
                
                if format.lower() == "csv":
                    # Generate CSV
                    output = io.StringIO()
                    writer = csv.writer(output)
                    
                    # Write headers
                    writer.writerow(["Category", "Metric", "Value"])
                    
                    # User analytics
                    writer.writerow(["Users", "Total Users", user_analytics["total_users"]])
                    writer.writerow(["Users", "Active Users", user_analytics["active_users"]])
                    writer.writerow(["Users", "Retention Rate", f"{user_analytics['retention_rate']}%"])
                    
                    # Conversation analytics
                    writer.writerow(["Conversations", "Total Conversations", conversation_analytics["total_conversations"]])
                    writer.writerow(["Conversations", "Average Length", conversation_analytics["average_length"]])
                    
                    # Bot analytics
                    writer.writerow(["Bot", "Total Messages", bot_analytics["total_messages"]])
                    writer.writerow(["Bot", "Average Response Time", f"{bot_analytics['average_response_time']}s"])
                    writer.writerow(["Bot", "Success Rate", f"{bot_analytics['success_rate']}%"])
                    writer.writerow(["Bot", "Error Rate", f"{bot_analytics['error_rate']}%"])
                    
                    # System analytics
                    writer.writerow(["System", "Total API Calls", system_analytics["total_api_calls"]])
                    
                    csv_content = output.getvalue()
                    return Response(
                        content=csv_content,
                        media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=analytics_export.csv"}
                    )
                else:
                    # Return JSON
                    return {
                        "user_analytics": user_analytics,
                        "conversation_analytics": conversation_analytics,
                        "bot_analytics": bot_analytics,
                        "system_analytics": system_analytics,
                        "export_date": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.error(f"Failed to export analytics: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to export analytics: {str(e)}"
                )
        
        # ==================== Admin System Configuration Endpoints ====================
        
        @self.app.get("/admin/config")
        async def get_system_config_endpoint(admin_user_id: str = Depends(verify_admin)):
            """Get current system configuration."""
            try:
                config = get_system_config()
                return config
            except Exception as e:
                logger.error(f"Failed to get system config: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve system config: {str(e)}"
                )
        
        @self.app.put("/admin/config")
        async def update_system_config_endpoint(
            payload: Dict[str, Any],
            admin_user_id: str = Depends(verify_admin)
        ):
            """Update system configuration."""
            try:
                config = payload.get("config", {})
                category = payload.get("category")
                
                if not config:
                    raise HTTPException(
                        status_code=400,
                        detail="Configuration data is required"
                    )
                
                # Validate configuration
                is_valid, error_msg = validate_config(config)
                if not is_valid:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid configuration: {error_msg}"
                    )
                
                # Update configuration
                success = update_system_config(config, admin_user_id, category)
                
                if not success:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to update system configuration"
                    )
                
                # Return updated configuration
                updated_config = get_system_config()
                return {
                    "message": "Configuration updated successfully",
                    "config": updated_config
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to update system config: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update system config: {str(e)}"
                )
        
        @self.app.get("/admin/config/history")
        async def get_config_history_endpoint(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
            category: Optional[str] = Query(None),
            admin_user_id: str = Depends(verify_admin)
        ):
            """Get configuration history with pagination."""
            try:
                history = get_config_history(page, page_size, category)
                return history
            except Exception as e:
                logger.error(f"Failed to get config history: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve config history: {str(e)}"
                )
        
        @self.app.post("/auth/token")
        async def create_token(user_id: str = "default"):
            """
            Create JWT token for authentication (backward compatibility endpoint).
            This endpoint is kept for backward compatibility but uses the new authentication system.
            Rate limiting is handled by middleware.
            """
            # Authenticate user (supports external auth with user_id only)
            user_data = authenticate_user(user_id=user_id)
            
            if not user_data:
                # Create a basic token for backward compatibility
                # Note: This should be replaced with proper user creation
                payload = {
                    "sub": user_id,
                    "exp": datetime.utcnow() + timedelta(hours=config.auth.jwt_expiration_hours),
                    "iat": datetime.utcnow(),
                    "jti": str(uuid.uuid4()),
                    "type": "access"
                }
                token = jwt.encode(payload, config.auth.jwt_secret, algorithm=config.auth.jwt_algorithm)
            else:
                # Use new auth system
                token = create_access_token(
                    user_id=user_data["user_id"],
                    roles=user_data.get("roles", []),
                    permissions=user_data.get("permissions", [])
                )
            
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
            user: dict = Depends(get_current_user)
        ):
            """REST API chat endpoint.
            
            Rate limiting is handled by middleware.
            """
            user_id = user["user_id"]
            
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
            
            # Connect to Redis cache
            if self.cache_manager:
                connected = await self.cache_manager.connect()
                if connected:
                    logger.info("Connected to Redis cache")
                    health_checker.add_check("redis", self._check_redis_health)
                else:
                    logger.warning("Redis cache not available, continuing without cache")
            
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
    
    async def _check_redis_health(self) -> bool:
        """Check Redis cache health."""
        if not self.cache_manager:
            return False
        return self.cache_manager._is_available()
    
    async def disconnect_services(self):
        """Disconnect from external services."""
        if self.nats_client:
            await self.nats_client.close()
            logger.info("Disconnected from NATS")
        if self.cache_manager:
            await self.cache_manager.disconnect()
            logger.info("Disconnected from Redis cache")

# Global service instance
gateway_service = GatewayService()

# Startup and shutdown events
@gateway_service.app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Starting Gateway service...")
    # Initialize database connection pool
    from db_pool import get_db_pool
    get_db_pool()  # Initialize the pool
    # Initialize gRPC connection pool
    from grpc_pool import get_grpc_pool
    get_grpc_pool()  # Initialize the pool
    await gateway_service.connect_services()
    logger.info("Gateway service started successfully")

@gateway_service.app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Shutting down Gateway service...")
    await gateway_service.disconnect_services()
    # Close database connection pool
    from db_pool import close_db_pool
    close_db_pool()
    # Close gRPC connection pool
    from grpc_pool import shutdown_grpc_pool
    await shutdown_grpc_pool()
    logger.info("Gateway service shut down")

# Export the FastAPI app
app = gateway_service.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
        port=int(os.getenv("GATEWAY_PORT", "8000")),
        reload=False,
        log_level=config.monitoring.log_level.lower()
    )


