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
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import List, Tuple

import grpc

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import shim clients
from june_grpc_api import asr as asr_shim
from june_grpc_api import tts as tts_shim


class TtsSttValidator:
    """Validates TTS and STT components used in test suite."""

    def __init__(
        self,
        tts_address: str = "localhost:50053",
        stt_address: str = "localhost:50052",
        sample_rate: int = 16000,
        tolerance: str = "contains",
    ):
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
                    text=text, voice_id="default", language="en", config=cfg
                )
                return audio if audio else b""
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return b""

    def pcm_to_wav(
        self,
        pcm_data: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> bytes:
        """Convert raw PCM audio data to WAV format."""
        import io
        import struct
        import wave

        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
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
            if len(audio_data) > 0 and not audio_data[:4] == b"RIFF":
                # Not a WAV file (doesn't start with RIFF header), convert PCM to WAV
                audio_data = self.pcm_to_wav(
                    audio_data, self.sample_rate, channels=1, sample_width=2
                )

            async with grpc.aio.insecure_channel(self.stt_address) as channel:
                client = asr_shim.SpeechToTextClient(channel)
                cfg = asr_shim.RecognitionConfig(language="en", interim_results=False)
                result = await client.recognize(
                    audio_data, sample_rate=self.sample_rate, encoding="wav", config=cfg
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
        text = re.sub(r"[.,!?;:]", "", text)

        # Handle padded single words if present: "the word X here" -> extract just "X"
        # (Not used currently, but kept for backward compatibility)
        padded_pattern = r"the\s+word\s+(\w+)\s+here"
        match = re.search(padded_pattern, text)
        if match:
            text = match.group(1)

        # Normalize numbers: "1, 2, 3" -> "one two three"
        number_map = {
            "1": "one",
            "2": "two",
            "3": "three",
            "4": "four",
            "5": "five",
            "6": "six",
            "7": "seven",
            "8": "eight",
            "9": "nine",
            "0": "zero",
        }
        for digit, word in number_map.items():
            text = text.replace(digit, word)

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def text_matches(self, input_text: str, output_text: str) -> bool:
        """Check if input and output text match based on tolerance."""
        input_norm = self.normalize_text(input_text)
        output_norm = self.normalize_text(output_text)

        # If normalized texts are empty, fail
        if not input_norm or not output_norm:
            return False

        if self.tolerance == "exact":
            return input_norm == output_norm
        elif self.tolerance == "contains":
            # Check if output contains input or vice versa (for longer outputs)
            # For single words, be more lenient - check if word appears in output
            input_words = input_norm.split()
            if len(input_words) == 1:
                # Single word: check if it appears anywhere in output
                return input_words[0] in output_norm.split()
            else:
                # Multiple words: check if input is contained in output or vice versa
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

    async def test_tts_round_trip(
        self, input_text: str, verbose: bool = False
    ) -> Tuple[bool, str, str]:
        """
        Test TTS round-trip: Text → TTS → STT → Text

        Returns:
            (success, input_text, output_text)
        """
        if verbose:
            logger.info(f"  Testing: '{input_text}'")

        # Step 1: Text → TTS → Audio
        audio = await self.tts_synthesize(input_text)
        if not audio or len(audio) == 0:
            if verbose:
                logger.error(f"  ❌ TTS produced empty audio")
            return (False, input_text, "")

        if verbose:
            logger.info(f"  ✅ TTS: Generated {len(audio)} bytes")

        # Step 2: Audio → STT → Text
        output_text = await self.stt_recognize(audio)
        if not output_text:
            if verbose:
                logger.error(f"  ❌ STT produced empty transcript")
            return (False, input_text, "")

        if verbose:
            logger.info(f"  ✅ STT: Recognized '{output_text}'")

        # Step 3: Compare
        matches = self.text_matches(input_text, output_text)
        if verbose:
            if matches:
                logger.info(f"  ✅ Match: '{input_text}' ≈ '{output_text}'")
            else:
                logger.warning(f"  ⚠️  Mismatch: '{input_text}' ≠ '{output_text}'")

        return (matches, input_text, output_text)

    async def test_batch_concurrent(
        self, test_cases: List, max_concurrent: int = 10, verbose: bool = False
    ) -> List[Tuple[bool, str, str]]:
        """
        Run multiple TTS round-trip tests concurrently.

        Args:
            test_cases: List of test cases (TestCase objects or strings)
            max_concurrent: Maximum number of concurrent tests
            verbose: Whether to show detailed output

        Returns:
            List of (success, input_text, output_text) tuples in original order
        """
        # Extract text from TestCase objects if needed
        case_texts = [
            case.text if hasattr(case, "text") else case for case in test_cases
        ]

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_with_semaphore(text: str) -> Tuple[bool, str, str]:
            async with semaphore:
                return await self.test_tts_round_trip(text, verbose=verbose)

        # Process in batches to maintain order and show progress
        results = []
        total = len(case_texts)

        for i in range(0, total, max_concurrent):
            batch_texts = case_texts[i : i + max_concurrent]
            batch_tasks = [run_with_semaphore(text) for text in batch_texts]
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)

            completed = min(i + len(batch_texts), total)
            if completed % 50 == 0 or completed == total:
                logger.info(f"  Progress: {completed}/{total}")

        return results

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

    async def test_stt_accuracy(
        self, test_cases: List[Tuple[str, str]]
    ) -> Tuple[int, int]:
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
                logger.info(
                    f"  ✅ '{audio_text}' → '{recognized}' (expected: '{expected_text}')"
                )
                passed += 1
            else:
                logger.warning(
                    f"  ⚠️  '{audio_text}' → '{recognized}' (expected: '{expected_text}')"
                )

        return (passed, len(test_cases))


async def main():
    """Run validation tests."""
    import sys

    # Import test case generator
    sys.path.insert(0, os.path.dirname(__file__))
    from test_case_generator import TestCase, TestCaseGenerator

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
        tolerance="contains",  # Use contains for more lenient matching
    )

    logger.info("=" * 80)
    logger.info("TTS/STT VALIDATION TEST SUITE")
    logger.info("=" * 80)
    logger.info("")

    # Generate test cases
    generator = TestCaseGenerator()
    target_short = 300
    target_medium = 400
    target_long = 300
    total_target = target_short + target_medium + target_long

    logger.info(
        f"Generating test cases: {target_short} short, {target_medium} medium, {target_long} long"
    )
    all_test_cases = generator.generate_all(
        short_count=target_short, medium_count=target_medium, long_count=target_long
    )

    stats = generator.get_statistics(all_test_cases)
    logger.info(f"Generated {stats['total']} test cases")
    logger.info(f"  Short (1-3 words): {stats['by_category'].get('short', 0)}")
    logger.info(f"  Medium (4-10 words): {stats['by_category'].get('medium', 0)}")
    logger.info(f"  Long (11+ words): {stats['by_category'].get('long', 0)}")
    logger.info("")

    # Organize by category
    short_cases = [case for case in all_test_cases if case.category == "short"]
    medium_cases = [case for case in all_test_cases if case.category == "medium"]
    long_cases = [case for case in all_test_cases if case.category == "long"]

    # Test 1: Short Phrases Round-Trip (with concurrency)
    logger.info("Test 1: Short Phrases Round-Trip (1-3 words)")
    logger.info("-" * 80)
    short_results = await validator.test_batch_concurrent(
        short_cases, max_concurrent=10, verbose=False
    )

    short_passed = sum(1 for success, _, _ in short_results if success)
    logger.info("")
    logger.info(
        f"Short phrases: {short_passed}/{len(short_cases)} passed ({short_passed*100//len(short_cases) if short_cases else 0}%)"
    )
    logger.info("")

    # Test 2: Medium Phrases Round-Trip (with concurrency)
    logger.info("Test 2: Medium Phrases Round-Trip (4-10 words)")
    logger.info("-" * 80)
    medium_results = await validator.test_batch_concurrent(
        medium_cases, max_concurrent=10, verbose=False
    )

    medium_passed = sum(1 for success, _, _ in medium_results if success)
    logger.info("")
    logger.info(
        f"Medium phrases: {medium_passed}/{len(medium_cases)} passed ({medium_passed*100//len(medium_cases) if medium_cases else 0}%)"
    )
    logger.info("")

    # Test 3: Long Phrases Round-Trip (with concurrency)
    logger.info("Test 3: Long Phrases Round-Trip (11+ words)")
    logger.info("-" * 80)
    long_results = await validator.test_batch_concurrent(
        long_cases, max_concurrent=10, verbose=False
    )

    long_passed = sum(1 for success, _, _ in long_results if success)
    logger.info("")
    logger.info(
        f"Long phrases: {long_passed}/{len(long_cases)} passed ({long_passed*100//len(long_cases) if long_cases else 0}%)"
    )
    logger.info("")

    # Test 4: TTS Consistency (sampling)
    logger.info("Test 4: TTS Consistency (sampling)")
    logger.info("-" * 80)
    consistency_samples = [
        short_cases[0].text if short_cases else "Hello",
        medium_cases[0].text if medium_cases else "The quick brown fox jumps",
        long_cases[0].text
        if long_cases
        else "The quick brown fox jumps over the lazy dog",
    ]
    consistency_passed = 0
    for text in consistency_samples:
        if await validator.test_tts_consistency(text, num_runs=3):
            consistency_passed += 1
        logger.info("")

    logger.info(f"Consistency: {consistency_passed}/{len(consistency_samples)} passed")
    logger.info("")

    # Summary
    logger.info("=" * 80)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 80)
    total_tests = (
        len(short_cases)
        + len(medium_cases)
        + len(long_cases)
        + len(consistency_samples)
    )
    total_passed = short_passed + medium_passed + long_passed + consistency_passed

    logger.info(f"Short Phrases (1-3 words): {short_passed}/{len(short_cases)}")
    logger.info(f"Medium Phrases (4-10 words): {medium_passed}/{len(medium_cases)}")
    logger.info(f"Long Phrases (11+ words): {long_passed}/{len(long_cases)}")
    logger.info(f"TTS Consistency: {consistency_passed}/{len(consistency_samples)}")
    logger.info(
        f"Total Round-Trip: {short_passed + medium_passed + long_passed}/{len(short_cases) + len(medium_cases) + len(long_cases)}"
    )
    logger.info(f"Total: {total_passed}/{total_tests}")
    logger.info("")

    # Show failures if any
    if total_passed < total_tests:
        logger.info("=" * 80)
        logger.info("FAILURES BY CATEGORY")
        logger.info("=" * 80)

        if short_passed < len(short_cases):
            failed_short = [
                (input_text, output_text)
                for success, input_text, output_text in short_results
                if not success
            ]
            logger.info(
                f"\nFailed Short Phrases ({len(failed_short)}/{len(short_cases)}):"
            )
            for input_text, output_text in failed_short[:10]:  # Show first 10
                logger.warning(f"  '{input_text}' → '{output_text}'")
            if len(failed_short) > 10:
                logger.warning(f"  ... and {len(failed_short) - 10} more")

        if medium_passed < len(medium_cases):
            failed_medium = [
                (input_text, output_text)
                for success, input_text, output_text in medium_results
                if not success
            ]
            logger.info(
                f"\nFailed Medium Phrases ({len(failed_medium)}/{len(medium_cases)}):"
            )
            for input_text, output_text in failed_medium[:10]:  # Show first 10
                logger.warning(f"  '{input_text}' → '{output_text}'")
            if len(failed_medium) > 10:
                logger.warning(f"  ... and {len(failed_medium) - 10} more")

        if long_passed < len(long_cases):
            failed_long = [
                (input_text, output_text)
                for success, input_text, output_text in long_results
                if not success
            ]
            logger.info(
                f"\nFailed Long Phrases ({len(failed_long)}/{len(long_cases)}):"
            )
            for input_text, output_text in failed_long[:10]:  # Show first 10
                logger.warning(f"  '{input_text}' → '{output_text}'")
            if len(failed_long) > 10:
                logger.warning(f"  ... and {len(failed_long) - 10} more")

    logger.info("")
    if total_passed == total_tests:
        logger.info("✅ All validation tests passed!")
        logger.info(f"✅ {total_passed}/{total_tests} tests passed (100%)")
        sys.exit(0)
    else:
        pass_rate = (total_passed * 100) // total_tests if total_tests > 0 else 0
        logger.warning(
            f"⚠️  Some tests failed: {total_passed}/{total_tests} passed ({pass_rate}%)"
        )
        if pass_rate < 100:
            logger.warning("⚠️  WARNING: TTS/STT may not be reliable for E2E tests")
            logger.warning("⚠️  Must achieve 100% pass rate for reliable E2E testing")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
