"""
STT Service - Speech-to-Text with Whisper, VAD, and gRPC streaming.
"""
import asyncio
import logging
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
from prometheus_client import Counter, Histogram, Gauge, generate_latest
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

from shared import config, setup_logging, Timer, HealthChecker, CircularBuffer

# Setup logging
setup_logging(config.monitoring.log_level, "stt")
logger = logging.getLogger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('stt_requests_total', 'Total requests', ['method', 'status'])
REQUEST_DURATION = Histogram('stt_request_duration_seconds', 'Request duration')
AUDIO_PROCESSING_TIME = Histogram('stt_audio_processing_seconds', 'Audio processing time')
VAD_DETECTIONS = Counter('stt_vad_detections_total', 'VAD detections', ['action'])
MODEL_LOAD_TIME = Histogram('stt_model_load_seconds', 'Model loading time')

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
        with Timer("recognition_stream"):
            try:
                audio_buffer = []
                session_id = str(uuid.uuid4())
                
                async for chunk in request_iterator:
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
                            yield interim_result
                            audio_buffer = []  # Clear buffer after interim result
                
                # Final transcription
                if audio_buffer:
                    final_result = await self._transcribe_audio(audio_buffer, is_final=True)
                    if final_result:
                        yield final_result
                
            except Exception as e:
                logger.error(f"Recognition stream error: {e}")
                error_result = RecognitionResult(
                    transcript="",
                    is_final=True,
                    confidence=0.0,
                    start_time_us=0,
                    end_time_us=0
                )
                yield error_result
    
    async def Recognize(self, request: RecognitionRequest, context: grpc.aio.ServicerContext) -> RecognitionResponse:
        """One-shot speech recognition."""
        with Timer("recognition"):
            try:
                # Process audio data
                audio_data = await self._process_audio_data(request.audio_data, request.sample_rate)
                
                # Transcribe
                result = await self._transcribe_audio(audio_data, is_final=True)
                
                if result:
                    return RecognitionResponse(
                        results=[result],
                        processing_time_ms=int(Timer("recognition").duration * 1000) if Timer("recognition").duration else 0
                    )
                else:
                    return RecognitionResponse(
                        results=[],
                        processing_time_ms=0
                    )
                    
            except Exception as e:
                logger.error(f"Recognition error: {e}")
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
    
    async def _transcribe_audio(self, audio_data: List[float], is_final: bool = True) -> Optional[RecognitionResult]:
        """Transcribe audio using Whisper."""
        try:
            if not audio_data or len(audio_data) < self.sample_rate * 0.1:  # Less than 100ms
                return None
            
            # Convert to numpy array
            audio_array = np.array(audio_data, dtype=np.float32)
            
            # Ensure audio is in the right format for Whisper
            if len(audio_array.shape) == 1:
                audio_array = audio_array.reshape(1, -1)
            
            # Transcribe with Whisper
            with Timer("whisper_transcription"):
                result = self.whisper_model.transcribe(
                    audio_array,
                    language="en",  # TODO: Make configurable
                    fp16=torch.cuda.is_available()
                )
            
            # Extract transcription details
            transcript = result["text"].strip()
            if not transcript:
                return None
            
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
                speaker_id=""  # TODO: Implement speaker diarization
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
    """Start the gRPC server."""
    server = aio.server()
    
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


