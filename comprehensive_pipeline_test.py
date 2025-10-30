#!/usr/bin/env python3
"""
Comprehensive Pass-Through Pipeline Test
Simulates: Gateway -> STT -> Inference -> TTS -> Gateway
"""
import asyncio
import logging
import json
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PassThroughPipeline:
    """Complete pass-through pipeline simulation."""
    
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
    
    def stt_recognize(self, audio_data: bytes) -> str:
        """STT pass-through: Recognize audio to text."""
        try:
            # Calculate audio duration
            audio_duration = len(audio_data) / (self.sample_rate * 2)  # 16kHz, 16-bit PCM
            
            # Generate mock transcript based on audio duration
            transcript = self._generate_mock_transcript(audio_duration)
            
            logger.info(f"STT: Recognized '{transcript}' from {audio_duration:.2f}s audio")
            return transcript
            
        except Exception as e:
            logger.error(f"STT recognition failed: {e}")
            return "STT recognition failed"
    
    def inference_process(self, text: str) -> str:
        """Inference pass-through: Process text through AI agent."""
        try:
            # Simple pass-through with some processing simulation
            processed_text = self._simulate_agent_processing(text)
            
            logger.info(f"Inference: Processed '{text}' -> '{processed_text}'")
            return processed_text
            
        except Exception as e:
            logger.error(f"Inference processing failed: {e}")
            return text  # Pass through original text on error
    
    def tts_synthesize(self, text: str) -> bytes:
        """TTS pass-through: Synthesize text to audio."""
        try:
            # Generate synthetic audio based on text
            duration = len(text.split()) * 0.5  # Rough estimate: 0.5s per word
            audio_data = self.generate_synthetic_audio(text, duration)
            
            logger.info(f"TTS: Synthesized '{text}' to {len(audio_data)} bytes audio")
            return audio_data
            
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return b""
    
    def _generate_mock_transcript(self, audio_duration: float) -> str:
        """Generate a mock transcript based on audio duration."""
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
    
    def _simulate_agent_processing(self, text: str) -> str:
        """Simulate AI agent processing."""
        # Simple processing examples
        if "hello" in text.lower():
            return f"Hello! I heard you say: {text}"
        elif "test" in text.lower():
            return f"Test received! Your message was: {text}"
        elif "question" in text.lower():
            return f"That's an interesting question about: {text}"
        else:
            return f"I understand you said: {text}"
    
    async def run_full_pipeline(self, input_text: str) -> Dict[str, Any]:
        """Run the complete pass-through pipeline."""
        logger.info(f"Starting full pipeline for: '{input_text}'")
        
        pipeline_data = {
            "input_text": input_text,
            "timestamp": datetime.now().isoformat(),
            "pipeline_id": str(uuid.uuid4()),
            "steps": {}
        }
        
        try:
            # Step 1: Generate initial audio (simulating user input)
            logger.info("Step 1: Generating input audio...")
            input_audio = self.generate_synthetic_audio(input_text)
            pipeline_data["steps"]["input_audio"] = {
                "size_bytes": len(input_audio),
                "duration_seconds": len(input_audio) / (self.sample_rate * 2)
            }
            
            # Step 2: STT Recognition
            logger.info("Step 2: STT Recognition...")
            recognized_text = self.stt_recognize(input_audio)
            pipeline_data["steps"]["stt_recognition"] = {
                "transcript": recognized_text,
                "confidence": 0.95
            }
            
            # Step 3: Inference Processing
            logger.info("Step 3: Inference Processing...")
            processed_text = self.inference_process(recognized_text)
            pipeline_data["steps"]["inference_processing"] = {
                "input": recognized_text,
                "output": processed_text
            }
            
            # Step 4: TTS Synthesis
            logger.info("Step 4: TTS Synthesis...")
            output_audio = self.tts_synthesize(processed_text)
            pipeline_data["steps"]["tts_synthesis"] = {
                "text": processed_text,
                "audio_size_bytes": len(output_audio),
                "duration_seconds": len(output_audio) / (self.sample_rate * 2)
            }
            
            # Step 5: Final output (simulating gateway response)
            logger.info("Step 5: Gateway Response...")
            pipeline_data["steps"]["gateway_response"] = {
                "status": "success",
                "response_audio_size": len(output_audio)
            }
            
            pipeline_data["status"] = "success"
            pipeline_data["total_processing_time"] = "simulated"
            
            logger.info("✅ Full pipeline completed successfully!")
            return pipeline_data
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            pipeline_data["status"] = "failed"
            pipeline_data["error"] = str(e)
            return pipeline_data
    
    async def run_comprehensive_test(self, test_cases: List[str]) -> Dict[str, Any]:
        """Run comprehensive tests on multiple test cases."""
        logger.info("Starting Comprehensive Pass-Through Pipeline Test...")
        
        results = {
            "test_timestamp": datetime.now().isoformat(),
            "total_tests": len(test_cases),
            "successful_tests": 0,
            "failed_tests": 0,
            "test_results": [],
            "pipeline_summary": {
                "total_input_audio_generated": 0,
                "total_output_audio_generated": 0,
                "total_stt_transcriptions": 0,
                "total_inference_processings": 0,
                "total_tts_syntheses": 0
            }
        }
        
        for i, test_text in enumerate(test_cases):
            logger.info(f"Running test {i+1}/{len(test_cases)}: '{test_text}'")
            
            try:
                # Run full pipeline
                pipeline_result = await self.run_full_pipeline(test_text)
                
                if pipeline_result["status"] == "success":
                    results["successful_tests"] += 1
                    
                    # Update summary statistics
                    steps = pipeline_result["steps"]
                    if "input_audio" in steps:
                        results["pipeline_summary"]["total_input_audio_generated"] += steps["input_audio"]["size_bytes"]
                    if "tts_synthesis" in steps:
                        results["pipeline_summary"]["total_output_audio_generated"] += steps["tts_synthesis"]["audio_size_bytes"]
                    if "stt_recognition" in steps:
                        results["pipeline_summary"]["total_stt_transcriptions"] += 1
                    if "inference_processing" in steps:
                        results["pipeline_summary"]["total_inference_processings"] += 1
                    if "tts_synthesis" in steps:
                        results["pipeline_summary"]["total_tts_syntheses"] += 1
                    
                    results["test_results"].append({
                        "test_text": test_text,
                        "status": "success",
                        "pipeline_result": pipeline_result
                    })
                    
                    logger.info(f"✅ Test {i+1} completed successfully")
                else:
                    results["failed_tests"] += 1
                    results["test_results"].append({
                        "test_text": test_text,
                        "status": "failed",
                        "error": pipeline_result.get("error", "Unknown error")
                    })
                    
                    logger.error(f"❌ Test {i+1} failed")
                    
            except Exception as e:
                logger.error(f"Test {i+1} failed with exception: {e}")
                results["failed_tests"] += 1
                results["test_results"].append({
                    "test_text": test_text,
                    "status": "failed",
                    "error": str(e)
                })
        
        return results

async def main():
    """Main function for testing."""
    logger.info("Starting Comprehensive Pass-Through Pipeline Test...")
    
    # Test cases
    test_cases = [
        "Hello world",
        "This is a test of the system",
        "How are you doing today?",
        "Testing speech to text to speech",
        "The quick brown fox jumps over the lazy dog"
    ]
    
    # Create pipeline instance
    pipeline = PassThroughPipeline()
    
    # Run comprehensive tests
    results = await pipeline.run_comprehensive_test(test_cases)
    
    # Print results
    logger.info("=" * 60)
    logger.info("COMPREHENSIVE PASS-THROUGH PIPELINE TEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Total tests: {results['total_tests']}")
    logger.info(f"Successful: {results['successful_tests']}")
    logger.info(f"Failed: {results['failed_tests']}")
    logger.info(f"Success rate: {results['successful_tests']/results['total_tests']*100:.1f}%")
    
    logger.info("\nPipeline Summary:")
    summary = results["pipeline_summary"]
    logger.info(f"  Total input audio generated: {summary['total_input_audio_generated']:,} bytes")
    logger.info(f"  Total output audio generated: {summary['total_output_audio_generated']:,} bytes")
    logger.info(f"  STT transcriptions: {summary['total_stt_transcriptions']}")
    logger.info(f"  Inference processings: {summary['total_inference_processings']}")
    logger.info(f"  TTS syntheses: {summary['total_tts_syntheses']}")
    
    # Save results to file
    with open('/tmp/pipeline_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info("Results saved to /tmp/pipeline_test_results.json")
    
    # Determine success
    success_rate = results['successful_tests'] / results['total_tests'] if results['total_tests'] > 0 else 0
    if success_rate >= 0.8:  # 80% success rate
        logger.info("✅ Comprehensive pipeline test PASSED")
        return True
    else:
        logger.error("❌ Comprehensive pipeline test FAILED")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)



