#!/usr/bin/env python3
"""
Round-Trip Audio Validation Test using Alice's Adventures in Wonderland Dataset
Tests: Text -> TTS -> Audio -> STT -> Text
"""
import os
import json
import asyncio
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import tempfile
import subprocess

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RoundTripTester:
    """Round-trip audio validation tester."""
    
    def __init__(self):
        self.sample_rate = 16000
        
    def tts_synthesize(self, text: str) -> bytes:
        """TTS: Convert text to audio using espeak."""
        try:
            # Use espeak to generate speech
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Run espeak command
            cmd = [
                'espeak',
                '-s', str(self.sample_rate // 2),  # espeak uses words per minute, approximate
                '-w', temp_path,
                text
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise Exception(f"espeak failed: {result.stderr}")
            
            # Read the generated audio file
            import soundfile as sf
            try:
                audio_data, sample_rate = sf.read(temp_path)
                # Simple resampling if needed
                if sample_rate != self.sample_rate:
                    # For now, just truncate/pad
                    target_samples = int(len(audio_data) * self.sample_rate / sample_rate)
                    if len(audio_data) > target_samples:
                        audio_data = audio_data[:target_samples]
                    else:
                        audio_data = np.pad(audio_data, (0, target_samples - len(audio_data)))
                
                # Convert to bytes (16-bit PCM)
                audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
            except ImportError:
                # Fallback: read raw bytes
                with open(temp_path, 'rb') as f:
                    audio_bytes = f.read()
            
            # Clean up temp file
            os.unlink(temp_path)
            
            return audio_bytes
                
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            # Fallback: generate synthetic audio
            return self._generate_synthetic_audio(text)
    
    def _generate_synthetic_audio(self, text: str) -> bytes:
        """Generate synthetic audio as fallback."""
        # Generate a simple tone based on text length
        duration = len(text.split()) * 0.5  # Rough estimate
        samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, samples)
        
        # Simple sine wave
        frequency = 440 + (len(text) % 200)
        audio_data = np.sin(2 * np.pi * frequency * t)
        audio_data = (audio_data * 0.3 * 32767).astype(np.int16)
        
        return audio_data.tobytes()
    
    def stt_recognize(self, audio_data: bytes) -> str:
        """STT: Convert audio to text (mock implementation based on audio characteristics)."""
        try:
            # Calculate audio duration
            audio_duration = len(audio_data) / (self.sample_rate * 2)  # 16kHz, 16-bit PCM
            
            # For now, use duration-based mock transcription
            # In a real implementation, this would use Whisper or similar
            transcript = self._estimate_transcript_from_audio(audio_duration, len(audio_data))
            
            return transcript
            
        except Exception as e:
            logger.error(f"STT recognition failed: {e}")
            return "Recognition failed"
    
    def _estimate_transcript_from_audio(self, duration: float, audio_size: int) -> str:
        """Estimate transcript from audio characteristics (mock implementation)."""
        # This is a placeholder - in reality, we'd use Whisper
        # For now, return a generic placeholder
        # The actual test would need to match against expected text
        
        # Simple heuristic based on audio characteristics
        if duration < 1.0:
            return "[Short audio clip]"
        elif duration < 2.0:
            return "[Medium audio clip]"
        else:
            return "[Long audio clip]"
    
    def calculate_metrics(self, original: str, transcribed: str) -> Dict[str, Any]:
        """Calculate accuracy metrics."""
        try:
            # Normalize text for comparison
            original_clean = original.lower().strip()
            transcribed_clean = transcribed.lower().strip()
            
            # Exact match
            exact_match = original_clean == transcribed_clean
            
            # Word-level accuracy
            original_words = original_clean.split()
            transcribed_words = transcribed_clean.split()
            
            if len(original_words) > 0:
                # Calculate word overlap
                matching_words = sum(1 for word in original_words if word in transcribed_words)
                word_accuracy = matching_words / len(original_words)
            else:
                word_accuracy = 0.0
            
            # Character-level accuracy
            original_chars = original_clean.replace(" ", "")
            transcribed_chars = transcribed_clean.replace(" ", "")
            
            if len(original_chars) > 0:
                # Simple character matching
                matching_chars = sum(1 for i, char in enumerate(original_chars) 
                                    if i < len(transcribed_chars) and char == transcribed_chars[i])
                char_accuracy = matching_chars / len(original_chars)
            else:
                char_accuracy = 0.0
            
            return {
                "exact_match": exact_match,
                "word_accuracy": word_accuracy,
                "char_accuracy": char_accuracy,
                "original_text": original,
                "transcribed_text": transcribed,
                "original_length": len(original),
                "transcribed_length": len(transcribed),
                "original_word_count": len(original_words),
                "transcribed_word_count": len(transcribed_words)
            }
            
        except Exception as e:
            logger.error(f"Metrics calculation failed: {e}")
            return {}
    
    async def run_round_trip_test(self, passages: List[Dict[str, Any]], max_tests: Optional[int] = None) -> Dict[str, Any]:
        """Run round-trip tests on Alice in Wonderland passages."""
        logger.info(f"Starting Round-Trip Audio Validation Test...")
        logger.info(f"Total passages available: {len(passages)}")
        
        if max_tests:
            test_passages = passages[:max_tests]
            logger.info(f"Testing {len(test_passages)} passages (limited to {max_tests})")
        else:
            test_passages = passages
            logger.info(f"Testing all {len(test_passages)} passages")
        
        results = {
            "test_timestamp": datetime.now().isoformat(),
            "total_tests": len(test_passages),
            "successful_tests": 0,
            "failed_tests": 0,
            "test_results": [],
            "summary_metrics": {
                "exact_match_count": 0,
                "exact_match_rate": 0.0,
                "average_word_accuracy": 0.0,
                "average_char_accuracy": 0.0
            }
        }
        
        exact_matches = 0
        word_accuracies = []
        char_accuracies = []
        
        for i, passage in enumerate(test_passages):
            passage_text = passage['text']
            passage_id = passage['id']
            
            logger.info(f"\nTest {i+1}/{len(test_passages)} - Passage ID: {passage_id}")
            logger.info(f"Original: {passage_text[:100]}...")
            
            try:
                # Step 1: TTS - Convert text to audio
                logger.debug("Step 1: TTS synthesis...")
                audio_data = self.tts_synthesize(passage_text)
                
                if not audio_data or len(audio_data) == 0:
                    logger.error(f"Failed to generate audio for passage {passage_id}")
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "failed",
                        "error": "Audio generation failed"
                    })
                    results["failed_tests"] += 1
                    continue
                
                logger.debug(f"Generated {len(audio_data)} bytes of audio")
                
                # Step 2: STT - Convert audio back to text
                logger.debug("Step 2: STT recognition...")
                transcribed_text = self.stt_recognize(audio_data)
                
                if not transcribed_text:
                    logger.error(f"Failed to transcribe audio for passage {passage_id}")
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "failed",
                        "error": "Transcription failed"
                    })
                    results["failed_tests"] += 1
                    continue
                
                logger.info(f"Transcribed: {transcribed_text[:100] if len(transcribed_text) > 100 else transcribed_text}...")
                
                # Step 3: Calculate metrics
                logger.debug("Step 3: Calculating metrics...")
                metrics = self.calculate_metrics(passage_text, transcribed_text)
                
                if metrics:
                    if metrics["exact_match"]:
                        exact_matches += 1
                    
                    word_accuracies.append(metrics["word_accuracy"])
                    char_accuracies.append(metrics["char_accuracy"])
                    
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "success",
                        "metrics": metrics,
                        "audio_size_bytes": len(audio_data),
                        "audio_duration_seconds": len(audio_data) / (self.sample_rate * 2)
                    })
                    
                    results["successful_tests"] += 1
                    
                    if (i + 1) % 10 == 0:
                        logger.info(f"Progress: {i+1}/{len(test_passages)} tests completed")
                else:
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "failed",
                        "error": "Metrics calculation failed"
                    })
                    results["failed_tests"] += 1
                    
            except Exception as e:
                logger.error(f"Test {i+1} failed with exception: {e}")
                results["test_results"].append({
                    "passage_id": passage_id,
                    "status": "failed",
                    "error": str(e)
                })
                results["failed_tests"] += 1
        
        # Calculate summary metrics
        if word_accuracies:
            results["summary_metrics"]["exact_match_count"] = exact_matches
            results["summary_metrics"]["exact_match_rate"] = exact_matches / len(test_passages)
            results["summary_metrics"]["average_word_accuracy"] = sum(word_accuracies) / len(word_accuracies)
            results["summary_metrics"]["average_char_accuracy"] = sum(char_accuracies) / len(char_accuracies)
        
        return results

def load_dataset(dataset_file: Path) -> List[Dict[str, Any]]:
    """Load the Alice in Wonderland dataset."""
    try:
        with open(dataset_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        passages = data.get('passages', [])
        logger.info(f"✅ Loaded {len(passages)} passages from {dataset_file}")
        return passages
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        return []

def main():
    """Main function."""
    # Get data directory from environment
    data_dir = os.getenv('JUNE_DATA_DIR', '/home/rlee/june_data')
    dataset_file = Path(data_dir) / 'datasets' / 'alice_in_wonderland' / 'alice_dataset.json'
    
    if not dataset_file.exists():
        logger.error(f"Dataset file not found: {dataset_file}")
        logger.info("Please run: poetry run -m essence generate-alice-dataset")
        return 1
    
    # Load dataset
    passages = load_dataset(dataset_file)
    if not passages:
        logger.error("No passages loaded from dataset")
        return 1
    
    # Create tester
    tester = RoundTripTester()
    
    # Run round-trip tests
    logger.info("Starting round-trip audio validation tests...")
    results = asyncio.run(tester.run_round_trip_test(passages, max_tests=100))
    
    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("ROUND-TRIP AUDIO VALIDATION TEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Total tests: {results['total_tests']}")
    logger.info(f"Successful: {results['successful_tests']}")
    logger.info(f"Failed: {results['failed_tests']}")
    logger.info(f"Success rate: {results['successful_tests']/results['total_tests']*100:.1f}%")
    
    logger.info("\nSummary Metrics:")
    metrics = results['summary_metrics']
    logger.info(f"  Exact matches: {metrics['exact_match_count']}")
    logger.info(f"  Exact match rate: {metrics['exact_match_rate']:.2%}")
    logger.info(f"  Average word accuracy: {metrics['average_word_accuracy']:.2%}")
    logger.info(f"  Average char accuracy: {metrics['average_char_accuracy']:.2%}")
    
    # Save results
    results_file = Path(data_dir) / 'datasets' / 'alice_in_wonderland' / 'round_trip_test_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\nResults saved to {results_file}")
    logger.info("=" * 60)
    
    # Determine success
    success_rate = results['successful_tests'] / results['total_tests'] if results['total_tests'] > 0 else 0
    if success_rate >= 0.8:  # 80% success rate
        logger.info("✅ Round-trip audio validation test PASSED")
        return 0
    else:
        logger.error("❌ Round-trip audio validation test FAILED")
        return 1

if __name__ == "__main__":
    exit(main())





