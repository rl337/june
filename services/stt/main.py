"""
STT Service - Speech-to-Text with Whisper, VAD, and gRPC streaming.
"""
import asyncio
import logging
import os
import io
import base64
import numpy as np
import torch
import torchaudio
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
import uuid

import grpc
from grpc import aio
import nats
import whisper
import webrtcvad
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
from prometheus_client.exposition import start_http_server
import librosa
import soundfile as sf

# Import generated protobuf classes
import sys
sys.path.append('../../proto')
from asr_pb2 import (
    AudioChunk, RecognitionRequest, RecognitionResponse, RecognitionResult,
    RecognitionConfig, WordInfo, HealthRequest, HealthResponse
)
import asr_pb2_grpc

from inference_core import config, setup_logging, Timer, HealthChecker, CircularBuffer

# Initialize tracing early
tracer = None
try:
    import sys
    from pathlib import Path
    # Add essence package to path for tracing import
    essence_path = Path(__file__).parent.parent.parent / "essence"
    if str(essence_path) not in sys.path:
        sys.path.insert(0, str(essence_path))
    from essence.chat.utils.tracing import setup_tracing, get_tracer
    from opentelemetry import trace
    setup_tracing(service_name="june-stt")
    tracer = get_tracer(__name__)
except ImportError:
    pass

# Import rate limiting
try:
    from june_rate_limit import RateLimitInterceptor, RateLimitConfig
    RATE_LIMIT_AVAILABLE = True
except ImportError:
    RATE_LIMIT_AVAILABLE = False
    RateLimitInterceptor = None
    RateLimitConfig = None

# Import input validation
try:
    from june_security import get_input_validator, InputValidationError
    input_validator = get_input_validator()
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False
    input_validator = None

# Import metrics storage
try:
    from stt_metrics import get_metrics_storage
except ImportError:
    # Fallback for different import paths
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from stt_metrics import get_metrics_storage

# Setup logging
setup_logging(config.monitoring.log_level, "stt")
logger = logging.getLogger(__name__)

# Prometheus metrics
REGISTRY = CollectorRegistry()
REQUEST_COUNT = Counter('stt_requests_total', 'Total requests', ['method', 'status'], registry=REGISTRY)
REQUEST_DURATION = Histogram('stt_request_duration_seconds', 'Request duration', registry=REGISTRY)
AUDIO_PROCESSING_TIME = Histogram('stt_audio_processing_seconds', 'Audio processing time', registry=REGISTRY)
VAD_DETECTIONS = Counter('stt_vad_detections_total', 'VAD detections', ['action'], registry=REGISTRY)
MODEL_LOAD_TIME = Histogram('stt_model_load_seconds', 'Model loading time', registry=REGISTRY)
TRANSCRIPTION_TIME = Histogram('stt_transcription_time_seconds', 'Transcription time', registry=REGISTRY)
ACTIVE_CONNECTIONS = Gauge('stt_active_connections', 'Active gRPC connections', registry=REGISTRY)
ERROR_COUNT = Counter('stt_errors_total', 'Total errors', ['error_type'], registry=REGISTRY)

class STTService(asr_pb2_grpc.SpeechToTextServicer):
    """Main STT service class."""
    
    def __init__(self):
        self.whisper_model = None
        self.vad = None
        self.nats_client = None
        self.health_checker = HealthChecker()
        self.audio_buffer = CircularBuffer(1000)
        self.device = config.stt.device
        self.sample_rate = config.stt.sample_rate
        
        # Add health checks
        self.health_checker.add_check("model", self._check_model_health)
        self.health_checker.add_check("nats", self._check_nats_health)
    
    async def RecognizeStream(self, request_iterator: AsyncGenerator[AudioChunk, None], context: grpc.aio.ServicerContext) -> AsyncGenerator[RecognitionResult, None]:
        """Streaming speech recognition."""
        span = None
        if tracer is not None:
            span = tracer.start_span("stt.recognize_stream")
            span.set_attribute("stt.method", "stream")
        
        try:
            with Timer("recognition_stream"):
                audio_buffer = []
                session_id = str(uuid.uuid4())
                chunk_count = 0
                total_audio_size = 0
                
                if span:
                    span.set_attribute("stt.session_id", session_id)
                
                async for chunk in request_iterator:
                    chunk_count += 1
                    total_audio_size += len(chunk.audio_data)
                    
                    # Process audio chunk
                    audio_data = await self._process_audio_chunk(chunk)
                    audio_buffer.extend(audio_data)
                    
                    # Check for voice activity if VAD is enabled
                    if config.stt.enable_vad and len(audio_buffer) > 0:
                        vad_result = await self._detect_voice_activity(audio_buffer)
                        if vad_result:
                            VAD_DETECTIONS.labels(action="detected").inc()
                        else:
                            VAD_DETECTIONS.labels(action="silence").inc()
                    
                    # Send interim results for long audio
                    if len(audio_buffer) > self.sample_rate * 5:  # 5 seconds
                        interim_result = await self._transcribe_audio(audio_buffer, is_final=False)
                        if interim_result:
                            if span:
                                span.set_attribute("stt.interim_transcript_length", len(interim_result.transcript))
                            yield interim_result
                            audio_buffer = []  # Clear buffer after interim result
                
                # Final transcription
                if audio_buffer:
                    final_result = await self._transcribe_audio(audio_buffer, is_final=True)
                    if final_result:
                        if span:
                            span.set_attribute("stt.transcript_length", len(final_result.transcript))
                            span.set_attribute("stt.confidence", final_result.confidence)
                            span.set_attribute("stt.detected_language", final_result.detected_language or "unknown")
                            span.set_attribute("stt.chunk_count", chunk_count)
                            span.set_attribute("stt.total_audio_size_bytes", total_audio_size)
                        yield final_result
                    elif span:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, "Empty transcription result"))
                
                if span:
                    span.set_status(trace.Status(trace.StatusCode.OK))
                
        except Exception as e:
            logger.error(f"Recognition stream error: {e}")
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
            error_result = RecognitionResult(
                transcript="",
                is_final=True,
                confidence=0.0,
                start_time_us=0,
                end_time_us=0
            )
            yield error_result
        finally:
            if span:
                span.end()
    
    async def Recognize(self, request: RecognitionRequest, context: grpc.aio.ServicerContext) -> RecognitionResponse:
        """One-shot speech recognition."""
        span = None
        if tracer is not None:
            span = tracer.start_span("stt.recognize")
            span.set_attribute("stt.method", "oneshot")
            span.set_attribute("stt.sample_rate", request.sample_rate)
            span.set_attribute("stt.audio_size_bytes", len(request.audio_data))
            if request.encoding:
                span.set_attribute("stt.encoding", request.encoding)
            if request.config and hasattr(request.config, "language") and request.config.language:
                span.set_attribute("stt.language", request.config.language)
        
        try:
            with Timer("recognition"):
                start_time = datetime.now()
                
                # Validate audio data
                if VALIDATION_AVAILABLE and input_validator:
                    try:
                        # Validate audio data size
                        if len(request.audio_data) > input_validator.MAX_AUDIO_FILE_SIZE:
                            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                            context.set_details(f"Audio file size ({len(request.audio_data)} bytes) exceeds maximum allowed size ({input_validator.MAX_AUDIO_FILE_SIZE} bytes)")
                            return RecognitionResponse()
                        
                        # Validate sample rate
                        if request.sample_rate <= 0 or request.sample_rate > 48000:
                            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                            context.set_details(f"Invalid sample rate: {request.sample_rate}. Must be between 1 and 48000")
                            return RecognitionResponse()
                        
                        # Validate encoding if provided
                        if request.encoding:
                            allowed_encodings = ['pcm', 'wav', 'ogg', 'flac', 'mp3']
                            try:
                                validated_encoding = input_validator.validate_enum(
                                    request.encoding,
                                    allowed_encodings,
                                    field_name="encoding",
                                    case_sensitive=False
                                )
                                request.encoding = validated_encoding
                            except InputValidationError as e:
                                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                                context.set_details(f"Invalid encoding: {str(e)}")
                                return RecognitionResponse()
                    except Exception as e:
                        logger.error(f"Input validation error: {e}")
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details(f"Input validation failed: {str(e)}")
                        return RecognitionResponse()
            
            audio_format = request.encoding if request.encoding else "pcm"
            audio_size = len(request.audio_data)
            audio_duration = 0.0
            transcript_length = 0
            confidence = 0.0
            error_message = None
            
            try:
                # Process audio data
                audio_data = await self._process_audio_data(request.audio_data, request.sample_rate)
                
                # Calculate audio duration
                audio_duration = len(audio_data) / request.sample_rate if request.sample_rate > 0 else 0.0
                
                # Extract language from config (if provided)
                language = None
                if request.config and hasattr(request.config, "language") and request.config.language:
                    language = request.config.language
                    # Use None for auto-detection if language is empty string
                    if language.strip() == "":
                        language = None
                
                # Transcribe with language (None = auto-detect)
                result = await self._transcribe_audio(audio_data, is_final=True, language=language)
                
                processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                if result:
                    transcript_length = len(result.transcript)
                    confidence = result.confidence
                    
                    # Update tracing span with results
                    if span:
                        span.set_attribute("stt.transcript_length", transcript_length)
                        span.set_attribute("stt.confidence", confidence)
                        span.set_attribute("stt.detected_language", result.detected_language or "unknown")
                        span.set_attribute("stt.audio_duration_seconds", audio_duration)
                        span.set_attribute("stt.processing_time_ms", processing_time_ms)
                        span.set_status(trace.Status(trace.StatusCode.OK))
                    
                    # Record metrics
                    try:
                        metrics = get_metrics_storage()
                        metrics.record_transcription(
                            audio_format=audio_format,
                            audio_duration_seconds=audio_duration,
                            audio_size_bytes=audio_size,
                            sample_rate=request.sample_rate,
                            transcript_length=transcript_length,
                            confidence=confidence,
                            processing_time_ms=processing_time_ms,
                            source="stt_service"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record metrics: {e}")
                    
                    return RecognitionResponse(
                        results=[result],
                        processing_time_ms=processing_time_ms
                    )
                else:
                    # Update tracing span for empty result
                    if span:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, "Empty transcription result"))
                    
                    # Record failed transcription
                    try:
                        metrics = get_metrics_storage()
                        metrics.record_transcription(
                            audio_format=audio_format,
                            audio_duration_seconds=audio_duration,
                            audio_size_bytes=audio_size,
                            sample_rate=request.sample_rate,
                            transcript_length=0,
                            confidence=0.0,
                            processing_time_ms=processing_time_ms,
                            source="stt_service",
                            error_message="Empty transcription result"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record metrics: {e}")
                    
                    return RecognitionResponse(
                        results=[],
                        processing_time_ms=processing_time_ms
                    )
                    
            except Exception as e:
                error_message = str(e)
                logger.error(f"Recognition error: {e}")
                
                # Update tracing span for error
                if span:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, error_message))
                    span.record_exception(e)
                
                # Record error metrics
                try:
                    processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                    metrics = get_metrics_storage()
                    metrics.record_transcription(
                        audio_format=audio_format,
                        audio_duration_seconds=audio_duration,
                        audio_size_bytes=audio_size,
                        sample_rate=request.sample_rate if hasattr(request, "sample_rate") else 16000,
                        transcript_length=0,
                        confidence=0.0,
                        processing_time_ms=processing_time_ms,
                        source="stt_service",
                        error_message=error_message
                    )
                except Exception as metrics_error:
                    logger.warning(f"Failed to record error metrics: {metrics_error}")
                
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return RecognitionResponse()
            finally:
                if span:
                    span.end()
    
    async def HealthCheck(self, request: HealthRequest, context: grpc.aio.ServicerContext) -> HealthResponse:
        """Health check endpoint."""
        health_status = await self.health_checker.check_all()
        is_healthy = all(health_status.values())
        
        return HealthResponse(
            healthy=is_healthy,
            version="0.2.0",
            model_name=config.stt.model_name
        )
    
    async def _process_audio_chunk(self, chunk: AudioChunk) -> List[float]:
        """Process incoming audio chunk."""
        try:
            # Decode audio data
            if chunk.encoding == "pcm":
                audio_data = np.frombuffer(chunk.audio_data, dtype=np.int16)
                # Convert to float32 and normalize
                audio_data = audio_data.astype(np.float32) / 32768.0
            elif chunk.encoding == "opus":
                # TODO: Implement Opus decoding
                audio_data = np.frombuffer(chunk.audio_data, dtype=np.float32)
            else:
                # Assume raw float32 data
                audio_data = np.frombuffer(chunk.audio_data, dtype=np.float32)
            
            # Resample if necessary
            if chunk.sample_rate != self.sample_rate:
                audio_data = await self._resample_audio(audio_data, chunk.sample_rate, self.sample_rate)
            
            return audio_data.tolist()
            
        except Exception as e:
            logger.error(f"Audio chunk processing error: {e}")
            return []
    
    async def _process_audio_data(self, audio_data: bytes, sample_rate: int) -> List[float]:
        """Process audio data for one-shot recognition."""
        try:
            # Decode audio data
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_array = audio_array.astype(np.float32) / 32768.0
            
            # Resample if necessary
            if sample_rate != self.sample_rate:
                audio_array = await self._resample_audio(audio_array, sample_rate, self.sample_rate)
            
            return audio_array.tolist()
            
        except Exception as e:
            logger.error(f"Audio data processing error: {e}")
            return []
    
    async def _resample_audio(self, audio_data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Resample audio data."""
        try:
            if orig_sr == target_sr:
                return audio_data
            
            # Use librosa for resampling
            resampled = librosa.resample(audio_data, orig_sr=orig_sr, target_sr=target_sr)
            return resampled
            
        except Exception as e:
            logger.error(f"Audio resampling error: {e}")
            return audio_data
    
    async def _transcribe_audio(self, audio_data: List[float], is_final: bool = True, language: Optional[str] = None) -> Optional[RecognitionResult]:
        """
        Transcribe audio using Whisper.
        
        Args:
            audio_data: Audio data as list of floats
            is_final: Whether this is the final chunk
            language: Language code (ISO 639-1) or None for auto-detection
            
        Returns:
            RecognitionResult or None if transcription fails
        """
        try:
            if not audio_data or len(audio_data) < self.sample_rate * 0.1:  # Less than 100ms
                return None
            
            # Convert to numpy array
            audio_array = np.array(audio_data, dtype=np.float32)
            
            # Ensure audio is in the right format for Whisper
            if len(audio_array.shape) == 1:
                audio_array = audio_array.reshape(1, -1)
            
            # Transcribe with Whisper
            # If language is None, Whisper will auto-detect the language
            with Timer("whisper_transcription"):
                transcribe_kwargs = {
                    "fp16": torch.cuda.is_available()
                }
                if language:
                    transcribe_kwargs["language"] = language
                # If language is None, don't pass it - Whisper will auto-detect
                
                result = self.whisper_model.transcribe(audio_array, **transcribe_kwargs)
            
            # Extract transcription details
            transcript = result["text"].strip()
            if not transcript:
                return None
            
            # Extract detected language from Whisper result
            # Whisper always returns the language code in result["language"], even when auto-detecting
            detected_language = result.get("language", None)
            # If language was explicitly provided, use it; otherwise use detected language
            if language:
                # Language was explicitly provided, so detected_language should match
                detected_language = language
            # If language was None (auto-detect), detected_language will be the auto-detected language
            
            # Calculate confidence (Whisper doesn't provide per-word confidence)
            confidence = 0.9  # Default confidence for Whisper
            
            # Extract word-level information if available
            words = []
            if "segments" in result:
                for segment in result["segments"]:
                    if "words" in segment:
                        for word_info in segment["words"]:
                            word = WordInfo(
                                word=word_info["word"],
                                confidence=word_info.get("probability", confidence),
                                start_time_us=int(word_info["start"] * 1_000_000),
                                end_time_us=int(word_info["end"] * 1_000_000)
                            )
                            words.append(word)
            
            # Calculate timing
            start_time_us = int(result["segments"][0]["start"] * 1_000_000) if result["segments"] else 0
            end_time_us = int(result["segments"][-1]["end"] * 1_000_000) if result["segments"] else len(audio_array) / self.sample_rate * 1_000_000
            
            return RecognitionResult(
                transcript=transcript,
                is_final=is_final,
                confidence=confidence,
                words=words,
                start_time_us=start_time_us,
                end_time_us=end_time_us,
                speaker_id="",  # TODO: Implement speaker diarization
                detected_language=detected_language or ""  # ISO 639-1 code of detected language
            )
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None
    
    async def _detect_voice_activity(self, audio_data: List[float]) -> bool:
        """Detect voice activity using WebRTC VAD."""
        try:
            if not self.vad or len(audio_data) < self.sample_rate * 0.02:  # Less than 20ms
                return False
            
            # Convert to 16-bit PCM for VAD
            audio_array = np.array(audio_data, dtype=np.float32)
            audio_16bit = (audio_array * 32767).astype(np.int16)
            
            # Process in 20ms chunks
            chunk_size = int(self.sample_rate * 0.02)  # 20ms
            vad_results = []
            
            for i in range(0, len(audio_16bit), chunk_size):
                chunk = audio_16bit[i:i + chunk_size]
                if len(chunk) == chunk_size:
                    is_speech = self.vad.is_speech(chunk.tobytes(), self.sample_rate)
                    vad_results.append(is_speech)
            
            # Return True if majority of chunks contain speech
            return sum(vad_results) > len(vad_results) / 2
            
        except Exception as e:
            logger.error(f"VAD error: {e}")
            return False
    
    async def _load_models(self):
        """Load Whisper model and initialize VAD."""
        with Timer("model_loading"):
            logger.info(f"Loading Whisper model: {config.stt.model_name}")
            
            # Load Whisper model
            self.whisper_model = whisper.load_model(
                config.stt.model_name,
                device=self.device
            )
            
            # Initialize VAD if enabled
            if config.stt.enable_vad:
                self.vad = webrtcvad.Vad(2)  # Aggressiveness level 2 (0-3)
                logger.info("VAD initialized")
            
            logger.info("STT models loaded successfully")
    
    async def _connect_services(self):
        """Connect to external services."""
        try:
            # Connect to NATS
            self.nats_client = await nats.connect(config.nats.url)
            logger.info("Connected to NATS")
            
        except Exception as e:
            logger.error(f"Failed to connect to services: {e}")
            raise
    
    async def _check_model_health(self) -> bool:
        """Check if Whisper model is loaded and ready."""
        return self.whisper_model is not None
    
    async def _check_nats_health(self) -> bool:
        """Check NATS connection health."""
        return self.nats_client is not None and self.nats_client.is_connected
    
    async def disconnect_services(self):
        """Disconnect from external services."""
        if self.nats_client:
            await self.nats_client.close()

# Global service instance
stt_service = STTService()

async def serve():
    """Start the gRPC server and HTTP metrics server."""
    # Start HTTP server for Prometheus metrics
    metrics_port = int(os.getenv("STT_METRICS_PORT", "8002"))
    try:
        start_http_server(metrics_port, registry=REGISTRY)
        logger.info(f"Started Prometheus metrics server on port {metrics_port}")
    except Exception as e:
        logger.warning(f"Failed to start metrics server on port {metrics_port}: {e}")
    
    interceptors = []
    
    # Add rate limiting interceptor if available
    if RATE_LIMIT_AVAILABLE:
        rate_limit_config = RateLimitConfig(
            default_per_minute=int(os.getenv("RATE_LIMIT_STT_PER_MINUTE", "60")),
            default_per_hour=int(os.getenv("RATE_LIMIT_STT_PER_HOUR", "1000")),
            use_redis=False,  # Use in-memory rate limiting for MVP (Redis not required)
            fallback_to_memory=True,
        )
        rate_limit_interceptor = RateLimitInterceptor(config=rate_limit_config)
        interceptors.append(rate_limit_interceptor)
        logger.info("Rate limiting enabled for STT service (in-memory, Redis not required)")
    
    server = aio.server(interceptors=interceptors if interceptors else None)
    
    # Add the service to the server
    asr_pb2_grpc.add_SpeechToTextServicer_to_server(stt_service, server)
    
    # Start server
    listen_addr = '[::]:50052'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting STT server on {listen_addr}")
    
    # Load models and connect to services
    await stt_service._load_models()
    await stt_service._connect_services()
    
    # Start serving
    await server.start()
    logger.info("STT server started")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down STT server...")
        await stt_service.disconnect_services()
        await server.stop(grace=5.0)

if __name__ == "__main__":
    asyncio.run(serve())







