#!/usr/bin/env python3
"""
Minimal TTS Service for testing.
"""
import asyncio
import logging
import subprocess
import tempfile
import os
import numpy as np
import soundfile as sf

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleTTSService:
    """Simple TTS service using espeak."""
    
    def __init__(self):
        self.sample_rate = 16000
        
    async def synthesize_text(self, text: str) -> bytes:
        """Synthesize text to audio using espeak."""
        try:
            if not text.strip():
                return b""
            
            logger.info(f"Synthesizing text: {text[:50]}...")
            
            # Use espeak to generate speech
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Run espeak command
            cmd = [
                'espeak',
                '-s', str(self.sample_rate),
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
            
            # Convert to bytes
            audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
            
            logger.info(f"Generated {len(audio_bytes)} bytes of audio")
            return audio_bytes
                
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return b""

async def main():
    """Main function for testing."""
    logger.info("Starting Simple TTS Service...")
    
    # Test espeak availability
    try:
        result = subprocess.run(['espeak', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception("espeak not available")
        logger.info("espeak is available")
    except Exception as e:
        logger.error(f"espeak check failed: {e}")
        return
    
    # Create service
    tts_service = SimpleTTSService()
    
    # Test synthesis
    test_text = "Hello, this is a test of the text to speech system."
    audio_data = await tts_service.synthesize_text(test_text)
    
    if audio_data:
        logger.info("✅ TTS service test successful!")
        logger.info(f"Generated {len(audio_data)} bytes of audio")
    else:
        logger.error("❌ TTS service test failed")

if __name__ == "__main__":
    asyncio.run(main())




