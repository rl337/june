#!/usr/bin/env python3
"""
Minimal STT Service - Standalone pass-through implementation.
"""
import asyncio
import logging
import json
import base64
import numpy as np
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
import uuid
import os

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MinimalSTTService:
    """Minimal STT service that returns mock transcriptions."""
    
    def __init__(self):
        self.sample_rate = 16000
        
    async def recognize_audio(self, audio_data: bytes) -> str:
        """Recognize audio and return mock transcript."""
        try:
            # Calculate audio duration
            audio_duration = len(audio_data) / (self.sample_rate * 2)  # 16kHz, 16-bit PCM
            
            # Generate mock transcript based on audio duration
            transcript = self._generate_mock_transcript(audio_duration)
            
            logger.info(f"Recognized audio ({audio_duration:.2f}s): '{transcript}'")
            return transcript
            
        except Exception as e:
            logger.error(f"Recognition error: {e}")
            return "Recognition failed"
    
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

async def main():
    """Main function for testing."""
    logger.info("Starting Minimal STT Service...")
    
    # Create service
    stt_service = MinimalSTTService()
    
    # Test recognition with synthetic audio
    test_durations = [0.5, 1.5, 2.5, 3.5, 4.5]
    
    for duration in test_durations:
        # Generate synthetic audio data
        samples = int(duration * stt_service.sample_rate)
        audio_data = np.random.randint(-32768, 32767, samples, dtype=np.int16).tobytes()
        
        # Test recognition
        transcript = await stt_service.recognize_audio(audio_data)
        logger.info(f"✅ Duration {duration}s -> '{transcript}'")
    
    logger.info("✅ Minimal STT service test completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())




