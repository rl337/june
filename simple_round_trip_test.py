#!/usr/bin/env python3
"""
Simple Round-Trip Audio Test - generates synthetic audio and tests STT.
"""
import asyncio
import logging
import numpy as np
import tempfile
import os
import json
from datetime import datetime

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleRoundTripTest:
    """Simple round-trip test for TTS -> STT."""
    
    def __init__(self):
        self.sample_rate = 16000
        
    def generate_synthetic_audio(self, text: str, duration: float = 2.0) -> bytes:
        """Generate synthetic audio data for testing."""
        try:
            # Generate a simple sine wave with some variation
            t = np.linspace(0, duration, int(self.sample_rate * duration))
            
            # Create a simple tone that varies based on text length
            frequency = 440 + (len(text) % 200)  # Vary frequency based on text
            audio_data = np.sin(2 * np.pi * frequency * t)
            
            # Add some amplitude variation
            amplitude = 0.3 + 0.2 * np.sin(2 * np.pi * 0.5 * t)
            audio_data = audio_data * amplitude
            
            # Convert to 16-bit PCM
            audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
            
            logger.info(f"Generated {len(audio_bytes)} bytes of synthetic audio")
            return audio_bytes
            
        except Exception as e:
            logger.error(f"Audio generation failed: {e}")
            return b""
    
    def simulate_stt_transcription(self, audio_data: bytes, original_text: str) -> str:
        """Simulate STT transcription with some realistic errors."""
        try:
            # Simulate transcription with some common errors
            # This is a mock implementation for testing the round-trip concept
            
            # Add some realistic transcription variations
            variations = {
                "Hello": ["Hello", "Hi", "Hey"],
                "world": ["world", "word", "work"],
                "test": ["test", "text", "best"],
                "system": ["system", "systems", "system"],
                "this": ["this", "that", "the"],
                "is": ["is", "it's", "its"],
                "a": ["a", "an", "the"]
            }
            
            words = original_text.lower().split()
            transcribed_words = []
            
            for word in words:
                # Remove punctuation for matching
                clean_word = word.strip('.,!?')
                if clean_word in variations:
                    # Choose a variation (simulate transcription errors)
                    transcribed_words.append(variations[clean_word][0])  # Use first option for now
                else:
                    transcribed_words.append(clean_word)
            
            transcribed_text = " ".join(transcribed_words)
            logger.info(f"Simulated transcription: '{transcribed_text}'")
            return transcribed_text
            
        except Exception as e:
            logger.error(f"STT simulation failed: {e}")
            return ""
    
    def calculate_metrics(self, original: str, transcribed: str) -> dict:
        """Calculate accuracy metrics."""
        try:
            original_words = original.lower().split()
            transcribed_words = transcribed.lower().split()
            
            # Exact match
            exact_match = original.lower() == transcribed.lower()
            
            # Word-level accuracy
            if len(original_words) > 0:
                word_accuracy = sum(1 for i, word in enumerate(original_words) 
                                  if i < len(transcribed_words) and word == transcribed_words[i]) / len(original_words)
            else:
                word_accuracy = 0.0
            
            # Character-level accuracy
            original_chars = original.lower().replace(" ", "")
            transcribed_chars = transcribed.lower().replace(" ", "")
            
            if len(original_chars) > 0:
                char_accuracy = sum(1 for i, char in enumerate(original_chars) 
                                  if i < len(transcribed_chars) and char == transcribed_chars[i]) / len(original_chars)
            else:
                char_accuracy = 0.0
            
            return {
                "exact_match": exact_match,
                "word_accuracy": word_accuracy,
                "char_accuracy": char_accuracy,
                "original_text": original,
                "transcribed_text": transcribed,
                "original_word_count": len(original_words),
                "transcribed_word_count": len(transcribed_words)
            }
            
        except Exception as e:
            logger.error(f"Metrics calculation failed: {e}")
            return {}
    
    async def run_round_trip_test(self, test_cases: list) -> dict:
        """Run round-trip tests on multiple test cases."""
        logger.info("Starting Round-Trip Audio Test...")
        
        results = {
            "test_timestamp": datetime.now().isoformat(),
            "total_tests": len(test_cases),
            "successful_tests": 0,
            "failed_tests": 0,
            "test_results": [],
            "overall_metrics": {
                "exact_match_rate": 0.0,
                "average_word_accuracy": 0.0,
                "average_char_accuracy": 0.0
            }
        }
        
        exact_matches = 0
        word_accuracies = []
        char_accuracies = []
        
        for i, test_text in enumerate(test_cases):
            logger.info(f"Running test {i+1}/{len(test_cases)}: '{test_text}'")
            
            try:
                # Step 1: Generate audio (TTS simulation)
                audio_data = self.generate_synthetic_audio(test_text)
                
                if not audio_data:
                    logger.error(f"Failed to generate audio for: {test_text}")
                    results["test_results"].append({
                        "test_text": test_text,
                        "status": "failed",
                        "error": "Audio generation failed"
                    })
                    results["failed_tests"] += 1
                    continue
                
                # Step 2: Transcribe audio (STT simulation)
                transcribed_text = self.simulate_stt_transcription(audio_data, test_text)
                
                if not transcribed_text:
                    logger.error(f"Failed to transcribe audio for: {test_text}")
                    results["test_results"].append({
                        "test_text": test_text,
                        "status": "failed",
                        "error": "Transcription failed"
                    })
                    results["failed_tests"] += 1
                    continue
                
                # Step 3: Calculate metrics
                metrics = self.calculate_metrics(test_text, transcribed_text)
                
                if metrics:
                    exact_matches += 1 if metrics["exact_match"] else 0
                    word_accuracies.append(metrics["word_accuracy"])
                    char_accuracies.append(metrics["char_accuracy"])
                    
                    results["test_results"].append({
                        "test_text": test_text,
                        "transcribed_text": transcribed_text,
                        "status": "success",
                        "metrics": metrics
                    })
                    results["successful_tests"] += 1
                    
                    logger.info(f"✅ Test {i+1} completed - Word accuracy: {metrics['word_accuracy']:.2f}")
                else:
                    results["test_results"].append({
                        "test_text": test_text,
                        "status": "failed",
                        "error": "Metrics calculation failed"
                    })
                    results["failed_tests"] += 1
                    
            except Exception as e:
                logger.error(f"Test {i+1} failed with error: {e}")
                results["test_results"].append({
                    "test_text": test_text,
                    "status": "failed",
                    "error": str(e)
                })
                results["failed_tests"] += 1
        
        # Calculate overall metrics
        if word_accuracies:
            results["overall_metrics"]["exact_match_rate"] = exact_matches / len(test_cases)
            results["overall_metrics"]["average_word_accuracy"] = sum(word_accuracies) / len(word_accuracies)
            results["overall_metrics"]["average_char_accuracy"] = sum(char_accuracies) / len(char_accuracies)
        
        return results

async def main():
    """Main function for testing."""
    logger.info("Starting Simple Round-Trip Audio Test...")
    
    # Test cases
    test_cases = [
        "Hello world",
        "This is a test",
        "The quick brown fox",
        "Testing one two three",
        "Audio processing test"
    ]
    
    # Create test instance
    test = SimpleRoundTripTest()
    
    # Run tests
    results = await test.run_round_trip_test(test_cases)
    
    # Print results
    logger.info("=" * 50)
    logger.info("ROUND-TRIP TEST RESULTS")
    logger.info("=" * 50)
    logger.info(f"Total tests: {results['total_tests']}")
    logger.info(f"Successful: {results['successful_tests']}")
    logger.info(f"Failed: {results['failed_tests']}")
    logger.info(f"Exact match rate: {results['overall_metrics']['exact_match_rate']:.2%}")
    logger.info(f"Average word accuracy: {results['overall_metrics']['average_word_accuracy']:.2%}")
    logger.info(f"Average char accuracy: {results['overall_metrics']['average_char_accuracy']:.2%}")
    
    # Save results to file
    with open('/tmp/round_trip_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info("Results saved to /tmp/round_trip_test_results.json")
    
    # Determine success
    success_rate = results['successful_tests'] / results['total_tests'] if results['total_tests'] > 0 else 0
    if success_rate >= 0.8:  # 80% success rate
        logger.info("✅ Round-trip test PASSED")
        return True
    else:
        logger.error("❌ Round-trip test FAILED")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)





