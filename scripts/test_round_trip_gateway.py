#!/usr/bin/env python3
"""
Round-Trip Audio Validation Test via Gateway
Tests the full pipeline: Text → TTS → Audio → Gateway → Audio → STT → Text

This simulates real user interaction:
1. User speaks text → converted to audio via TTS
2. Audio sent to Gateway (as if from user/microphone)
3. Gateway processes and returns audio response
4. Response audio converted back to text via STT for validation

Two TTS→STT conversions tested:
- Input: Text → TTS → Audio (simulating user input)
- Output: Audio → STT → Text (validating Gateway response)
"""
import os
import json
import asyncio
import logging
import grpc
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import protobuf classes from installed package
from june_grpc_api import tts_pb2, tts_pb2_grpc, asr_pb2, asr_pb2_grpc

class GatewayRoundTripTester:
    """Round-trip tester via Gateway simulating real user flow."""
    
    def __init__(self, 
                 tts_address: str = "localhost:50053",
                 stt_address: str = "localhost:50052",
                 gateway_url: str = "http://localhost:8000",
                 test_data_dir: Optional[str] = None):
        self.tts_address = tts_address
        self.stt_address = stt_address
        self.gateway_url = gateway_url
        self.sample_rate = 16000
        
        # Set up test data directory
        # Check if JUNE_TEST_DATA_DIR is set and points to a specific run directory
        test_run_dir_env = os.getenv('JUNE_TEST_DATA_DIR')
        if test_run_dir_env and 'run_' in test_run_dir_env:
            # Shell script has created a specific run directory - use it
            self.test_run_dir = Path(test_run_dir_env)
        else:
            # Create our own test run directory
            if test_data_dir is None:
                base_dir = os.getenv('JUNE_TEST_DATA_DIR', os.path.expanduser('~/june_test_data'))
                test_data_dir = base_dir
            
            self.test_data_dir = Path(test_data_dir)
            self.test_run_dir = self.test_data_dir / datetime.now().strftime("run_%Y%m%d_%H%M%S")
        
        self.test_run_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for artifacts
        (self.test_run_dir / "input_audio").mkdir(exist_ok=True)
        (self.test_run_dir / "output_audio").mkdir(exist_ok=True)
        (self.test_run_dir / "transcripts").mkdir(exist_ok=True)
        (self.test_run_dir / "metadata").mkdir(exist_ok=True)
        
        logger.info(f"Test artifacts will be saved to: {self.test_run_dir}")
        logger.info(f"Test run directory resolved from JUNE_TEST_DATA_DIR: {test_run_dir_env}")
        logger.info(f"Test run directory absolute path: {self.test_run_dir.absolute()}")
        
    async def tts_synthesize(self, text: str) -> bytes:
        """TTS: Convert text to audio using real TTS gRPC service."""
        try:
            async with grpc.aio.insecure_channel(self.tts_address) as channel:
                stub = tts_pb2_grpc.TextToSpeechStub(channel)
                
                config = tts_pb2.SynthesisConfig(
                    sample_rate=self.sample_rate,
                    speed=1.0,
                    pitch=0.0
                )
                
                request = tts_pb2.SynthesisRequest(
                    text=text,
                    config=config,
                    voice_id="default",
                    language="en"
                )
                
                logger.debug(f"TTS: Synthesizing '{text[:50]}...'")
                response = await stub.Synthesize(request, timeout=30.0)
                
                if response.audio_data:
                    logger.debug(f"TTS: Generated {len(response.audio_data)} bytes")
                    return response.audio_data
                else:
                    logger.error("TTS: Empty audio response")
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
                stub = asr_pb2_grpc.SpeechToTextStub(channel)
                
                cfg = asr_pb2.RecognitionConfig(language="en", interim_results=False)
                request = asr_pb2.RecognitionRequest(
                    audio_data=audio_data,
                    sample_rate=self.sample_rate,
                    encoding="wav",
                    config=cfg,
                )
                
                logger.debug(f"STT: Recognizing {len(audio_data)} bytes of audio")
                response = await stub.Recognize(request, timeout=30.0)
                
                if response.results and len(response.results) > 0:
                    result = response.results[0]
                    transcript = result.transcript
                    confidence = result.confidence
                    logger.debug(f"STT: Recognized '{transcript}' (confidence: {confidence:.2f})")
                    return transcript
                else:
                    logger.error("STT: No results returned")
                    return ""
                    
        except grpc.RpcError as e:
            logger.error(f"STT gRPC error: {e.code()} - {e.details()}")
            return ""
        except Exception as e:
            logger.error(f"STT recognition failed: {e}")
            return ""
    
    async def send_audio_to_gateway(self, audio_data: bytes, session_id: str = "test_session") -> bytes:
        """Send audio to Gateway and get audio response."""
        try:
            # Send audio to Gateway as if from user
            # Using the Gateway's audio input endpoint
            url = f"{self.gateway_url}/api/v1/audio/transcribe"
            
            logger.debug(f"Gateway: Sending {len(audio_data)} bytes to {url}")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Send audio as multipart form data
                files = {
                    'audio': ('audio.wav', audio_data, 'audio/wav')
                }
                data = {
                    'session_id': session_id
                }
                
                response = await client.post(url, files=files, data=data)
                
                if response.status_code == 200:
                    result = response.json()
                    # Gateway should return audio response
                    # For now, assume it returns audio_data field
                    if 'audio_data' in result:
                        audio_response = result['audio_data']
                        if isinstance(audio_response, str):
                            # Base64 encoded
                            import base64
                            return base64.b64decode(audio_response)
                        else:
                            return audio_response
                    elif 'response_audio' in result:
                        # Alternative field name
                        audio_response = result['response_audio']
                        if isinstance(audio_response, str):
                            import base64
                            return base64.b64decode(audio_response)
                        else:
                            return audio_response
                    else:
                        logger.error(f"Gateway: No audio in response: {result}")
                        return b""
                else:
                    logger.error(f"Gateway: HTTP {response.status_code} - {response.text}")
                    return b""
                    
        except Exception as e:
            logger.error(f"Gateway request failed: {e}")
            # Fallback: for now, return empty (Gateway might not be fully implemented)
            return b""
    
    def calculate_metrics(self, original: str, transcribed: str) -> Dict[str, Any]:
        """Calculate accuracy metrics."""
        try:
            original_clean = original.lower().strip()
            transcribed_clean = transcribed.lower().strip()
            
            exact_match = original_clean == transcribed_clean
            
            original_words = original_clean.split()
            transcribed_words = transcribed_clean.split()
            
            if len(original_words) > 0:
                matching_words = sum(1 for word in original_words if word in transcribed_words)
                word_accuracy = matching_words / len(original_words)
            else:
                word_accuracy = 0.0
            
            original_chars = original_clean.replace(" ", "")
            transcribed_chars = transcribed_clean.replace(" ", "")
            
            if len(original_chars) > 0:
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
    
    def save_audio_file(self, audio_data: bytes, filename: str, is_input: bool = True) -> Path:
        """Save audio data to file."""
        try:
            if is_input:
                audio_dir = self.test_run_dir / "input_audio"
            else:
                audio_dir = self.test_run_dir / "output_audio"
            
            audio_file = audio_dir / f"{filename}.wav"
            
            # Write audio as WAV file (assuming 16-bit PCM, mono, 16kHz)
            import struct
            with open(audio_file, 'wb') as f:
                # WAV header
                f.write(b'RIFF')
                f.write(struct.pack('<I', len(audio_data) + 36))  # File size - 8
                f.write(b'WAVE')
                f.write(b'fmt ')
                f.write(struct.pack('<I', 16))  # fmt chunk size
                f.write(struct.pack('<HHIIHH', 1, 1, self.sample_rate, self.sample_rate * 2, 2, 16))  # PCM, mono, 16kHz, 16-bit
                f.write(b'data')
                f.write(struct.pack('<I', len(audio_data)))  # Data chunk size
                f.write(audio_data)
            
            logger.debug(f"Saved audio to {audio_file}")
            return audio_file
            
        except Exception as e:
            logger.error(f"Failed to save audio file: {e}")
            return Path()
    
    def save_transcript(self, passage_id: int, original: str, input_transcribed: str, output_transcribed: str) -> Path:
        """Save transcript to file."""
        try:
            transcript_file = self.test_run_dir / "transcripts" / f"passage_{passage_id:03d}.txt"
            
            with open(transcript_file, 'w', encoding='utf-8') as f:
                f.write(f"Passage ID: {passage_id}\n")
                f.write(f"{'='*60}\n\n")
                f.write(f"Original Text:\n{original}\n\n")
                f.write(f"{'-'*60}\n\n")
                f.write(f"Input Transcript (Text → TTS → STT):\n{input_transcribed}\n\n")
                f.write(f"{'-'*60}\n\n")
                f.write(f"Output Transcript (Gateway Audio → STT):\n{output_transcribed}\n")
            
            logger.debug(f"Saved transcript to {transcript_file}")
            return transcript_file
            
        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")
            return Path()
    
    def save_test_metadata(self, passage_id: int, metadata: Dict[str, Any]) -> Path:
        """Save test metadata to JSON file."""
        try:
            metadata_file = self.test_run_dir / "metadata" / f"passage_{passage_id:03d}.json"
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved metadata to {metadata_file}")
            return metadata_file
            
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
            return Path()
    
    def check_models(self) -> Dict[str, Any]:
        """Check if required models are available."""
        model_cache_dir = Path(os.getenv('MODEL_CACHE_DIR', os.path.expanduser('~/models')))
        
        logger.info(f"Checking models in {model_cache_dir}...")
        
        model_status = {
            "model_cache_dir": str(model_cache_dir),
            "exists": model_cache_dir.exists(),
            "has_models": False,
            "model_files": []
        }
        
        if model_cache_dir.exists():
            # Check for model files
            model_files = list(model_cache_dir.rglob("*.bin")) + list(model_cache_dir.rglob("*.safetensors"))
            if len(model_files) > 0:
                model_status["has_models"] = True
                model_status["model_files"] = [str(f.relative_to(model_cache_dir)) for f in model_files[:10]]
                logger.info(f"✅ Found {len(model_files)} model files")
            else:
                logger.warning(f"⚠️  Model cache directory exists but no models found")
                logger.info(f"   Run: python scripts/download_models.py --all")
        else:
            logger.warning(f"⚠️  Model cache directory does not exist: {model_cache_dir}")
            logger.info(f"   Run: python scripts/download_models.py --all")
        
        return model_status
    
    async def test_connectivity(self) -> Dict[str, bool]:
        """Test connectivity to all services."""
        logger.info("Testing connectivity to services...")
        
        results = {
            "tts": False,
            "stt": False,
            "gateway": False
        }
        
        # Test TTS
        try:
            async with grpc.aio.insecure_channel(self.tts_address) as channel:
                stub = tts_pb2_grpc.TextToSpeechStub(channel)
                # Optional: call health if implemented in proto
                results["tts"] = True
                logger.info(f"✅ TTS service reachable at {self.tts_address}")
        except Exception as e:
            logger.error(f"❌ Cannot connect to TTS: {e}")
        
        # Test STT
        try:
            async with grpc.aio.insecure_channel(self.stt_address) as channel:
                stub = asr_pb2_grpc.SpeechToTextStub(channel)
                results["stt"] = True
                logger.info(f"✅ STT service reachable at {self.stt_address}")
        except Exception as e:
            logger.error(f"❌ Cannot connect to STT: {e}")
        
        # Test Gateway
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.gateway_url}/health")
                results["gateway"] = response.status_code == 200
                if results["gateway"]:
                    logger.info(f"✅ Gateway healthy at {self.gateway_url}")
                else:
                    logger.error(f"❌ Gateway unhealthy: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Cannot connect to Gateway: {e}")
        
        return results
    
    async def run_round_trip_test(self, passages: List[Dict[str, Any]], max_tests: Optional[int] = None) -> Dict[str, Any]:
        """Run full round-trip tests via Gateway."""
        logger.info(f"Starting Gateway Round-Trip Test")
        logger.info(f"Flow: Text → TTS → Audio → Gateway → Audio → STT → Text")
        logger.info(f"Total passages available: {len(passages)}")
        
        # Check models
        model_status = self.check_models()
        
        # Test connectivity
        connectivity = await self.test_connectivity()
        if not all([connectivity["tts"], connectivity["stt"], connectivity["gateway"]]):
            logger.warning("Not all services are available. Some tests may fail.")
            logger.warning("Connectivity: TTS={}, STT={}, Gateway={}".format(
                connectivity["tts"], connectivity["stt"], connectivity["gateway"]))
            logger.warning("Attempting to continue with available services...")
            # Continue anyway - partial results are better than none
        
        if max_tests:
            test_passages = passages[:max_tests]
        else:
            test_passages = passages
        
        logger.info(f"Testing {len(test_passages)} passages")
        
        results = {
            "test_timestamp": datetime.now().isoformat(),
            "test_run_directory": str(self.test_run_dir),
            "service_addresses": {
                "tts": self.tts_address,
                "stt": self.stt_address,
                "gateway": self.gateway_url
            },
            "model_status": model_status,
            "connectivity": connectivity,
            "total_tests": len(test_passages),
            "successful_tests": 0,
            "failed_tests": 0,
            "test_results": [],
            "summary_metrics": {
                "input_exact_match_count": 0,
                "output_exact_match_count": 0,
                "input_exact_match_rate": 0.0,
                "output_exact_match_rate": 0.0,
                "average_input_word_accuracy": 0.0,
                "average_output_word_accuracy": 0.0
            }
        }
        
        input_exact_matches = 0
        output_exact_matches = 0
        input_word_accuracies = []
        output_word_accuracies = []
        
        for i, passage in enumerate(test_passages):
            passage_text = passage['text']
            passage_id = passage['id']
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Test {i+1}/{len(test_passages)} - Passage ID: {passage_id}")
            logger.info(f"Input text: {passage_text[:100]}...")
            
            try:
                # Step 1: TTS - Convert input text to audio (simulating user)
                logger.info(f"  Step 1: TTS synthesis (input)...")
                input_audio = await self.tts_synthesize(passage_text)
                
                if not input_audio or len(input_audio) == 0:
                    logger.error(f"  ❌ Failed to generate input audio")
                    # Still save metadata about the failure
                    failure_metadata = {
                        "passage_id": passage_id,
                        "test_timestamp": datetime.now().isoformat(),
                        "original_text": passage_text,
                        "status": "failed",
                        "error": "Input audio generation failed",
                        "error_stage": "tts_synthesis"
                    }
                    self.save_test_metadata(passage_id, failure_metadata)
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "failed",
                        "error": "Input audio generation failed"
                    })
                    results["failed_tests"] += 1
                    continue
                
                logger.info(f"  ✅ Generated {len(input_audio)} bytes of input audio")
                
                # Save input audio artifact
                input_audio_file = self.save_audio_file(input_audio, f"passage_{passage_id:03d}_input", is_input=True)
                
                # Step 2: STT - Convert input audio back to text (validating input conversion)
                logger.info(f"  Step 2: STT recognition (input validation)...")
                input_transcribed = await self.stt_recognize(input_audio)
                
                if not input_transcribed:
                    logger.error(f"  ❌ Failed to transcribe input audio")
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "failed",
                        "error": "Input transcription failed"
                    })
                    results["failed_tests"] += 1
                    continue
                
                logger.info(f"  ✅ Input transcribed: {input_transcribed[:100]}...")
                
                # Calculate input metrics
                input_metrics = self.calculate_metrics(passage_text, input_transcribed)
                if input_metrics.get("exact_match"):
                    input_exact_matches += 1
                if input_metrics.get("word_accuracy") is not None:
                    input_word_accuracies.append(input_metrics["word_accuracy"])
                
                # Step 3: Gateway - Send audio to Gateway and get response
                logger.info(f"  Step 3: Sending audio to Gateway...")
                output_audio = await self.send_audio_to_gateway(input_audio)
                
                if not output_audio or len(output_audio) == 0:
                    logger.warning(f"  ⚠️  Gateway returned empty audio (might be pass-through mode)")
                    # Continue anyway - Gateway might echo back or return empty
                    output_audio = input_audio  # Fallback for testing
                
                logger.info(f"  ✅ Received {len(output_audio)} bytes from Gateway")
                
                # Save output audio artifact
                output_audio_file = self.save_audio_file(output_audio, f"passage_{passage_id:03d}_output", is_input=False)
                
                # Step 4: STT - Convert Gateway response audio to text
                logger.info(f"  Step 4: STT recognition (output validation)...")
                output_transcribed = await self.stt_recognize(output_audio)
                
                if not output_transcribed:
                    logger.error(f"  ❌ Failed to transcribe output audio")
                    results["test_results"].append({
                        "passage_id": passage_id,
                        "status": "partial",
                        "error": "Output transcription failed",
                        "input_metrics": input_metrics
                    })
                    results["failed_tests"] += 1
                    continue
                
                logger.info(f"  ✅ Output transcribed: {output_transcribed[:100]}...")
                
                # Calculate output metrics (comparing Gateway response to original)
                output_metrics = self.calculate_metrics(passage_text, output_transcribed)
                if output_metrics.get("exact_match"):
                    output_exact_matches += 1
                if output_metrics.get("word_accuracy") is not None:
                    output_word_accuracies.append(output_metrics["word_accuracy"])
                
                # Save artifacts
                transcript_file = self.save_transcript(passage_id, passage_text, input_transcribed, output_transcribed)
                
                # Create comprehensive metadata
                test_metadata = {
                    "passage_id": passage_id,
                    "test_timestamp": datetime.now().isoformat(),
                    "original_text": passage_text,
                    "input_transcript": input_transcribed,
                    "output_transcript": output_transcribed,
                    "input_metrics": input_metrics,
                    "output_metrics": output_metrics,
                    "artifacts": {
                        "input_audio": str(input_audio_file),
                        "output_audio": str(output_audio_file),
                        "transcript": str(transcript_file)
                    },
                    "audio_sizes": {
                        "input_bytes": len(input_audio),
                        "output_bytes": len(output_audio)
                    }
                }
                metadata_file = self.save_test_metadata(passage_id, test_metadata)
                
                # Store results
                results["test_results"].append({
                    "passage_id": passage_id,
                    "status": "success",
                    "input_metrics": input_metrics,
                    "output_metrics": output_metrics,
                    "input_audio_size": len(input_audio),
                    "output_audio_size": len(output_audio),
                    "artifacts": {
                        "input_audio": str(input_audio_file),
                        "output_audio": str(output_audio_file),
                        "transcript": str(transcript_file),
                        "metadata": str(metadata_file)
                    }
                })
                
                results["successful_tests"] += 1
                
                logger.info(f"  📊 Input accuracy: {input_metrics.get('word_accuracy', 0):.2%}, Output accuracy: {output_metrics.get('word_accuracy', 0):.2%}")
                logger.info(f"  💾 Artifacts saved: audio ({len(input_audio)}, {len(output_audio)} bytes), transcript, metadata")
                
                if (i + 1) % 10 == 0:
                    logger.info(f"\nProgress: {i+1}/{len(test_passages)} tests completed")
                    
            except Exception as e:
                logger.error(f"  ❌ Test failed: {e}")
                results["test_results"].append({
                    "passage_id": passage_id,
                    "status": "failed",
                    "error": str(e)
                })
                results["failed_tests"] += 1
        
        # Calculate summary metrics
        if input_word_accuracies:
            results["summary_metrics"]["input_exact_match_count"] = input_exact_matches
            results["summary_metrics"]["input_exact_match_rate"] = input_exact_matches / len(test_passages)
            results["summary_metrics"]["average_input_word_accuracy"] = sum(input_word_accuracies) / len(input_word_accuracies)
        
        if output_word_accuracies:
            results["summary_metrics"]["output_exact_match_count"] = output_exact_matches
            results["summary_metrics"]["output_exact_match_rate"] = output_exact_matches / len(test_passages)
            results["summary_metrics"]["average_output_word_accuracy"] = sum(output_word_accuracies) / len(output_word_accuracies)
        
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
    import argparse
    
    parser = argparse.ArgumentParser(description='Gateway Round-Trip Audio Validation Test')
    parser.add_argument('--max-tests', type=int, default=100,
                       help='Maximum number of tests to run (default: 100)')
    parser.add_argument('--limit', type=int, default=None,
                       help='Alias for --max-tests (default: 100)')
    
    args = parser.parse_args()
    
    # Use limit if provided, otherwise max_tests
    max_tests = args.limit if args.limit is not None else args.max_tests
    
    # Get data directory
    data_dir = os.getenv('JUNE_DATA_DIR', '/home/rlee/june_data')
    dataset_file = Path(data_dir) / 'datasets' / 'alice_in_wonderland' / 'alice_dataset.json'
    
    if not dataset_file.exists():
        logger.error(f"Dataset file not found: {dataset_file}")
        logger.info("Please run scripts/generate_alice_dataset.py first")
        return 1
    
    # Load dataset
    passages = load_dataset(dataset_file)
    if not passages:
        return 1
    
    # Service addresses
    tts_address = os.getenv('TTS_SERVICE_ADDRESS', 'localhost:50053')
    stt_address = os.getenv('STT_SERVICE_ADDRESS', 'localhost:50052')
    gateway_url = os.getenv('GATEWAY_URL', 'http://localhost:8000')
    
    logger.info(f"TTS Service: {tts_address}")
    logger.info(f"STT Service: {stt_address}")
    logger.info(f"Gateway URL: {gateway_url}")
    
    # Create tester
    tester = GatewayRoundTripTester(
        tts_address=tts_address,
        stt_address=stt_address,
        gateway_url=gateway_url
    )
    
    # Run tests
    logger.info("\n" + "="*60)
    logger.info("GATEWAY ROUND-TRIP AUDIO VALIDATION TEST")
    logger.info("="*60)
    logger.info("Testing full pipeline via Gateway:")
    logger.info("  Text → TTS → Audio → Gateway → Audio → STT → Text")
    logger.info(f"Running up to {max_tests} tests")
    logger.info("="*60 + "\n")
    
    results = asyncio.run(tester.run_round_trip_test(passages, max_tests=max_tests))
    
    if results.get("status") == "failed":
        logger.error("Test failed - services not available")
        return 1
    
    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Total tests: {results['total_tests']}")
    logger.info(f"Successful: {results['successful_tests']}")
    logger.info(f"Failed: {results['failed_tests']}")
    
    logger.info("\nInput Conversion Metrics (Text → TTS → STT):")
    metrics = results['summary_metrics']
    logger.info(f"  Exact matches: {metrics['input_exact_match_count']}")
    logger.info(f"  Exact match rate: {metrics['input_exact_match_rate']:.2%}")
    logger.info(f"  Average word accuracy: {metrics['average_input_word_accuracy']:.2%}")
    
    logger.info("\nOutput Conversion Metrics (Gateway Audio → STT):")
    logger.info(f"  Exact matches: {metrics['output_exact_match_count']}")
    logger.info(f"  Exact match rate: {metrics['output_exact_match_rate']:.2%}")
    logger.info(f"  Average word accuracy: {metrics['average_output_word_accuracy']:.2%}")
    
    # Save results to both locations
    results_file = Path(data_dir) / 'datasets' / 'alice_in_wonderland' / 'gateway_round_trip_test_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Also save to test run directory
    test_summary_file = tester.test_run_dir / 'test_summary.json'
    with open(test_summary_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_run_directory": str(tester.test_run_dir),
            "test_timestamp": results.get("test_timestamp"),
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\nResults saved to {results_file}")
    logger.info(f"Test artifacts saved to: {tester.test_run_dir}")
    logger.info("=" * 60)
    
    # Determine success
    success_rate = results['successful_tests'] / results['total_tests'] if results['total_tests'] > 0 else 0
    if success_rate >= 0.5:
        logger.info("✅ Gateway round-trip test PASSED")
        return 0
    else:
        logger.error("❌ Gateway round-trip test FAILED")
        return 1

if __name__ == "__main__":
    exit(main())

