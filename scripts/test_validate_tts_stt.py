#!/usr/bin/env python3
"""
Validation Tests for TTS and STT Components Used in Test Suite

This test suite validates that our TTS and STT services are working correctly,
which is critical since we use them in our end-to-end tests. If these are broken,
our E2E tests would give incorrect results.

Tests:
1. TTS Round-Trip: Text → TTS → STT → Text (should match input)
2. STT Accuracy: Known audio → STT → Text (should match expected)
3. TTS Consistency: Same text → TTS multiple times (should produce similar audio)
4. STT Robustness: Various text lengths and complexities
"""
import os
import sys
import asyncio
import logging
import grpc
from typing import List, Tuple
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import shim clients
from june_grpc_api import tts as tts_shim, asr as asr_shim


class TtsSttValidator:
    """Validates TTS and STT components used in test suite."""
    
    def __init__(self,
                 tts_address: str = "localhost:50053",
                 stt_address: str = "localhost:50052",
                 sample_rate: int = 16000,
                 tolerance: str = "contains"):
        self.tts_address = tts_address
        self.stt_address = stt_address
        self.sample_rate = sample_rate
        self.tolerance = tolerance  # "exact", "contains", "fuzzy"
        
        logger.info(f"TTS Service: {self.tts_address}")
        logger.info(f"STT Service: {self.stt_address}")
        logger.info(f"Sample Rate: {self.sample_rate}")
    
    async def tts_synthesize(self, text: str) -> bytes:
        """Convert text to audio using TTS."""
        try:
            async with grpc.aio.insecure_channel(self.tts_address) as channel:
                client = tts_shim.TextToSpeechClient(channel)
                cfg = tts_shim.SynthesisConfig(speed=1.0, pitch=0.0)
                audio = await client.synthesize(
                    text=text,
                    voice_id="default",
                    language="en",
                    config=cfg
                )
                return audio if audio else b""
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return b""
    
    def pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
        """Convert raw PCM audio data to WAV format."""
        import struct
        import wave
        import io
        
        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        
        wav_buffer.seek(0)
        return wav_buffer.read()
    
    async def stt_recognize(self, audio_data: bytes) -> str:
        """Convert audio to text using STT.
        
        Note: audio_data should be WAV format (with header) for STT to work.
        """
        try:
            # If audio_data is raw PCM (from TTS), convert to WAV
            # TTS returns PCM16 (2 bytes per sample), mono, at sample_rate
            if len(audio_data) > 0 and not audio_data[:4] == b'RIFF':
                # Not a WAV file (doesn't start with RIFF header), convert PCM to WAV
                audio_data = self.pcm_to_wav(audio_data, self.sample_rate, channels=1, sample_width=2)
            
            async with grpc.aio.insecure_channel(self.stt_address) as channel:
                client = asr_shim.SpeechToTextClient(channel)
                cfg = asr_shim.RecognitionConfig(language="en", interim_results=False)
                result = await client.recognize(
                    audio_data,
                    sample_rate=self.sample_rate,
                    encoding="wav",
                    config=cfg
                )
                return result.transcript if result.transcript else ""
        except Exception as e:
            logger.error(f"STT recognition failed: {e}")
            return ""
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        import re
        # Convert to lowercase and remove punctuation
        text = text.strip().lower()
        text = re.sub(r'[.,!?;:]', '', text)
        
        # Normalize numbers: "1, 2, 3" -> "one two three"
        number_map = {
            "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
            "6": "six", "7": "seven", "8": "eight", "9": "nine", "0": "zero"
        }
        for digit, word in number_map.items():
            text = text.replace(digit, word)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def text_matches(self, input_text: str, output_text: str) -> bool:
        """Check if input and output text match based on tolerance."""
        input_norm = self.normalize_text(input_text)
        output_norm = self.normalize_text(output_text)
        
        if self.tolerance == "exact":
            return input_norm == output_norm
        elif self.tolerance == "contains":
            # Check if output contains input or vice versa (for longer outputs)
            return input_norm in output_norm or output_norm in input_norm
        elif self.tolerance == "fuzzy":
            # Simple fuzzy match - at least 70% of words match
            input_words = set(input_norm.split())
            output_words = set(output_norm.split())
            if not input_words:
                return False
            overlap = len(input_words & output_words)
            return overlap / len(input_words) >= 0.7
        else:
            return False
    
    async def test_tts_round_trip(self, input_text: str) -> Tuple[bool, str, str]:
        """
        Test TTS round-trip: Text → TTS → STT → Text
        
        Returns:
            (success, input_text, output_text)
        """
        logger.info(f"  Testing: '{input_text}'")
        
        # Step 1: Text → TTS → Audio
        audio = await self.tts_synthesize(input_text)
        if not audio or len(audio) == 0:
            logger.error(f"  ❌ TTS produced empty audio")
            return (False, input_text, "")
        
        logger.info(f"  ✅ TTS: Generated {len(audio)} bytes")
        
        # Step 2: Audio → STT → Text
        output_text = await self.stt_recognize(audio)
        if not output_text:
            logger.error(f"  ❌ STT produced empty transcript")
            return (False, input_text, "")
        
        logger.info(f"  ✅ STT: Recognized '{output_text}'")
        
        # Step 3: Compare
        matches = self.text_matches(input_text, output_text)
        if matches:
            logger.info(f"  ✅ Match: '{input_text}' ≈ '{output_text}'")
        else:
            logger.warning(f"  ⚠️  Mismatch: '{input_text}' ≠ '{output_text}'")
        
        return (matches, input_text, output_text)
    
    async def test_tts_consistency(self, text: str, num_runs: int = 3) -> bool:
        """
        Test TTS consistency: Same text should produce similar audio lengths.
        
        Returns:
            True if audio lengths are within 20% of each other
        """
        logger.info(f"  Testing TTS consistency for: '{text}' ({num_runs} runs)")
        
        audio_lengths = []
        for i in range(num_runs):
            audio = await self.tts_synthesize(text)
            if not audio or len(audio) == 0:
                logger.error(f"  ❌ Run {i+1}: Empty audio")
                return False
            audio_lengths.append(len(audio))
            logger.info(f"  Run {i+1}: {len(audio)} bytes")
        
        # Check consistency (within 20% variance)
        avg_length = sum(audio_lengths) / len(audio_lengths)
        max_variance = avg_length * 0.2
        
        for length in audio_lengths:
            if abs(length - avg_length) > max_variance:
                logger.warning(f"  ⚠️  Inconsistent audio lengths (variance > 20%)")
                return False
        
        logger.info(f"  ✅ Consistent: {audio_lengths} (avg: {avg_length:.0f})")
        return True
    
    async def test_stt_accuracy(self, test_cases: List[Tuple[str, str]]) -> Tuple[int, int]:
        """
        Test STT accuracy with known audio-text pairs.
        
        Args:
            test_cases: List of (audio_text, expected_text) tuples
                      where audio_text is the text to generate audio from
        
        Returns:
            (passed, total)
        """
        logger.info(f"  Testing STT accuracy with {len(test_cases)} cases")
        
        passed = 0
        for audio_text, expected_text in test_cases:
            # Generate audio from text
            audio = await self.tts_synthesize(audio_text)
            if not audio or len(audio) == 0:
                logger.error(f"  ❌ Failed to generate audio for '{audio_text}'")
                continue
            
            # Recognize audio
            recognized = await self.stt_recognize(audio)
            if not recognized:
                logger.error(f"  ❌ Failed to recognize audio for '{audio_text}'")
                continue
            
            # Compare
            matches = self.text_matches(expected_text, recognized)
            if matches:
                logger.info(f"  ✅ '{audio_text}' → '{recognized}' (expected: '{expected_text}')")
                passed += 1
            else:
                logger.warning(f"  ⚠️  '{audio_text}' → '{recognized}' (expected: '{expected_text}')")
        
        return (passed, len(test_cases))


async def main():
    """Run validation tests."""
    # Detect Docker environment
    is_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"
    
    if is_docker:
        tts_address = os.getenv("TTS_URL", "tts:50053").replace("grpc://", "")
        stt_address = os.getenv("STT_URL", "stt:50052").replace("grpc://", "")
    else:
        tts_address = os.getenv("TTS_URL", "localhost:50053").replace("grpc://", "")
        stt_address = os.getenv("STT_URL", "localhost:50052").replace("grpc://", "")
    
    validator = TtsSttValidator(
        tts_address=tts_address,
        stt_address=stt_address,
        tolerance="contains"  # Use contains for more lenient matching
    )
    
    logger.info("=" * 80)
    logger.info("TTS/STT VALIDATION TEST SUITE")
    logger.info("=" * 80)
    logger.info("")
    
    # Test 1: TTS Round-Trip Accuracy
    logger.info("Test 1: TTS Round-Trip Accuracy")
    logger.info("-" * 80)
    test_texts = [
        "Hello",
        "Hello world",
        "Test",
        "The quick brown fox",
        "One two three four five",
    ]
    
    round_trip_results = []
    for text in test_texts:
        success, input_text, output_text = await validator.test_tts_round_trip(text)
        round_trip_results.append((success, input_text, output_text))
        logger.info("")
    
    round_trip_passed = sum(1 for success, _, _ in round_trip_results if success)
    logger.info(f"Round-trip results: {round_trip_passed}/{len(test_texts)} passed")
    logger.info("")
    
    # Test 2: TTS Consistency
    logger.info("Test 2: TTS Consistency")
    logger.info("-" * 80)
    consistency_texts = ["Hello world", "Test consistency"]
    consistency_passed = 0
    for text in consistency_texts:
        if await validator.test_tts_consistency(text):
            consistency_passed += 1
        logger.info("")
    
    logger.info(f"Consistency results: {consistency_passed}/{len(consistency_texts)} passed")
    logger.info("")
    
    # Test 3: STT Accuracy (with various text complexities)
    logger.info("Test 3: STT Accuracy")
    logger.info("-" * 80)
    stt_test_cases = [
        ("Hello", "Hello"),
        ("World", "World"),
        ("Test", "Test"),
        ("Quick brown fox", "Quick brown fox"),
    ]
    
    stt_passed, stt_total = await validator.test_stt_accuracy(stt_test_cases)
    logger.info("")
    logger.info(f"STT accuracy: {stt_passed}/{stt_total} passed")
    logger.info("")
    
    # Summary
    logger.info("=" * 80)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 80)
    total_tests = len(test_texts) + len(consistency_texts) + len(stt_test_cases)
    total_passed = round_trip_passed + consistency_passed + stt_passed
    
    logger.info(f"TTS Round-Trip: {round_trip_passed}/{len(test_texts)}")
    logger.info(f"TTS Consistency: {consistency_passed}/{len(consistency_texts)}")
    logger.info(f"STT Accuracy: {stt_passed}/{stt_total}")
    logger.info(f"Total: {total_passed}/{total_tests}")
    logger.info("")
    
    if total_passed == total_tests:
        logger.info("✅ All validation tests passed!")
        sys.exit(0)
    else:
        logger.warning(f"⚠️  Some tests failed: {total_passed}/{total_tests} passed")
        logger.warning("⚠️  WARNING: TTS/STT may not be reliable for E2E tests")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

