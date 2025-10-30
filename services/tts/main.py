"""
TTS Service - Text-to-Speech with simple espeak implementation.
"""
import asyncio
import logging
import io
import base64
import numpy as np
import subprocess
import tempfile
import os
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
import uuid

import grpc
from grpc import aio
import nats
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import soundfile as sf

# Import generated protobuf classes
import sys
sys.path.append('./proto')
from tts_pb2 import (
    SynthesisRequest, SynthesisConfig, AudioChunk, AudioResponse,
    HealthRequest, HealthResponse
)
import tts_pb2_grpc

from inference_core import config, setup_logging, Timer, HealthChecker, CircularBuffer

# Setup logging
setup_logging(config.monitoring.log_level, "tts")
logger = logging.getLogger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('tts_requests_total', 'Total requests', ['method', 'status'])
REQUEST_DURATION = Histogram('tts_request_duration_seconds', 'Request duration')
AUDIO_GENERATION_TIME = Histogram('tts_audio_generation_seconds', 'Audio generation time')
MODEL_LOAD_TIME = Histogram('tts_model_load_seconds', 'Model loading time')
AUDIO_DURATION = Histogram('tts_audio_duration_seconds', 'Generated audio duration')

class TTSService(tts_pb2_grpc.TextToSpeechServicer):
    """Main TTS service class."""
    
    def __init__(self):
        self.tts_model = None
        self.nats_client = None
        self.health_checker = HealthChecker()
        self.audio_buffer = CircularBuffer(1000)
        self.device = config.tts.device
        self.sample_rate = config.tts.sample_rate
        
        # Add health checks
        self.health_checker.add_check("model", self._check_model_health)
        self.health_checker.add_check("nats", self._check_nats_health)
    
    async def SynthesizeStream(self, request_iterator: AsyncGenerator[SynthesisRequest, None], context: grpc.aio.ServicerContext) -> AsyncGenerator[AudioChunk, None]:
        """Streaming text-to-speech synthesis."""
        with Timer("synthesis_stream"):
            try:
                async for request in request_iterator:
                    # Generate audio for each request
                    audio_data = await self._synthesize_text(
                        request.text,
                        request.voice_id,
                        request.language,
                        request.config
                    )
                    
                    if audio_data is not None:
                        # Split audio into chunks for streaming
                        chunk_size = int(self.sample_rate * 0.1)  # 100ms chunks
                        
                        for i in range(0, len(audio_data), chunk_size):
                            chunk_data = audio_data[i:i + chunk_size]
                            
                            # Convert to bytes
                            audio_bytes = (chunk_data * 32767).astype(np.int16).tobytes()
                            
                            chunk = AudioChunk(
                                audio_data=audio_bytes,
                                sample_rate=self.sample_rate,
                                channels=1,
                                encoding="pcm16",
                                is_final=(i + chunk_size >= len(audio_data)),
                                timestamp_us=int(i / self.sample_rate * 1_000_000)
                            )
                            
                            yield chunk
                            
                            # Small delay to simulate streaming
                            await asyncio.sleep(0.01)
                    
            except Exception as e:
                logger.error(f"Synthesis stream error: {e}")
                error_chunk = AudioChunk(
                    audio_data=b"",
                    sample_rate=self.sample_rate,
                    channels=1,
                    encoding="pcm16",
                    is_final=True,
                    timestamp_us=0
                )
                yield error_chunk
    
    async def Synthesize(self, request: SynthesisRequest, context: grpc.aio.ServicerContext) -> AudioResponse:
        """One-shot text-to-speech synthesis."""
        with Timer("synthesis"):
            try:
                # Generate audio
                audio_data = await self._synthesize_text(
                    request.text,
                    request.voice_id,
                    request.language,
                    request.config
                )
                
                if audio_data is not None:
                    # Convert to bytes
                    audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
                    duration_ms = int(len(audio_data) / self.sample_rate * 1000)
                    
                    return AudioResponse(
                        audio_data=audio_bytes,
                        sample_rate=self.sample_rate,
                        encoding="pcm16",
                        duration_ms=duration_ms
                    )
                else:
                    return AudioResponse(
                        audio_data=b"",
                        sample_rate=self.sample_rate,
                        encoding="pcm16",
                        duration_ms=0
                    )
                    
            except Exception as e:
                logger.error(f"Synthesis error: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return AudioResponse()
    
    async def HealthCheck(self, request: HealthRequest, context: grpc.aio.ServicerContext) -> HealthResponse:
        """Health check endpoint."""
        health_status = await self.health_checker.check_all()
        is_healthy = all(health_status.values())
        
        return HealthResponse(
            healthy=is_healthy,
            version="0.2.0",
            available_voices=["default", "female", "male"]  # TODO: Get from model
        )
    
    async def _synthesize_text(self, text: str, voice_id: str, language: str, config: SynthesisConfig) -> Optional[np.ndarray]:
        """Synthesize text to audio using espeak."""
        try:
            if not text.strip():
                return None
            
            with Timer("audio_generation"):
                # Use espeak to generate audio
                audio_data = await self._espeak_synthesis(text, voice_id, language, config)
                
                # Ensure audio is in the right format
                if audio_data is not None and len(audio_data.shape) > 1:
                    audio_data = audio_data.flatten()
                
                # Normalize audio
                if audio_data is not None and np.max(np.abs(audio_data)) > 0:
                    audio_data = audio_data / np.max(np.abs(audio_data))
                
                # Record metrics
                duration = len(audio_data) / self.sample_rate
                AUDIO_DURATION.observe(duration)
                
                return audio_data
                
        except Exception as e:
            logger.error(f"Text synthesis error: {e}")
            return None
    
    async def _espeak_synthesis(self, text: str, voice_id: str, language: str, config: SynthesisConfig) -> np.ndarray:
        """Synthesize text using espeak."""
        try:
            # Use espeak to generate speech
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Run espeak command
            cmd = [
                'espeak',
                '-s', str(config.sample_rate),
                '-w', temp_path,
                text
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"espeak failed: {result.stderr}")
            
            # Read the generated audio file
            audio_data, sample_rate = sf.read(temp_path)
            
            # Clean up temp file
            os.unlink(temp_path)
            
            # Resample if needed
            if sample_rate != config.sample_rate:
                # Simple resampling (for now, just truncate/pad)
                target_samples = int(len(audio_data) * config.sample_rate / sample_rate)
                if len(audio_data) > target_samples:
                    audio_data = audio_data[:target_samples]
                else:
                    audio_data = np.pad(audio_data, (0, target_samples - len(audio_data)))
            
            return audio_data.astype(np.float32)
                
        except Exception as e:
            logger.error(f"espeak synthesis failed: {e}")
            # Fallback to basic synthesis
            return await self._basic_synthesis(text, voice_id, language, config)
    
    async def _basic_synthesis(self, text: str, voice_id: str, language: str, config: SynthesisConfig) -> np.ndarray:
        """Basic synthesis fallback (generates silence with configurable duration)."""
        # Calculate duration based on text length (rough estimate)
        words_per_second = 2.5
        word_count = len(text.split())
        duration = word_count / words_per_second
        
        # Apply speed factor
        if config.speed > 0:
            duration = duration / config.speed
        
        # Generate silence (placeholder)
        samples = int(duration * self.sample_rate)
        audio_data = np.zeros(samples, dtype=np.float32)
        
        # Add some basic prosody variation
        if config.pitch != 0:
            # Simple pitch variation simulation
            t = np.linspace(0, duration, samples)
            pitch_variation = np.sin(2 * np.pi * 0.5 * t) * config.pitch * 0.1
            audio_data += pitch_variation
        
        return audio_data
    
    async def _load_models(self):
        """Load TTS model (espeak-based)."""
        with Timer("model_loading"):
            logger.info("Initializing espeak-based TTS")
            
            try:
                # Test espeak availability
                result = subprocess.run(['espeak', '--version'], capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception("espeak not available")
                
                logger.info("espeak TTS initialized successfully")
                self.tts_model = "espeak"  # Mark as available
                
            except Exception as e:
                logger.warning(f"Failed to initialize espeak: {e}")
                logger.info("Using basic synthesis fallback")
                self.tts_model = None
    
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
        """Check if TTS model is loaded and ready."""
        return self.tts_model is not None
    
    async def _check_nats_health(self) -> bool:
        """Check NATS connection health."""
        return self.nats_client is not None and self.nats_client.is_connected
    
    async def disconnect_services(self):
        """Disconnect from external services."""
        if self.nats_client:
            await self.nats_client.close()

# Global service instance
tts_service = TTSService()

async def serve():
    """Start the gRPC server."""
    server = aio.server()
    
    # Add the service to the server
    tts_pb2_grpc.add_TextToSpeechServicer_to_server(tts_service, server)
    
    # Start server
    listen_addr = '[::]:50053'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting TTS server on {listen_addr}")
    
    # Load models and connect to services
    await tts_service._load_models()
    await tts_service._connect_services()
    
    # Start serving
    await server.start()
    logger.info("TTS server started")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down TTS server...")
        await tts_service.disconnect_services()
        await server.stop(grace=5.0)

if __name__ == "__main__":
    asyncio.run(serve())


