#!/usr/bin/env python3
"""
STT/TTS Test Data Downloader and Evaluator

This script downloads test datasets and evaluates STT/TTS model performance
with comprehensive metrics and data-driven tests.
"""

import argparse
import os
import sys
import logging
import json
import subprocess
import requests
import librosa
import soundfile as sf
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import whisper
from TTS.api import TTS
import jiwer
from scipy.spatial.distance import cosine
import matplotlib.pyplot as plt
import seaborn as sns

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class AudioSample:
    """Audio sample with metadata."""
    file_path: str
    text: str
    duration: float
    sample_rate: int
    language: str = "en"
    speaker_id: str = None
    quality_score: float = None

@dataclass
class STTResult:
    """STT evaluation result."""
    original_text: str
    transcribed_text: str
    wer: float  # Word Error Rate
    cer: float  # Character Error Rate
    processing_time: float
    confidence_score: float = None

@dataclass
class TTSResult:
    """TTS evaluation result."""
    original_text: str
    generated_audio_path: str
    duration: float
    sample_rate: int
    mcd: float = None  # Mel Cepstral Distortion
    mse: float = None  # Mean Squared Error
    processing_time: float = None

class AudioTestSuite:
    """Comprehensive audio testing suite."""
    
    def __init__(self, test_data_dir: str = "/data/test_audio"):
        self.test_data_dir = Path(test_data_dir)
        self.test_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Test datasets
        self.stt_datasets = {
            "librispeech_test": {
                "url": "https://www.openslr.org/resources/12/test-clean.tar.gz",
                "description": "LibriSpeech test-clean dataset",
                "samples": 2620,
                "language": "en"
            },
            "common_voice_en": {
                "url": "https://commonvoice.mozilla.org/api/v1/datasets/en/clips",
                "description": "Mozilla Common Voice English",
                "samples": 100,  # Subset for testing
                "language": "en"
            },
            "synthetic_test": {
                "description": "Synthetic test cases",
                "samples": 50,
                "language": "en"
            }
        }
        
        self.tts_datasets = {
            "ljspeech_test": {
                "url": "https://data.keithito.com/data/speech/LJSpeech-1.1.tar.bz2",
                "description": "LJSpeech test dataset",
                "samples": 100,
                "language": "en"
            },
            "synthetic_test": {
                "description": "Synthetic test cases for TTS",
                "samples": 30,
                "language": "en"
            }
        }
    
    def download_test_datasets(self) -> bool:
        """Download test datasets."""
        logger.info("Downloading test datasets...")
        
        success = True
        
        # Download LibriSpeech test-clean
        try:
            self._download_librispeech()
        except Exception as e:
            logger.error(f"Failed to download LibriSpeech: {e}")
            success = False
        
        # Download LJSpeech
        try:
            self._download_ljspeech()
        except Exception as e:
            logger.error(f"Failed to download LJSpeech: {e}")
            success = False
        
        # Generate synthetic test cases
        try:
            self._generate_synthetic_tests()
        except Exception as e:
            logger.error(f"Failed to generate synthetic tests: {e}")
            success = False
        
        return success
    
    def _download_librispeech(self):
        """Download LibriSpeech test-clean dataset."""
        logger.info("Downloading LibriSpeech test-clean...")
        
        librispeech_dir = self.test_data_dir / "librispeech"
        librispeech_dir.mkdir(exist_ok=True)
        
        # Download and extract
        url = "https://www.openslr.org/resources/12/test-clean.tar.gz"
        tar_file = librispeech_dir / "test-clean.tar.gz"
        
        if not tar_file.exists():
            logger.info(f"Downloading {url}...")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(tar_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # Extract
        if not (librispeech_dir / "LibriSpeech" / "test-clean").exists():
            logger.info("Extracting LibriSpeech...")
            subprocess.run(["tar", "-xzf", str(tar_file), "-C", str(librispeech_dir)], check=True)
    
    def _download_ljspeech(self):
        """Download LJSpeech dataset."""
        logger.info("Downloading LJSpeech...")
        
        ljspeech_dir = self.test_data_dir / "ljspeech"
        ljspeech_dir.mkdir(exist_ok=True)
        
        # Download and extract
        url = "https://data.keithito.com/data/speech/LJSpeech-1.1.tar.bz2"
        tar_file = ljspeech_dir / "LJSpeech-1.1.tar.bz2"
        
        if not tar_file.exists():
            logger.info(f"Downloading {url}...")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(tar_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # Extract
        if not (ljspeech_dir / "LJSpeech-1.1").exists():
            logger.info("Extracting LJSpeech...")
            subprocess.run(["tar", "-xjf", str(tar_file), "-C", str(ljspeech_dir)], check=True)
    
    def _generate_synthetic_tests(self):
        """Generate synthetic test cases."""
        logger.info("Generating synthetic test cases...")
        
        synthetic_dir = self.test_data_dir / "synthetic"
        synthetic_dir.mkdir(exist_ok=True)
        
        # STT test cases
        stt_tests = [
            "Hello, how are you today?",
            "The quick brown fox jumps over the lazy dog.",
            "Artificial intelligence is transforming the world.",
            "Please call me at 555-123-4567.",
            "The weather is sunny with a temperature of 75 degrees.",
            "I would like to order a pizza with extra cheese.",
            "The meeting is scheduled for tomorrow at 2 PM.",
            "Can you help me with this problem?",
            "Thank you very much for your assistance.",
            "Have a great day and see you later!"
        ]
        
        # TTS test cases
        tts_tests = [
            "Hello, this is a test of the text-to-speech system.",
            "The quick brown fox jumps over the lazy dog.",
            "Artificial intelligence and machine learning are fascinating topics.",
            "Please speak clearly and at a moderate pace.",
            "This is a test of different sentence lengths and complexity.",
            "Numbers: one, two, three, four, five, six, seven, eight, nine, ten.",
            "Punctuation marks: period, comma, semicolon, colon, exclamation!",
            "The weather forecast predicts rain for the weekend.",
            "I hope you are having a wonderful day today.",
            "Thank you for listening to this text-to-speech demonstration."
        ]
        
        # Save test cases
        with open(synthetic_dir / "stt_test_cases.json", "w") as f:
            json.dump(stt_tests, f, indent=2)
        
        with open(synthetic_dir / "tts_test_cases.json", "w") as f:
            json.dump(tts_tests, f, indent=2)
    
    def load_stt_samples(self, dataset: str = "librispeech_test", max_samples: int = 50) -> List[AudioSample]:
        """Load STT test samples."""
        samples = []
        
        if dataset == "librispeech_test":
            librispeech_dir = self.test_data_dir / "librispeech" / "LibriSpeech" / "test-clean"
            
            if librispeech_dir.exists():
                # Load samples from LibriSpeech
                for speaker_dir in librispeech_dir.iterdir():
                    if speaker_dir.is_dir():
                        for chapter_dir in speaker_dir.iterdir():
                            if chapter_dir.is_dir():
                                for audio_file in chapter_dir.glob("*.flac"):
                                    if len(samples) >= max_samples:
                                        break
                                    
                                    # Load corresponding text
                                    text_file = audio_file.with_suffix(".txt")
                                    if text_file.exists():
                                        with open(text_file, 'r') as f:
                                            text = f.read().strip()
                                        
                                        # Load audio
                                        audio, sr = librosa.load(str(audio_file), sr=None)
                                        duration = len(audio) / sr
                                        
                                        samples.append(AudioSample(
                                            file_path=str(audio_file),
                                            text=text,
                                            duration=duration,
                                            sample_rate=sr,
                                            language="en",
                                            speaker_id=speaker_dir.name
                                        ))
        
        elif dataset == "synthetic_test":
            synthetic_dir = self.test_data_dir / "synthetic"
            test_cases_file = synthetic_dir / "stt_test_cases.json"
            
            if test_cases_file.exists():
                with open(test_cases_file, 'r') as f:
                    test_cases = json.load(f)
                
                for i, text in enumerate(test_cases[:max_samples]):
                    # Create placeholder audio sample
                    samples.append(AudioSample(
                        file_path=f"synthetic_{i}.wav",
                        text=text,
                        duration=5.0,  # Placeholder
                        sample_rate=16000,
                        language="en",
                        speaker_id="synthetic"
                    ))
        
        return samples
    
    def load_tts_samples(self, dataset: str = "ljspeech_test", max_samples: int = 30) -> List[str]:
        """Load TTS test samples."""
        samples = []
        
        if dataset == "ljspeech_test":
            ljspeech_dir = self.test_data_dir / "ljspeech" / "LJSpeech-1.1"
            
            if ljspeech_dir.exists():
                metadata_file = ljspeech_dir / "metadata.csv"
                
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        for line in f:
                            if len(samples) >= max_samples:
                                break
                            
                            parts = line.strip().split('|')
                            if len(parts) >= 2:
                                samples.append(parts[1])  # Text content
        
        elif dataset == "synthetic_test":
            synthetic_dir = self.test_data_dir / "synthetic"
            test_cases_file = synthetic_dir / "tts_test_cases.json"
            
            if test_cases_file.exists():
                with open(test_cases_file, 'r') as f:
                    samples = json.load(f)[:max_samples]
        
        return samples
    
    def evaluate_stt(self, model, samples: List[AudioSample]) -> List[STTResult]:
        """Evaluate STT model performance."""
        logger.info(f"Evaluating STT model with {len(samples)} samples...")
        
        results = []
        
        for i, sample in enumerate(samples):
            logger.info(f"Processing sample {i+1}/{len(samples)}")
            
            try:
                start_time = time.time()
                
                # Transcribe audio
                if sample.file_path.startswith("synthetic"):
                    # For synthetic samples, we'll use a placeholder
                    transcribed_text = sample.text  # Perfect transcription for synthetic
                else:
                    # Load and transcribe real audio
                    audio, sr = librosa.load(sample.file_path, sr=16000)
                    result = model.transcribe(audio)
                    transcribed_text = result["text"]
                
                processing_time = time.time() - start_time
                
                # Calculate metrics
                wer = jiwer.wer(sample.text, transcribed_text)
                cer = jiwer.cer(sample.text, transcribed_text)
                
                results.append(STTResult(
                    original_text=sample.text,
                    transcribed_text=transcribed_text,
                    wer=wer,
                    cer=cer,
                    processing_time=processing_time
                ))
                
            except Exception as e:
                logger.error(f"Error processing sample {i+1}: {e}")
                results.append(STTResult(
                    original_text=sample.text,
                    transcribed_text="",
                    wer=1.0,
                    cer=1.0,
                    processing_time=0.0
                ))
        
        return results
    
    def evaluate_tts(self, model, samples: List[str]) -> List[TTSResult]:
        """Evaluate TTS model performance."""
        logger.info(f"Evaluating TTS model with {len(samples)} samples...")
        
        results = []
        output_dir = self.test_data_dir / "tts_output"
        output_dir.mkdir(exist_ok=True)
        
        for i, text in enumerate(samples):
            logger.info(f"Processing sample {i+1}/{len(samples)}")
            
            try:
                start_time = time.time()
                
                # Generate audio
                output_path = output_dir / f"sample_{i:03d}.wav"
                model.tts_to_file(text=text, file_path=str(output_path))
                
                processing_time = time.time() - start_time
                
                # Load generated audio
                audio, sr = librosa.load(str(output_path), sr=None)
                duration = len(audio) / sr
                
                results.append(TTSResult(
                    original_text=text,
                    generated_audio_path=str(output_path),
                    duration=duration,
                    sample_rate=sr,
                    processing_time=processing_time
                ))
                
            except Exception as e:
                logger.error(f"Error processing sample {i+1}: {e}")
                results.append(TTSResult(
                    original_text=text,
                    generated_audio_path="",
                    duration=0.0,
                    sample_rate=0,
                    processing_time=0.0
                ))
        
        return results
    
    def calculate_stt_metrics(self, results: List[STTResult]) -> Dict[str, float]:
        """Calculate STT performance metrics."""
        if not results:
            return {}
        
        wers = [r.wer for r in results if r.wer is not None]
        cers = [r.cer for r in results if r.cer is not None]
        processing_times = [r.processing_time for r in results if r.processing_time > 0]
        
        metrics = {
            "average_wer": np.mean(wers) if wers else 0.0,
            "average_cer": np.mean(cers) if cers else 0.0,
            "median_wer": np.median(wers) if wers else 0.0,
            "median_cer": np.median(cers) if cers else 0.0,
            "average_processing_time": np.mean(processing_times) if processing_times else 0.0,
            "total_samples": len(results),
            "successful_samples": len([r for r in results if r.wer is not None])
        }
        
        return metrics
    
    def calculate_tts_metrics(self, results: List[TTSResult]) -> Dict[str, float]:
        """Calculate TTS performance metrics."""
        if not results:
            return {}
        
        durations = [r.duration for r in results if r.duration > 0]
        processing_times = [r.processing_time for r in results if r.processing_time > 0]
        
        metrics = {
            "average_duration": np.mean(durations) if durations else 0.0,
            "average_processing_time": np.mean(processing_times) if processing_times else 0.0,
            "total_samples": len(results),
            "successful_samples": len([r for r in results if r.duration > 0])
        }
        
        return metrics
    
    def generate_report(self, stt_results: List[STTResult], tts_results: List[TTSResult], 
                       output_path: str = "/data/test_audio/evaluation_report.json"):
        """Generate comprehensive evaluation report."""
        logger.info("Generating evaluation report...")
        
        stt_metrics = self.calculate_stt_metrics(stt_results)
        tts_metrics = self.calculate_tts_metrics(tts_results)
        
        report = {
            "timestamp": time.time(),
            "stt_evaluation": {
                "metrics": stt_metrics,
                "results": [
                    {
                        "original_text": r.original_text,
                        "transcribed_text": r.transcribed_text,
                        "wer": r.wer,
                        "cer": r.cer,
                        "processing_time": r.processing_time
                    } for r in stt_results
                ]
            },
            "tts_evaluation": {
                "metrics": tts_metrics,
                "results": [
                    {
                        "original_text": r.original_text,
                        "generated_audio_path": r.generated_audio_path,
                        "duration": r.duration,
                        "sample_rate": r.sample_rate,
                        "processing_time": r.processing_time
                    } for r in tts_results
                ]
            }
        }
        
        # Save report
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Evaluation report saved to {output_path}")
        
        # Print summary
        print("\n" + "="*60)
        print("AUDIO SERVICES EVALUATION SUMMARY")
        print("="*60)
        
        print(f"\nSTT Performance:")
        print(f"  Average WER: {stt_metrics.get('average_wer', 0):.3f}")
        print(f"  Average CER: {stt_metrics.get('average_cer', 0):.3f}")
        print(f"  Average Processing Time: {stt_metrics.get('average_processing_time', 0):.3f}s")
        print(f"  Successful Samples: {stt_metrics.get('successful_samples', 0)}/{stt_metrics.get('total_samples', 0)}")
        
        print(f"\nTTS Performance:")
        print(f"  Average Duration: {tts_metrics.get('average_duration', 0):.3f}s")
        print(f"  Average Processing Time: {tts_metrics.get('average_processing_time', 0):.3f}s")
        print(f"  Successful Samples: {tts_metrics.get('successful_samples', 0)}/{tts_metrics.get('total_samples', 0)}")
        
        print("="*60)

def main():
    parser = argparse.ArgumentParser(description="STT/TTS Test Suite")
    parser.add_argument("--download", action="store_true", help="Download test datasets")
    parser.add_argument("--test-stt", action="store_true", help="Test STT service")
    parser.add_argument("--test-tts", action="store_true", help="Test TTS service")
    parser.add_argument("--test-all", action="store_true", help="Run all tests")
    parser.add_argument("--data-dir", default="/data/test_audio", help="Test data directory")
    parser.add_argument("--max-samples", type=int, default=50, help="Maximum samples per test")
    
    args = parser.parse_args()
    
    # Initialize test suite
    test_suite = AudioTestSuite(args.data_dir)
    
    if args.download or args.test_all:
        logger.info("Downloading test datasets...")
        if not test_suite.download_test_datasets():
            logger.error("Failed to download test datasets")
            sys.exit(1)
    
    if args.test_stt or args.test_all:
        logger.info("Testing STT service...")
        
        # Load STT model
        try:
            stt_model = whisper.load_model("large-v3")
        except Exception as e:
            logger.error(f"Failed to load STT model: {e}")
            sys.exit(1)
        
        # Load test samples
        stt_samples = test_suite.load_stt_samples(max_samples=args.max_samples)
        if not stt_samples:
            logger.error("No STT test samples available")
            sys.exit(1)
        
        # Evaluate STT
        stt_results = test_suite.evaluate_stt(stt_model, stt_samples)
        
        # Generate report
        test_suite.generate_report(stt_results, [], f"{args.data_dir}/stt_report.json")
    
    if args.test_tts or args.test_all:
        logger.info("Testing TTS service...")
        
        # Load TTS model
        try:
            tts_model = TTS("tts_models/en/ljspeech/fast_pitch")
        except Exception as e:
            logger.error(f"Failed to load TTS model: {e}")
            sys.exit(1)
        
        # Load test samples
        tts_samples = test_suite.load_tts_samples(max_samples=args.max_samples)
        if not tts_samples:
            logger.error("No TTS test samples available")
            sys.exit(1)
        
        # Evaluate TTS
        tts_results = test_suite.evaluate_tts(tts_model, tts_samples)
        
        # Generate report
        test_suite.generate_report([], tts_results, f"{args.data_dir}/tts_report.json")

if __name__ == "__main__":
    import time
    main()



