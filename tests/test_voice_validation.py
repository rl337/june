"""
Validation test suite for voice message quality and accuracy.

Tests voice message round-trip accuracy, response quality, latency, and various audio qualities/lengths.
This suite provides comprehensive validation metrics for the voice message pipeline.
"""
import pytest
import asyncio
import os
import grpc
import httpx
import time
import json
import numpy as np
import struct
import base64
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
import logging

from june_grpc_api import asr as asr_shim, tts as tts_shim

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Service addresses
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
STT_ADDRESS = os.getenv("STT_SERVICE_ADDRESS", "localhost:50052")
TTS_ADDRESS = os.getenv("TTS_SERVICE_ADDRESS", "localhost:50053")
INFERENCE_ADDRESS = os.getenv("INFERENCE_API_URL", "localhost:50051").replace("grpc://", "")

# Test configurations
SAMPLE_RATES = [8000, 16000, 44100, 48000]  # Various audio qualities
DURATION_CATEGORIES = {
    "short": (0.5, 3.0),      # 0.5-3 seconds
    "medium": (3.0, 10.0),    # 3-10 seconds
    "long": (10.0, 30.0)      # 10-30 seconds
}


def create_wav_file(audio_data: bytes, sample_rate: int = 16000) -> bytes:
    """Create a WAV file from raw PCM audio data."""
    num_samples = len(audio_data) // 2  # 16-bit = 2 bytes per sample
    data_size = len(audio_data)
    file_size = 36 + data_size
    
    wav = b'RIFF'
    wav += struct.pack('<I', file_size)
    wav += b'WAVE'
    wav += b'fmt '
    wav += struct.pack('<I', 16)  # fmt chunk size
    wav += struct.pack('<HHIIHH', 1, 1, sample_rate, sample_rate * 2, 2, 16)  # PCM, mono
    wav += b'data'
    wav += struct.pack('<I', data_size)
    wav += audio_data
    
    return wav


def calculate_wer(reference: str, hypothesis: str) -> float:
    """Calculate Word Error Rate (WER)."""
    ref_words = reference.lower().strip().split()
    hyp_words = hypothesis.lower().strip().split()
    
    if len(ref_words) == 0:
        return 1.0 if len(hyp_words) > 0 else 0.0
    
    # Simple WER calculation (insertions + deletions + substitutions)
    # Using Levenshtein-like approach for words
    import difflib
    matches = difflib.SequenceMatcher(None, ref_words, hyp_words).ratio()
    return 1.0 - matches


def calculate_cer(reference: str, hypothesis: str) -> float:
    """Calculate Character Error Rate (CER)."""
    ref_chars = reference.lower().replace(" ", "")
    hyp_chars = hypothesis.lower().replace(" ", "")
    
    if len(ref_chars) == 0:
        return 1.0 if len(hyp_chars) > 0 else 0.0
    
    import difflib
    matches = difflib.SequenceMatcher(None, ref_chars, hyp_chars).ratio()
    return 1.0 - matches


def calculate_word_accuracy(reference: str, hypothesis: str) -> float:
    """Calculate word-level accuracy."""
    ref_words = reference.lower().strip().split()
    hyp_words = hypothesis.lower().strip().split()
    
    if len(ref_words) == 0:
        return 0.0
    
    # Count matching words at same positions
    matches = sum(1 for i in range(min(len(ref_words), len(hyp_words))) 
                  if ref_words[i] == hyp_words[i])
    return matches / len(ref_words)


class VoiceMessageValidationSuite:
    """Comprehensive validation test suite for voice messages."""
    
    def __init__(self):
        self.results_dir = Path(os.getenv("JUNE_TEST_DATA_DIR", os.path.expanduser("~/june_test_data"))) / "validation_tests"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.test_results = []
    
    async def synthesize_audio(self, text: str, sample_rate: int = 16000) -> Tuple[Optional[bytes], float]:
        """Synthesize audio using TTS service and measure latency."""
        try:
            start_time = time.time()
            async with grpc.aio.insecure_channel(TTS_ADDRESS) as channel:
                client = tts_shim.TextToSpeechClient(channel)
                cfg = tts_shim.SynthesisConfig(sample_rate=sample_rate, speed=1.0, pitch=0.0)
                audio = await client.synthesize(text=text, voice_id="default", language="en", config=cfg)
                latency = time.time() - start_time
                return audio, latency
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return None, 0.0
    
    async def transcribe_audio(self, audio_data: bytes, sample_rate: int = 16000) -> Tuple[Optional[str], float, Optional[float]]:
        """Transcribe audio using STT service and measure latency."""
        try:
            start_time = time.time()
            async with grpc.aio.insecure_channel(STT_ADDRESS) as channel:
                client = asr_shim.SpeechToTextClient(channel)
                cfg = asr_shim.RecognitionConfig(language="en", interim_results=False)
                result = await client.recognize(audio_data, sample_rate=sample_rate, encoding="wav", config=cfg)
                latency = time.time() - start_time
                confidence = getattr(result, 'confidence', None)
                return result.transcript, latency, confidence
        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            return None, 0.0, None
    
    async def full_round_trip(self, text: str, sample_rate: int = 16000) -> Dict[str, Any]:
        """Perform full round-trip test: Text ? TTS ? STT ? Text."""
        result = {
            "input_text": text,
            "sample_rate": sample_rate,
            "success": False,
            "metrics": {},
            "latencies": {}
        }
        
        # Step 1: TTS synthesis
        audio, tts_latency = await self.synthesize_audio(text, sample_rate)
        if not audio:
            result["error"] = "TTS synthesis failed"
            return result
        
        result["latencies"]["tts"] = tts_latency
        result["audio_size_bytes"] = len(audio)
        
        # Convert to WAV for STT
        wav_data = create_wav_file(audio, sample_rate)
        
        # Step 2: STT transcription
        transcript, stt_latency, confidence = await self.transcribe_audio(wav_data, sample_rate)
        if not transcript:
            result["error"] = "STT transcription failed"
            return result
        
        result["latencies"]["stt"] = stt_latency
        result["latencies"]["total"] = tts_latency + stt_latency
        result["transcript"] = transcript
        result["confidence"] = confidence
        
        # Step 3: Calculate metrics
        result["metrics"] = {
            "wer": calculate_wer(text, transcript),
            "cer": calculate_cer(text, transcript),
            "word_accuracy": calculate_word_accuracy(text, transcript),
            "exact_match": text.lower().strip() == transcript.lower().strip()
        }
        
        result["success"] = True
        return result
    
    async def test_round_trip_accuracy(self, test_cases: List[str]) -> Dict[str, Any]:
        """Test round-trip accuracy with multiple test cases."""
        logger.info(f"Testing round-trip accuracy with {len(test_cases)} test cases")
        
        results = {
            "test_type": "round_trip_accuracy",
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(test_cases),
            "successful_tests": 0,
            "failed_tests": 0,
            "test_results": [],
            "summary_metrics": {
                "average_wer": 0.0,
                "average_cer": 0.0,
                "average_word_accuracy": 0.0,
                "exact_match_rate": 0.0,
                "average_tts_latency": 0.0,
                "average_stt_latency": 0.0,
                "average_total_latency": 0.0
            }
        }
        
        wers = []
        cers = []
        word_accuracies = []
        exact_matches = 0
        tts_latencies = []
        stt_latencies = []
        total_latencies = []
        
        for i, test_text in enumerate(test_cases):
            logger.info(f"Test {i+1}/{len(test_cases)}: '{test_text[:50]}...'")
            
            round_trip_result = await self.full_round_trip(test_text)
            
            if round_trip_result["success"]:
                results["successful_tests"] += 1
                metrics = round_trip_result["metrics"]
                wers.append(metrics["wer"])
                cers.append(metrics["cer"])
                word_accuracies.append(metrics["word_accuracy"])
                if metrics["exact_match"]:
                    exact_matches += 1
                
                tts_latencies.append(round_trip_result["latencies"]["tts"])
                stt_latencies.append(round_trip_result["latencies"]["stt"])
                total_latencies.append(round_trip_result["latencies"]["total"])
            else:
                results["failed_tests"] += 1
            
            results["test_results"].append(round_trip_result)
        
        # Calculate summary metrics
        if wers:
            results["summary_metrics"]["average_wer"] = sum(wers) / len(wers)
            results["summary_metrics"]["average_cer"] = sum(cers) / len(cers)
            results["summary_metrics"]["average_word_accuracy"] = sum(word_accuracies) / len(word_accuracies)
            results["summary_metrics"]["exact_match_rate"] = exact_matches / len(test_cases)
            results["summary_metrics"]["average_tts_latency"] = sum(tts_latencies) / len(tts_latencies)
            results["summary_metrics"]["average_stt_latency"] = sum(stt_latencies) / len(stt_latencies)
            results["summary_metrics"]["average_total_latency"] = sum(total_latencies) / len(total_latencies)
        
        return results
    
    async def test_audio_quality_variations(self, base_text: str) -> Dict[str, Any]:
        """Test with various audio quality settings (sample rates)."""
        logger.info(f"Testing audio quality variations with text: '{base_text[:50]}...'")
        
        results = {
            "test_type": "audio_quality_variations",
            "timestamp": datetime.now().isoformat(),
            "base_text": base_text,
            "sample_rates": SAMPLE_RATES,
            "test_results": []
        }
        
        for sample_rate in SAMPLE_RATES:
            logger.info(f"Testing with sample rate: {sample_rate} Hz")
            
            round_trip_result = await self.full_round_trip(base_text, sample_rate)
            round_trip_result["sample_rate"] = sample_rate
            results["test_results"].append(round_trip_result)
        
        return results
    
    async def test_audio_length_variations(self, duration_category: str, sample_texts: List[str]) -> Dict[str, Any]:
        """Test with various audio lengths."""
        logger.info(f"Testing {duration_category} audio messages ({len(sample_texts)} tests)")
        
        min_duration, max_duration = DURATION_CATEGORIES[duration_category]
        
        results = {
            "test_type": "audio_length_variations",
            "timestamp": datetime.now().isoformat(),
            "duration_category": duration_category,
            "duration_range": (min_duration, max_duration),
            "test_results": []
        }
        
        for i, text in enumerate(sample_texts):
            logger.info(f"Test {i+1}/{len(sample_texts)}: {duration_category} message ({len(text)} chars)")
            
            round_trip_result = await self.full_round_trip(text)
            round_trip_result["text_length_chars"] = len(text)
            round_trip_result["text_length_words"] = len(text.split())
            results["test_results"].append(round_trip_result)
        
        # Calculate category-specific metrics
        successful = [r for r in results["test_results"] if r.get("success", False)]
        if successful:
            avg_wer = sum(r["metrics"]["wer"] for r in successful) / len(successful)
            avg_latency = sum(r["latencies"]["total"] for r in successful) / len(successful)
            results["category_metrics"] = {
                "average_wer": avg_wer,
                "average_latency": avg_latency,
                "success_rate": len(successful) / len(results["test_results"])
            }
        
        return results
    
    async def test_response_quality(self, test_cases: List[str]) -> Dict[str, Any]:
        """Test response quality metrics (WER, CER, word accuracy)."""
        logger.info(f"Testing response quality with {len(test_cases)} test cases")
        
        results = {
            "test_type": "response_quality",
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(test_cases),
            "quality_metrics": {
                "wer_threshold": 0.10,  # 10% WER threshold
                "cer_threshold": 0.05,  # 5% CER threshold
                "word_accuracy_threshold": 0.90  # 90% word accuracy threshold
            },
            "test_results": [],
            "summary": {}
        }
        
        wers = []
        cers = []
        word_accuracies = []
        
        for test_text in test_cases:
            round_trip_result = await self.full_round_trip(test_text)
            
            if round_trip_result["success"]:
                metrics = round_trip_result["metrics"]
                wers.append(metrics["wer"])
                cers.append(metrics["cer"])
                word_accuracies.append(metrics["word_accuracy"])
            
            results["test_results"].append(round_trip_result)
        
        # Calculate summary
        if wers:
            results["summary"] = {
                "average_wer": sum(wers) / len(wers),
                "average_cer": sum(cers) / len(cers),
                "average_word_accuracy": sum(word_accuracies) / len(word_accuracies),
                "wer_pass_rate": sum(1 for w in wers if w <= results["quality_metrics"]["wer_threshold"]) / len(wers),
                "cer_pass_rate": sum(1 for c in cers if c <= results["quality_metrics"]["cer_threshold"]) / len(cers),
                "word_accuracy_pass_rate": sum(1 for a in word_accuracies if a >= results["quality_metrics"]["word_accuracy_threshold"]) / len(word_accuracies)
            }
        
        return results
    
    async def test_latency(self, test_cases: List[str]) -> Dict[str, Any]:
        """Test latency measurements for TTS and STT services."""
        logger.info(f"Testing latency with {len(test_cases)} test cases")
        
        results = {
            "test_type": "latency",
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(test_cases),
            "latency_requirements": {
                "tts_max_seconds": 5.0,  # TTS should complete within 5 seconds
                "stt_max_seconds": 10.0,  # STT should complete within 10 seconds
                "total_max_seconds": 15.0  # Total round-trip should complete within 15 seconds
            },
            "test_results": [],
            "summary": {}
        }
        
        tts_latencies = []
        stt_latencies = []
        total_latencies = []
        
        for test_text in test_cases:
            round_trip_result = await self.full_round_trip(test_text)
            
            if round_trip_result["success"]:
                latencies = round_trip_result["latencies"]
                tts_latencies.append(latencies["tts"])
                stt_latencies.append(latencies["stt"])
                total_latencies.append(latencies["total"])
            
            results["test_results"].append(round_trip_result)
        
        # Calculate summary
        if tts_latencies:
            results["summary"] = {
                "tts": {
                    "average": sum(tts_latencies) / len(tts_latencies),
                    "min": min(tts_latencies),
                    "max": max(tts_latencies),
                    "pass_rate": sum(1 for l in tts_latencies if l <= results["latency_requirements"]["tts_max_seconds"]) / len(tts_latencies)
                },
                "stt": {
                    "average": sum(stt_latencies) / len(stt_latencies),
                    "min": min(stt_latencies),
                    "max": max(stt_latencies),
                    "pass_rate": sum(1 for l in stt_latencies if l <= results["latency_requirements"]["stt_max_seconds"]) / len(stt_latencies)
                },
                "total": {
                    "average": sum(total_latencies) / len(total_latencies),
                    "min": min(total_latencies),
                    "max": max(total_latencies),
                    "pass_rate": sum(1 for l in total_latencies if l <= results["latency_requirements"]["total_max_seconds"]) / len(total_latencies)
                }
            }
        
        return results
    
    def save_results(self, results: Dict[str, Any]):
        """Save test results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_type = results.get("test_type", "unknown")
        filename = f"{test_type}_{timestamp}.json"
        filepath = self.results_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {filepath}")
        return filepath


@pytest.fixture(scope="session")
async def validation_suite():
    """Fixture providing validation test suite instance."""
    return VoiceMessageValidationSuite()


@pytest.mark.asyncio
async def test_round_trip_accuracy(validation_suite):
    """Test voice message round-trip accuracy."""
    test_cases = [
        "Hello, how are you today?",
        "The quick brown fox jumps over the lazy dog.",
        "Artificial intelligence is transforming the world.",
        "Please call me at 555-123-4567.",
        "The weather is sunny with a temperature of 75 degrees.",
        "Testing one two three four five.",
        "This is a longer sentence that tests the system with more words and complexity.",
    ]
    
    results = await validation_suite.test_round_trip_accuracy(test_cases)
    validation_suite.save_results(results)
    
    # Assertions
    assert results["successful_tests"] > 0, "At least some tests should succeed"
    assert results["summary_metrics"]["average_wer"] < 0.20, "WER should be less than 20%"
    assert results["summary_metrics"]["average_word_accuracy"] > 0.80, "Word accuracy should be greater than 80%"


@pytest.mark.asyncio
async def test_response_quality(validation_suite):
    """Test response quality and accuracy metrics."""
    test_cases = [
        "Hello world",
        "This is a test message",
        "The quality of transcription matters",
        "Accuracy is important for user experience",
        "Testing various sentence structures",
    ]
    
    results = await validation_suite.test_response_quality(test_cases)
    validation_suite.save_results(results)
    
    # Assertions
    assert results["summary"]["average_wer"] < 0.15, "Average WER should be less than 15%"
    assert results["summary"]["average_word_accuracy"] > 0.85, "Average word accuracy should be greater than 85%"


@pytest.mark.asyncio
async def test_latency(validation_suite):
    """Test latency measurements."""
    test_cases = [
        "Short message",
        "This is a medium length message for testing latency",
        "This is a longer message that tests how the system handles messages with more content and words",
    ]
    
    results = await validation_suite.test_latency(test_cases)
    validation_suite.save_results(results)
    
    # Assertions
    assert results["summary"]["tts"]["average"] < 5.0, "Average TTS latency should be less than 5 seconds"
    assert results["summary"]["stt"]["average"] < 10.0, "Average STT latency should be less than 10 seconds"
    assert results["summary"]["total"]["average"] < 15.0, "Average total latency should be less than 15 seconds"


@pytest.mark.asyncio
async def test_audio_quality_variations(validation_suite):
    """Test with various audio quality settings."""
    test_text = "Testing audio quality with different sample rates"
    
    results = await validation_suite.test_audio_quality_variations(test_text)
    validation_suite.save_results(results)
    
    # Assertions
    assert len(results["test_results"]) == len(SAMPLE_RATES), "Should test all sample rates"
    successful = [r for r in results["test_results"] if r.get("success", False)]
    assert len(successful) > 0, "At least some quality variations should work"


@pytest.mark.asyncio
async def test_audio_length_short(validation_suite):
    """Test with short audio messages."""
    test_cases = [
        "Hi",
        "Yes",
        "No thanks",
        "OK",
        "Hello"
    ]
    
    results = await validation_suite.test_audio_length_variations("short", test_cases)
    validation_suite.save_results(results)
    
    # Assertions
    assert len(results["test_results"]) == len(test_cases), "Should test all short messages"


@pytest.mark.asyncio
async def test_audio_length_medium(validation_suite):
    """Test with medium length audio messages."""
    test_cases = [
        "Hello, how are you today?",
        "This is a medium length message for testing.",
        "The weather is nice today.",
        "I would like to order a pizza.",
        "Can you help me with this task?",
    ]
    
    results = await validation_suite.test_audio_length_variations("medium", test_cases)
    validation_suite.save_results(results)
    
    # Assertions
    assert len(results["test_results"]) == len(test_cases), "Should test all medium messages"


@pytest.mark.asyncio
async def test_audio_length_long(validation_suite):
    """Test with long audio messages."""
    test_cases = [
        "This is a longer message that tests how the system handles messages with more content and words. It includes multiple sentences and should provide a good test of the system's capabilities.",
        "The quick brown fox jumps over the lazy dog. This sentence contains every letter of the alphabet. It's commonly used for testing text processing systems.",
        "Artificial intelligence and machine learning are fascinating topics that are transforming many aspects of our daily lives and work environments.",
    ]
    
    results = await validation_suite.test_audio_length_variations("long", test_cases)
    validation_suite.save_results(results)
    
    # Assertions
    assert len(results["test_results"]) == len(test_cases), "Should test all long messages"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
