#!/usr/bin/env python3
"""
End-to-End Text Passthrough Test

⚠️ **OBSOLETE:** This test is obsolete because it depends on the gateway service,
which has been removed as part of the refactoring. The gateway service was
removed to achieve a minimal architecture with direct gRPC communication between
services.

**Original Purpose:**
Tests the complete pipeline:
1. Input text → TTS → audio
2. Audio → Gateway (with full_round_trip=true)
3. Gateway: STT → LLM (passthrough) → TTS → audio response
4. Gateway audio response → STT → text
5. Assert: final text == input text

This validated that the passthrough LLM correctly preserves the input text
through the entire audio processing pipeline.

**Status:** This test file is kept for reference but is not functional.
To test the pipeline without gateway, use direct gRPC calls to STT, LLM, and TTS services.
"""
import os
import sys
import asyncio
import logging
import grpc
import httpx
from typing import Optional
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import shim clients
from june_grpc_api import tts as tts_shim, asr as asr_shim


class EndToEndTextPassthroughTest:
    """End-to-end test for text passthrough via Gateway."""
    
    def __init__(self,
                 tts_address: str = "localhost:50053",
                 stt_address: str = "localhost:50052",
                 gateway_url: str = "http://localhost:8000",
                 sample_rate: int = 16000):
        self.tts_address = tts_address
        self.stt_address = stt_address
        self.gateway_url = gateway_url
        self.sample_rate = sample_rate
        
        logger.info(f"TTS Service: {self.tts_address}")
        logger.info(f"STT Service: {self.stt_address}")
        logger.info(f"Gateway URL: {self.gateway_url}")
    
    async def text_to_speech(self, text: str) -> bytes:
        """Step 1: Convert text to audio using TTS."""
        try:
            logger.info(f"Step 1: TTS - Converting text to audio: '{text}'")
            async with grpc.aio.insecure_channel(self.tts_address) as channel:
                client = tts_shim.TextToSpeechClient(channel)
                cfg = tts_shim.SynthesisConfig(
                    sample_rate=self.sample_rate,
                    speed=1.0,
                    pitch=0.0
                )
                audio = await client.synthesize(
                    text=text,
                    voice_id="default",
                    language="en",
                    config=cfg
                )
                if audio:
                    logger.info(f"  ✅ Generated {len(audio)} bytes of audio")
                    return audio
                else:
                    logger.error("  ❌ TTS returned empty audio")
                    return b""
        except Exception as e:
            logger.error(f"  ❌ TTS failed: {e}")
            raise
    
    async def send_to_gateway(self, audio_data: bytes, session_id: str = "e2e_test") -> bytes:
        """Step 2: Send audio to Gateway with full_round_trip=true."""
        try:
            logger.info(f"Step 2: Gateway - Sending {len(audio_data)} bytes with full_round_trip=true")
            url = f"{self.gateway_url}/api/v1/audio/transcribe"
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                files = {
                    'audio': ('audio.wav', audio_data, 'audio/wav')
                }
                data = {
                    'session_id': session_id,
                    'full_round_trip': 'true'  # Request: STT → LLM → TTS
                }
                
                response = await client.post(url, files=files, data=data)
                
                if response.status_code != 200:
                    logger.error(f"  ❌ Gateway returned status {response.status_code}: {response.text}")
                    return b""
                
                result = response.json()
                logger.info(f"  ✅ Gateway response keys: {list(result.keys())}")
                
                # Extract audio response
                if 'audio_data' in result:
                    audio_response = result['audio_data']
                    if isinstance(audio_response, str):
                        import base64
                        audio_bytes = base64.b64decode(audio_response)
                        logger.info(f"  ✅ Decoded {len(audio_bytes)} bytes from base64")
                        return audio_bytes
                    else:
                        return audio_response
                else:
                    logger.error(f"  ❌ No audio_data in response. Available keys: {list(result.keys())}")
                    return b""
                    
        except Exception as e:
            logger.error(f"  ❌ Gateway request failed: {e}")
            raise
    
    def pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
        """Convert raw PCM audio data to WAV format."""
        import wave
        import io
        
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        
        wav_buffer.seek(0)
        return wav_buffer.read()
    
    async def speech_to_text(self, audio_data: bytes) -> str:
        """Step 3: Convert audio to text using STT."""
        try:
            logger.info(f"Step 3: STT - Converting {len(audio_data)} bytes to text")
            
            # Convert PCM to WAV if needed (TTS returns raw PCM)
            if len(audio_data) > 0 and not audio_data[:4] == b'RIFF':
                audio_data = self.pcm_to_wav(audio_data, self.sample_rate, channels=1, sample_width=2)
            
            async with grpc.aio.insecure_channel(self.stt_address) as channel:
                client = asr_shim.SpeechToTextClient(channel)
                cfg = asr_shim.RecognitionConfig(
                    language="en",
                    interim_results=False
                )
                result = await client.recognize(
                    audio_data,
                    sample_rate=self.sample_rate,
                    encoding="wav",
                    config=cfg
                )
                if result.transcript:
                    logger.info(f"  ✅ Recognized: '{result.transcript}' (confidence: {result.confidence:.2f})")
                    return result.transcript
                else:
                    logger.error("  ❌ STT returned empty transcript")
                    return ""
        except Exception as e:
            logger.error(f"  ❌ STT failed: {e}")
            raise
    
    async def test_text_passthrough(self, input_text: str, tolerance: str = "exact") -> bool:
        """
        Run the complete end-to-end test.
        
        Args:
            input_text: Text to test
            tolerance: "exact" (must match exactly) or "contains" (output must contain input)
            
        Returns:
            True if test passed, False otherwise
        """
        logger.info("=" * 80)
        logger.info("END-TO-END TEXT PASSTHROUGH TEST")
        logger.info("=" * 80)
        logger.info(f"Input text: '{input_text}'")
        logger.info("")
        
        try:
            # Step 1: Text → TTS → Audio
            input_audio = await self.text_to_speech(input_text)
            if not input_audio or len(input_audio) == 0:
                logger.error("❌ Failed at Step 1: TTS")
                return False
            logger.info("")
            
            # Step 2: Audio → Gateway (STT → LLM → TTS) → Audio Response
            output_audio = await self.send_to_gateway(input_audio)
            if not output_audio or len(output_audio) == 0:
                logger.error("❌ Failed at Step 2: Gateway")
                return False
            logger.info("")
            
            # Step 3: Audio Response → STT → Text
            output_text = await self.speech_to_text(output_audio)
            if not output_text:
                logger.error("❌ Failed at Step 3: STT")
                return False
            logger.info("")
            
            # Step 4: Assert text matches
            logger.info("Step 4: Validation - Comparing input and output text")
            logger.info(f"  Input:  '{input_text}'")
            logger.info(f"  Output: '{output_text}'")
            
            input_normalized = input_text.strip().lower()
            output_normalized = output_text.strip().lower()
            
            if tolerance == "exact":
                passed = input_normalized == output_normalized
                logger.info(f"  Comparison: {'✅ EXACT MATCH' if passed else '❌ MISMATCH'}")
            elif tolerance == "contains":
                passed = input_normalized in output_normalized or output_normalized in input_normalized
                logger.info(f"  Comparison: {'✅ OUTPUT CONTAINS INPUT' if passed else '❌ NO MATCH'}")
            else:
                logger.error(f"  Unknown tolerance mode: {tolerance}")
                return False
            
            logger.info("")
            logger.info("=" * 80)
            if passed:
                logger.info("✅ TEST PASSED: Text successfully passthrough pipeline")
            else:
                logger.info("❌ TEST FAILED: Text did not match after pipeline")
            logger.info("=" * 80)
            
            return passed
            
        except Exception as e:
            logger.error(f"❌ Test failed with exception: {e}", exc_info=True)
            return False


async def main():
    """Main test runner."""
    # Get service addresses from environment or use defaults
    # If running in Docker, use service names; otherwise use localhost
    import socket
    is_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"
    
    if is_docker:
        tts_address = os.getenv("TTS_URL", "tts:50053").replace("grpc://", "")
        stt_address = os.getenv("STT_URL", "stt:50052").replace("grpc://", "")
        gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000")
    else:
        tts_address = os.getenv("TTS_URL", "localhost:50053").replace("grpc://", "")
        stt_address = os.getenv("STT_URL", "localhost:50052").replace("grpc://", "")
        gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8000")
    
    tester = EndToEndTextPassthroughTest(
        tts_address=tts_address,
        stt_address=stt_address,
        gateway_url=gateway_url
    )
    
    # Test cases
    test_cases = [
        ("Hello world", "exact"),
        ("The quick brown fox jumps over the lazy dog", "contains"),  # Longer text, may have slight variations
        ("Test", "exact"),
    ]
    
    results = []
    for input_text, tolerance in test_cases:
        passed = await tester.test_text_passthrough(input_text, tolerance=tolerance)
        results.append({
            "input": input_text,
            "tolerance": tolerance,
            "passed": passed
        })
        logger.info("")
    
    # Summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    logger.info(f"Passed: {passed_count}/{total_count}")
    for i, result in enumerate(results, 1):
        status = "✅" if result["passed"] else "❌"
        logger.info(f"  {i}. {status} '{result['input']}' ({result['tolerance']})")
    
    # Exit with non-zero if any test failed
    sys.exit(0 if passed_count == total_count else 1)


if __name__ == "__main__":
    asyncio.run(main())

