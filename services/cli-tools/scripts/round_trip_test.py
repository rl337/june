#!/usr/bin/env python3
"""
Round-Trip Audio Testing for STT/TTS Services

This script performs round-trip testing by:
1. Converting text to speech using TTS service
2. Transcribing the audio using STT service
3. Comparing the original text with the transcribed result
4. Calculating accuracy and quality metrics

This is an excellent way to validate the integrated performance of both services.
"""

import argparse
import os
import sys
import logging
import json
import time
import numpy as np
import soundfile as sf
import librosa
import jiwer
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
import subprocess

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class RoundTripResult:
    """Result of a round-trip TTS→STT test."""

    original_text: str
    transcribed_text: str
    tts_processing_time: float
    stt_processing_time: float
    total_processing_time: float
    wer: float  # Word Error Rate
    cer: float  # Character Error Rate
    match_percentage: float
    exact_match: bool
    audio_duration: float
    sample_rate: int


class RoundTripTester:
    """Round-trip audio testing between TTS and STT."""

    def __init__(self, test_data_dir: str = "/tmp/round_trip_tests"):
        self.test_data_dir = Path(test_data_dir)
        self.test_data_dir.mkdir(parents=True, exist_ok=True)

        # Test cases covering various scenarios
        self.test_cases = [
            # Basic phrases
            "Hello, how are you?",
            "The quick brown fox jumps over the lazy dog.",
            "Artificial intelligence is transforming the world.",
            # Numbers and dates
            "The meeting is scheduled for March 15th, 2024 at 3:30 PM.",
            "Please call me at 555-123-4567.",
            "The temperature is 75 degrees Fahrenheit.",
            # Questions
            "Can you help me with this problem?",
            "What is the weather forecast for tomorrow?",
            "Where is the nearest restaurant?",
            # Longer sentences
            "I would like to order a pizza with extra cheese, pepperoni, and mushrooms.",
            "The weather is sunny with a temperature of 75 degrees and a slight breeze from the west.",
            "Please send me an email with the details about tomorrow's meeting at 2 PM in the conference room.",
            # Special characters and punctuation
            "Prices are: $19.99, €15.50, and ¥2000.",
            "The code is: ABC-123-XYZ",
            "Visit our website at www.example.com or email us at info@example.com",
            # Complex sentences
            "The artificial intelligence system successfully processed the natural language input and generated an appropriate response.",
            "Scientists discovered that machine learning algorithms can be trained to recognize patterns in large datasets.",
            "The weather forecast predicts rain for the weekend, so we should plan indoor activities.",
            # Emotional context
            "I'm really excited about this new opportunity!",
            "This VIP event is amazing and I'm having a wonderful time.",
            "That's terrible news and I'm sorry to hear about your situation.",
            # Technical content
            "The API endpoint returns JSON data with a status code of 200.",
            "Please implement the REST API following best practices for authentication and error handling.",
            "The database connection string should be configured in the environment variables.",
        ]

    def test_round_trip(
        self,
        tts_service_url: str = "localhost:50053",
        stt_service_url: str = "localhost:50052",
    ) -> List[RoundTripResult]:
        """Run round-trip tests through TTS and STT services."""
        logger.info(f"Starting round-trip tests with {len(self.test_cases)} test cases")
        logger.info(f"TTS Service: {tts_service_url}")
        logger.info(f"STT Service: {stt_service_url}")

        results = []

        for i, original_text in enumerate(self.test_cases):
            logger.info(f"\n{'='*60}")
            logger.info(f"Test Case {i+1}/{len(self.test_cases)}")
            logger.info(f"Original Text: '{original_text}'")
            logger.info(f"{'='*60}")

            try:
                # Step 1: TTS - Convert text to speech
                logger.info("Step 1: Converting text to speech...")
                tts_start = time.time()

                audio_file = self._text_to_speech(
                    tts_service_url, original_text, f"test_{i:03d}.wav"
                )

                tts_time = time.time() - tts_start
                logger.info(f"TTS completed in {tts_time:.3f}s")

                # Load audio to get metadata
                if audio_file and os.path.exists(audio_file):
                    audio, sr = librosa.load(audio_file, sr=None)
                    audio_duration = len(audio) / sr
                else:
                    audio_duration = 0.0
                    sr = 16000

                # Step 2: STT - Transcribe audio to text
                logger.info("Step 2: Converting speech to text...")
                stt_start = time.time()

                transcribed_text = self._speech_to_text(stt_service_url, audio_file)

                stt_time = time.time() - stt_start
                logger.info(f"STT completed in {stt_time:.3f}s")

                # Step 3: Calculate metrics
                logger.info("Step 3: Calculating metrics...")

                wer = jiwer.wer(original_text, transcribed_text)
                cer = jiwer.cer(original_text, transcribed_text)

                # Calculate match percentage
                # Normalize both texts for comparison
                orig_normalized = self._normalize_text(original_text)
                trans_normalized = self._normalize_text(transcribed_text)

                exact_match = orig_normalized == trans_normalized

                # Calculate character-level match percentage
                TAGrame_char = jiwer.cer(
                    original_text, transcribed_text, return_dict=True
                )
                match_percentage = (1 - TAGrame_char["cer"]) * 100

                total_time = tts_time + stt_time

                # Create result
                result = RoundTripResult(
                    original_text=original_text,
                    transcribed_text=transcribed_text,
                    tts_processing_time=tts_time,
                    stt_processing_time=stt_time,
                    total_processing_time=total_time,
                    wer=wer,
                    cer=cer,
                    match_percentage=match_percentage,
                    exact_match=exact_match,
                    audio_duration=audio_duration,
                    sample_rate=sr,
                )

                results.append(result)

                # Print results
                logger.info(f"\nResults:")
                logger.info(f"  Transcribed Text: '{transcribed_text}'")
                logger.info(f"  Exact Match: {exact_match}")
                logger.info(f"  Match Percentage: {match_percentage:.2f}%")
                logger.info(f"  Word Error Rate (WER): {wer:.4f}")
                logger.info(f"  Character Error Rate (CER): {cer:.4f}")
                logger.info(f"  TTS Processing: {tts_time:.3f}s")
                logger.info(f"  STT Processing: {stt_time:.3f}s")
                logger.info(f"  Total Processing: {total_time:.3f}s")

                # Cleanup audio file
                if audio_file and os.path.exists(audio_file):
                    os.remove(audio_file)

            except Exception as e:
                logger.error(f"Round-trip test failed: {e}")
                # Create failed result
                results.append(
                    RoundTripResult(
                        original_text=original_text,
                        transcribed_text="",
                        tts_processing_time=0.0,
                        stt_processing_time=0.0,
                        total_processing_time=0.0,
                        wer=1.0,
                        cer=1.0,
                        match_percentage=0.0,
                        exact_match=False,
                        audio_duration=0.0,
                        sample_rate=0,
                    )
                )

        return results

    def _text_to_speech(self, service_url: str, text: str, filename: str) -> str:
        """Convert text to speech using TTS service (simplified implementation)."""
        audio_file = str(self.test_data_dir / filename)

        # In a real implementation, this would use proper gRPC client
        # For now, we'll use a simplified approach that checks service health

        try:
            # Check if TTS service is available
            result = subprocess.run(
                ["grpcurl", "-plaintext", service_url, "grpc.health.v1.Health/Check"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise Exception(f"TTS service health check failed: {result.stderr}")

            # Simulate TTS processing by creating a simple audio file
            # In a real implementation, this would call the TTS gRPC service
            logger.warning(
                "Using simulated TTS (implement proper gRPC client for production)"
            )

            # Generate a simple sine wave audio as placeholder
            sample_rate = 22050
            duration = min(
                len(text) * 0.1, 10.0
            )  # Estimate duration based on text length
            t = np.linspace(0, duration, int(sample_rate * duration))
            audio = np.sin(2 * np.pi * 440 * t) * 0.1  # Simple sine wave
            audio += np.random.normal(0, 0.01, len(audio))  # Add some noise

            sf.write(audio_file, audio, sample_rate)

            return audio_file

        except subprocess.TimeoutExpired:
            raise Exception("TTS service connection timeout")
        except FileNotFoundError:
            raise Exception("grpcurl not found - cannot test gRPC service")
        except Exception as e:
            raise Exception(f"TTS conversion failed: {e}")

    def _speech_to_text(self, service_url: str, audio_file: str) -> str:
        """Convert speech to text using STT service (simplified implementation)."""

        # In a real implementation, this would use proper gRPC client
        # For now, we'll use a simplified approach

        try:
            # Check if STT service is available
            result = subprocess.run(
                ["grpcurl", "-plaintext", service_url, "grpc.health.v1.Health/Check"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise Exception(f"STT service health check failed: {result.stderr}")

            # For now, return a simulated transcription
            # In production, this would call the STT gRPC service
            logger.warning(
                "Using simulated STT (implement proper gRPC client for production)"
            )

            # Simulate transcription delay
            time.sleep(0.1)

            # Return original text as placeholder (simulate perfect transcription)
            return "Hello, how are you?"  # Placeholder

        except subprocess.TimeoutExpired:
            raise Exception("STT service connection timeout")
        except FileNotFoundError:
            raise Exception("grpcurl not found - cannot test gRPC service")
        except Exception as e:
            raise Exception(f"STT conversion failed: {e}")

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Convert to lowercase
        text = text.lower()

        # Remove extra whitespace
        text = " ".join(text.split())

        # Remove punctuation for exact match comparison
        import string

        text = text.translate(str.maketrans("", "", string.punctuation))

        return text

    def calculate_statistics(self, results: List[RoundTripResult]) -> Dict[str, Any]:
        """Calculate overall statistics from round-trip test results."""
        if not results:
            return {}

        exact_matches = sum(1 for r in results if r.exact_match)
        successful_tests = len([r for r in results if r.transcribed_text])

        metrics = {
            "total_tests": len(results),
            "successful_tests": successful_tests,
            "exact_matches": exact_matches,
            "exact_match_rate": exact_matches / len(results) if results else 0.0,
            "average_wer": np.mean([r.wer for r in results if r.transcribed_text])
            if successful_tests > 0
            else 0.0,
            "average_cer": np.mean([r.cer for r in results if r.transcribed_text])
            if successful_tests > 0
            else 0.0,
            "average_match_percentage": np.mean(
                [r.match_percentage for r in results if r.transcribed_text]
            )
            if successful_tests > 0
            else 0.0,
            "average_tts_time": np.mean(
                [r.tts_processing_time for r in results if r.tts_processing_time > 0]
            )
            if results
            else 0.0,
            "average_stt_time": np.mean(
                [r.stt_processing_time for r in results if r.stt_processing_time > 0]
            )
            if results
            else 0.0,
            "average_total_time": np.mean(
                [
                    r.total_processing_time
                    for r in results
                    if r.total_processing_time > 0
                ]
            )
            if results
            else 0.0,
            "average_audio_duration": np.mean(
                [r.audio_duration for r in results if r.audio_duration > 0]
            )
            if results
            else 0.0,
        }

        return metrics

    def generate_report(
        self,
        results: List[RoundTripResult],
        output_path: str = "/tmp/round_trip_report.json",
    ) -> str:
        """Generate comprehensive round-trip test report."""
        logger.info("Generating round-trip test report...")

        statistics = self.calculate_statistics(results)

        report = {
            "timestamp": time.time(),
            "test_type": "round_trip_tts_stt",
            "statistics": statistics,
            "results": [asdict(r) for r in results],
        }

        # Save report
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Report saved to {output_path}")

        # Print summary
        print("\n" + "=" * 60)
        print("ROUND-TRIP AUDIO TEST SUMMARY")
        print("=" * 60)
        print(f"\nTotal Tests: {statistics['total_tests']}")
        print(f"Successful Tests: {statistics['successful_tests']}")
        print(f"Exact Matches: {statistics['exact_matches']}")
        print(f"Exact Match Rate: {statistics['exact_match_rate']:.2%}")
        print(f"\nAverage Word Error Rate (WER): {statistics['average_wer']:.4f}")
        print(f"Average Character Error Rate (CER): {statistics['average_cer']:.4f}")
        print(
            f"Average Match Percentage: {statistics['average_match_percentage']:.2f}%"
        )
        print(f"\nAverage TTS Processing Time: {statistics['average_tts_time']:.3f}s")
        print(f"Average STT Processing Time: {statistics['average_stt_time']:.3f}s")
        print(f"Average Total Processing Time: {statistics['average_total_time']:.3f}s")
        print("=" * 60)

        return output_path


def main():
    parser = argparse.ArgumentParser(description="Round-Trip Audio Testing (TTS→STT)")
    parser.add_argument("--tts-url", default="localhost:50053", help="TTS service URL")
    parser.add_argument("--stt-url", default="localhost:50052", help="STT service URL")
    parser.add_argument("--test-cases", type=int, help="Number of test cases to run")
    parser.add_argument(
        "--data-dir", default="/tmp/round_trip_tests", help="Test data directory"
    )
    parser.add_argument(
        "--output", default="/tmp/round_trip_report.json", help="Output report file"
    )

    args = parser.parse_args()

    # Initialize tester
    tester = RoundTripTester(args.data_dir)

    # Limit test cases if specified
    if args.test_cases:
        tester.test_cases = tester.test_cases[: args.test_cases]

    # Run round-trip tests
    logger.info("Starting round-trip TTS→STT tests...")
    results = tester.test_round_trip(args.tts_url, args.stt_url)

    # Generate report
    report_file = tester.generate_report(results, args.output)

    # Determine exit code
    statistics = tester.calculate_statistics(results)
    success_rate = statistics["exact_match_rate"]

    if success_rate >= 0.8:  # 80% exact match rate
        logger.info("Round-trip tests passed! (≥80% exact match rate)")
        sys.exit(0)
    else:
        logger.warning(f"Round-trip tests below threshold ({success_rate:.2%} < 80%)")
        sys.exit(1)


if __name__ == "__main__":
    main()
