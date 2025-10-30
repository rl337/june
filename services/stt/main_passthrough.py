#!/usr/bin/env python3
"""
Pass-through STT Service - Simple speech-to-text that returns mock transcriptions.
"""
import asyncio
import logging
import json
import base64
import numpy as np
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
import uuid

import grpc
from grpc import aio
import nats
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Import generated protobuf classes
import sys
sys.path.append('./proto')
from asr_pb2 import (
    RecognitionRequest, RecognitionConfig, RecognitionResult, RecognitionResponse,
    HealthRequest, HealthResponse
)
import asr_pb2_grpc

from inference_core import config, setup_logging, Timer, HealthChecker, CircularBuffer

# Setup logging
setup_logging(config.monitoring.log_level, "stt")
logger = logging.getLogger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('stt_requests_total', 'Total requests', ['method', 'status'])
REQUEST_DURATION = Histogram('stt_request_duration_seconds', 'Request duration')
AUDIO_PROCESSING_TIME = Histogram('stt_audio_processing_seconds', 'Audio processing time')
MODEL_LOAD_TIME = Histogram('stt_model_load_seconds', 'Model loading time')
AUDIO_DURATION = Histogram('stt_audio_duration_seconds', 'Input audio duration')

class PassThroughSTTService(asr_pb2_grpc.SpeechRecognitionServicer):
    """Pass-through STT service that returns mock transcriptions."""
    
    def __init__(self):
        self.nats_client = None
        self.health_checker = HealthChecker()
        self.audio_buffer = CircularBuffer(1000)
        
        # Add health checks
        self.health_checker.add_check("nats", self._check_nats_health)
    
    async def RecognizeStream(self, request_iterator: AsyncGenerator[RecognitionRequest, None], context: grpc.aio.ServicerContext) -> AsyncGenerator[RecognitionResult, None]:
        """Streaming speech recognition - pass-through implementation."""
        with Timer("recognition_stream"):
            try:
                audio_chunks = []
                total_audio_duration = 0.0
                
                async for request in request_iterator:
                    # Collect audio chunks
                    if request.audio_data:
                        audio_chunks.append(request.audio_data)
                        # Estimate duration (assuming 16kHz, 16-bit PCM)
                        chunk_duration = len(request.audio_data) / (16000 * 2)  # 2 bytes per sample
                        total_audio_duration += chunk_duration
                    
                    # Send interim results
                    interim_result = RecognitionResult(
                        transcript="Processing audio...",
                        confidence=0.5,
                        is_final=False,
                        timestamp_us=int(total_audio_duration * 1_000_000)
                    )
                    yield interim_result
                
                # Generate final result based on audio duration
                final_transcript = self._generate_mock_transcript(total_audio_duration)
                
                final_result = RecognitionResult(
                    transcript=final_transcript,
                    confidence=0.95,
                    is_final=True,
                    timestamp_us=int(total_audio_duration * 1_000_000)
                )
                
                # Record metrics
                AUDIO_DURATION.observe(total_audio_duration)
                REQUEST_COUNT.labels(method='stream', status='success').inc()
                
                yield final_result
                
            except Exception as e:
                logger.error(f"Recognition stream error: {e}")
                REQUEST_COUNT.labels(method='stream', status='error').inc()
                error_result = RecognitionResult(
                    transcript="",
                    confidence=0.0,
                    is_final=True,
                    timestamp_us=0
                )
                yield error_result
    
    async def Recognize(self, request: RecognitionRequest, context: grpc.aio.ServicerContext) -> RecognitionResponse:
        """One-shot speech recognition - pass-through implementation."""
        with Timer("recognition"):
            try:
                # Calculate audio duration
                audio_duration = len(request.audio_data) / (16000 * 2)  # 16kHz, 16-bit PCM
                
                # Generate mock transcript based on audio duration
                transcript = self._generate_mock_transcript(audio_duration)
                
                # Record metrics
                AUDIO_DURATION.observe(audio_duration)
                REQUEST_COUNT.labels(method='oneshot', status='success').inc()
                
                return RecognitionResponse(
                    results=[RecognitionResult(
                        transcript=transcript,
                        confidence=0.95,
                        is_final=True,
                        timestamp_us=int(audio_duration * 1_000_000)
                    )]
                )
                
            except Exception as e:
                logger.error(f"Recognition error: {e}")
                REQUEST_COUNT.labels(method='oneshot', status='error').inc()
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return RecognitionResponse()
    
    async def HealthCheck(self, request: HealthRequest, context: grpc.aio.ServicerContext) -> HealthResponse:
        """Health check endpoint."""
        health_status = await self.health_checker.check_all()
        is_healthy = all(health_status.values())
        
        return HealthResponse(
            healthy=is_healthy,
            version="0.2.0",
            available_languages=["en", "es", "fr", "de"]  # Mock languages
        )
    
    def _generate_mock_transcript(self, audio_duration: float) -> str:
        """Generate a mock transcript based on audio duration."""
        # Simple mock transcriptions based on duration
        if audio_duration < 1.0:
            return "Hello"
        elif audio_duration < 2.0:
            return "Hello world"
        elif audio_duration < 3.0:
            return "This is a test"
        elif audio_duration < 4.0:
            return "Testing speech recognition"
        elif audio_duration < 5.0:
            return "This is a longer test message"
        else:
            return "This is a very long test message for speech recognition testing"
    
    async def _connect_services(self):
        """Connect to external services."""
        try:
            # Connect to NATS
            self.nats_client = await nats.connect(config.nats.url)
            logger.info("Connected to NATS")
            
        except Exception as e:
            logger.error(f"Failed to connect to services: {e}")
            raise
    
    async def _check_nats_health(self) -> bool:
        """Check NATS connection health."""
        return self.nats_client is not None and self.nats_client.is_connected
    
    async def disconnect_services(self):
        """Disconnect from external services."""
        if self.nats_client:
            await self.nats_client.close()

# Global service instance
stt_service = PassThroughSTTService()

async def serve():
    """Start the gRPC server."""
    server = aio.server()
    
    # Add the service to the server
    asr_pb2_grpc.add_SpeechRecognitionServicer_to_server(stt_service, server)
    
    # Start server
    listen_addr = '[::]:50052'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting STT server on {listen_addr}")
    
    # Connect to services
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





