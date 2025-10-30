#!/usr/bin/env python3
"""
Round-Trip Audio Validation Test using Alice's Adventures in Wonderland Dataset
Tests against REAL STT/TTS services via gRPC: Text -> TTS -> Audio -> STT -> Text
"""
import os
import json
import asyncio
import logging
import grpc
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import protobuf classes
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'proto'))

try:
    from tts_pb2 import SynthesisRequest, SynthesisConfig, AudioResponse
    import tts_pb2_grpc
    from asr_pb2 import RecognitionRequest, RecognitionResponse
    import asr_pb2_grpc
except ImportError as e:
    logger.error(f"Failed to import protobuf classes: {e}")
    logger.error("Make sure proto Python files are generated: python3 -m grpc_tools.protoc --python_out=proto --grpc_python_out=proto --proto_path=proto proto/*.proto")
    sys.exit(1)

class RealRoundTripTester:
    """Round-trip audio validation tester using real gRPC services."""
    
    def __init__(self, tts_address: str = "localhost:50053", stt_address: str = "localhost:50052"):
        self.tts_address = tts_address
        self.stt_address = stt_address
        self.sample_rate = 16000
        
    async def tts_synthesize(self, text: str) -> bytes:
        """TTS: Convert text to audio using real TTS gRPC service."""
        try:
            async with grpc.aio.insecure_channel(self.tts_address) as channel:
                stub = tts_pb2_grpc.TextToSpeechStub(channel)
                
                # Create synthesis request
                config = SynthesisConfig(
                    sample_rate=self.sample_rate,
                    speed=1.0,
                    pitch=0.0
                )
                
                request = SynthesisRequest(
                    text=text,
                    config=config,
                    voice_id="default",
                    language="en"
                )
                
                # Call TTS service
                logger.debug(f"Calling TTS service at {self.tts_address}...")
                response = await stub.Synthesize(request, timeout=30.0)
                
                if response.audio_data:
                    logger.debug(f"Received {len(response.audio_data)} bytes of audio from TTS")
                    return response.audio_data
                else:
                    logger.error("TTS service returned empty audio")
                    return b""
                    
        except grpc.RpcError as e:
            logger.error(f"TTS gRPC error: {e.code()} - {e.details()}")
            return b""
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return b""
    
    async def stt_recognize(self, audio_data: bytes) -> str:
        """STT: Convert audio to text using real STT gRPC service."""
        try:
            async with grpc.aio.insecure_channel(self.stt_address) as channel:
                stub = asr_pb2_grpc.SpeechRecognitionStub(channel)
                
                # Create recognition request
                request = RecognitionRequest(
                    audio_data=audio_data,
                    config=None,  # Use default config
                    language="en"
                )
                
                # Call STT service
                logger.debug(f"Calling STT service at {self.stt_address}...")
                response = await stub.Recognize(request, timeout=30.0)
                
                if response.results and len(response.results) > 0:
                    # Get the first result
                    result = response.results[0]
                    transcript = result.transcript
                    confidence = result.confidence
                    logger.debug(f"STT recognized: '{transcript}' (confidence: {confidence:.2f})")
                    return transcript
                else:
                    logger.error("STT service returned no results")
                    return ""
                    
        except grpc.RpcError as e:
            logger.error(f"STT gRPC error: {e.code()} - {e.details()}")
            return ""
        except Exception as e:
            logger.error(f"STT recognition failed: {e}")
            return ""
    
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
                # Calculate word overlap (simple approach)
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
    
    async def test_connectivity(self) -> bool:
        """Test connectivity to TTS and STT services."""
        logger.info("Testing connectivity to services...")
        
        # Test TTS
        try:
            async with grpc.aio.insecure_channel(self.tts_address) as channel:
                stub = tts_pb2_grpc.TextToSpeechStub(channel)
                from tts_pb2 import HealthRequest
                health = await stub.HealthCheck(HealthRequest(), timeout=5.0)
                if health.healthy:
                    logger.info(f"✅ TTS service is healthy at {self.tts_address}")
                else:
                    logger.error(f"❌ TTS service is unhealthy at {self.tts_address}")
                    return False
        except Exception as e:
            logger.error(f"❌ Cannot connect to TTS service at {self.tts_address}: {e}")
            return False
        
        # Test STT
        try:
            async with grpc.aio.insecure_channel(self.stt_address) as channel:
                stub = asr_pb2_grpc.SpeechRecognitionStub(channel)
                from asr_pb2 import HealthRequest
                health = await stub.HealthCheck(HealthRequest(), timeout=5.0)
                if health.healthy:
                    logger.info(f"✅ STT service is healthy at {self.stt_address}")
                else:
                    logger.error(f"❌ STT service is unhealthy at {self.stt_address}")
                    return False
        except Exception as e:
            logger.error(f"❌ Cannot connect to STT service at {self.stt_address}: {e}")
            return False
        
        return True
    
    async def run_round_trip_test(self, passages: List[Dict[str, Any]], max_tests: Optional[int] = None) -> Dict[str, Any]:
        """Run round-trip tests on Alice in Wonderland passages."""
        logger.info(f"Starting REAL Round-Trip Audio Validation Test...")
        logger.info(f"Total passages available: {len(passages)}")
        
        # Test connectivity first
        if not await self.test_connectivity():
            logger.error("Services are not available. Please ensure STT and TTS services are running in Docker.")
            return {
                "test_timestamp": datetime.now().isoformat(),
                "status": "failed",
                "error": "Services not available"
            }
        
        if max_tests:
            test_passages = passages[:max_tests]
            logger.info(f"Testing {len(test_passages)} passages (limited to {max_tests})")
        else:
            test_passages = passages
            logger.info(f"Testing all {len(test_passages)} passages")
        
        results = {
            "test_timestamp": datetime.now().isoformat(),
            "service_addresses": {
                "tts": self.tts_address,
                "stt": self.stt_address
            },
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
                logger.info(f"  Step 1: TTS synthesis...")
                audio_data = await self.tts_synthesize(passage_text)
                
                if not audio_data or len(audio_data) == 0:
                    logger.error(f"  ❌ Failed to generate audio for passage {passage_id}")
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "failed",
                        "error": "Audio generation failed"
                    })
                    results["failed_tests"] += 1
                    continue
                
                logger.info(f"  ✅ Generated {len(audio_data)} bytes of audio")
                
                # Step 2: STT - Convert audio back to text
                logger.info(f"  Step 2: STT recognition...")
                transcribed_text = await self.stt_recognize(audio_data)
                
                if not transcribed_text:
                    logger.error(f"  ❌ Failed to transcribe audio for passage {passage_id}")
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "failed",
                        "error": "Transcription failed"
                    })
                    results["failed_tests"] += 1
                    continue
                
                logger.info(f"  ✅ Transcribed: {transcribed_text[:100] if len(transcribed_text) > 100 else transcribed_text}...")
                
                # Step 3: Calculate metrics
                logger.info(f"  Step 3: Calculating metrics...")
                metrics = self.calculate_metrics(passage_text, transcribed_text)
                
                if metrics:
                    if metrics["exact_match"]:
                        exact_matches += 1
                        logger.info(f"  🎉 EXACT MATCH!")
                    
                    word_accuracies.append(metrics["word_accuracy"])
                    char_accuracies.append(metrics["char_accuracy"])
                    
                    logger.info(f"  Word accuracy: {metrics['word_accuracy']:.2%}, Char accuracy: {metrics['char_accuracy']:.2%}")
                    
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "success",
                        "metrics": metrics,
                        "audio_size_bytes": len(audio_data),
                        "audio_duration_seconds": len(audio_data) / (self.sample_rate * 2)
                    })
                    
                    results["successful_tests"] += 1
                    
                    if (i + 1) % 10 == 0:
                        logger.info(f"\nProgress: {i+1}/{len(test_passages)} tests completed")
                else:
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "failed",
                        "error": "Metrics calculation failed"
                    })
                    results["failed_tests"] += 1
                    
            except Exception as e:
                logger.error(f"  ❌ Test {i+1} failed with exception: {e}")
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
        logger.info("Please run scripts/generate_alice_dataset.py first")
        return 1
    
    # Load dataset
    passages = load_dataset(dataset_file)
    if not passages:
        logger.error("No passages loaded from dataset")
        return 1
    
    # Service addresses
    tts_address = os.getenv('TTS_SERVICE_ADDRESS', 'localhost:50053')
    stt_address = os.getenv('STT_SERVICE_ADDRESS', 'localhost:50052')
    
    logger.info(f"TTS Service: {tts_address}")
    logger.info(f"STT Service: {stt_address}")
    
    # Create tester
    tester = RealRoundTripTester(tts_address=tts_address, stt_address=stt_address)
    
    # Run round-trip tests
    logger.info("Starting round-trip audio validation tests against REAL services...")
    results = asyncio.run(tester.run_round_trip_test(passages, max_tests=100))
    
    if results.get("status") == "failed":
        logger.error("Test failed - services not available")
        return 1
    
    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("REAL ROUND-TRIP AUDIO VALIDATION TEST RESULTS")
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
    results_file = Path(data_dir) / 'datasets' / 'alice_in_wonderland' / 'real_round_trip_test_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\nResults saved to {results_file}")
    logger.info("=" * 60)
    
    # Determine success
    success_rate = results['successful_tests'] / results['total_tests'] if results['total_tests'] > 0 else 0
    if success_rate >= 0.5:  # 50% success rate for real services (adjust as needed)
        logger.info("✅ Round-trip audio validation test PASSED")
        return 0
    else:
        logger.error("❌ Round-trip audio validation test FAILED")
        return 1

if __name__ == "__main__":
    exit(main())




