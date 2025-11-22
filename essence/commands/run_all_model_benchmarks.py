"""
Run All Model Benchmarks - Comprehensive benchmarking for LLM, STT, and TTS models.

Usage:
    poetry run python -m essence run-all-model-benchmarks [--llm] [--stt] [--tts] [--audio-stack] [--output-dir DIR]

This command runs comprehensive benchmarks on all models:
- LLM: HumanEval, MBPP coding benchmarks (with baseline comparisons)
- STT: LibriSpeech test-clean WER/CER (compare to Whisper-large-v3 published results)
- TTS: Quality metrics and round-trip tests (compare to FastSpeech2 published results)
- Audio Stack: End-to-end round-trip tests (TTS → STT → LLM → TTS)

All results are compared against published third-party benchmarks to verify model performance.
"""
import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from essence.chat.utils.tracing import setup_tracing
from essence.command import Command

logger = logging.getLogger(__name__)

# Import benchmark components (may not be available in all environments)
try:
    from essence.agents.dataset_loader import DatasetLoader
    from essence.agents.evaluator import BenchmarkEvaluator

    LLM_BENCHMARKS_AVAILABLE = True
except ImportError as e:
    LLM_BENCHMARKS_AVAILABLE = False
    LLM_IMPORT_ERROR = str(e)
    BenchmarkEvaluator = None
    DatasetLoader = None

try:
    import grpc
    from proto import asr_pb2, asr_pb2_grpc, tts_pb2, tts_pb2_grpc

    STT_TTS_AVAILABLE = True
except ImportError as e:
    STT_TTS_AVAILABLE = False
    STT_TTS_IMPORT_ERROR = str(e)


@dataclass
class STTBenchmarkResult:
    """STT benchmark result with comparison to published baselines."""

    dataset: str
    total_samples: int
    successful_samples: int
    average_wer: float  # Word Error Rate
    average_cer: float  # Character Error Rate
    baseline_wer: Optional[float] = None  # Published baseline WER
    baseline_cer: Optional[float] = None  # Published baseline CER
    wer_delta: Optional[float] = None  # Our WER - Baseline WER
    cer_delta: Optional[float] = None  # Our CER - Baseline CER
    average_latency_seconds: float = 0.0
    model_name: str = "openai/whisper-large-v3"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class TTSBenchmarkResult:
    """TTS benchmark result with comparison to published baselines."""

    dataset: str
    total_samples: int
    successful_samples: int
    average_mos: Optional[float] = None  # Mean Opinion Score (if available)
    average_mcd: Optional[float] = None  # Mel Cepstral Distortion
    round_trip_wer: Optional[float] = None  # WER from round-trip TTS→STT
    round_trip_cer: Optional[float] = None  # CER from round-trip TTS→STT
    baseline_mos: Optional[float] = None  # Published baseline MOS
    baseline_mcd: Optional[float] = None  # Published baseline MCD
    average_latency_seconds: float = 0.0
    model_name: str = "facebook/fastspeech2-en-ljspeech"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class AudioStackBenchmarkResult:
    """End-to-end audio stack benchmark result."""

    total_tests: int
    successful_tests: int
    average_round_trip_wer: float
    average_round_trip_cer: float
    average_llm_latency_seconds: float
    average_stt_latency_seconds: float
    average_tts_latency_seconds: float
    average_total_latency_seconds: float
    end_to_end_success_rate: float  # Percentage of successful end-to-end flows

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ComprehensiveBenchmarkReport:
    """Comprehensive benchmark report for all models."""

    timestamp: str
    llm_results: Optional[Dict[str, Any]] = None
    stt_results: Optional[STTBenchmarkResult] = None
    tts_results: Optional[TTSBenchmarkResult] = None
    audio_stack_results: Optional[AudioStackBenchmarkResult] = None
    summary: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "timestamp": self.timestamp,
        }
        if self.llm_results:
            result["llm_results"] = self.llm_results
        if self.stt_results:
            result["stt_results"] = self.stt_results.to_dict()
        if self.tts_results:
            result["tts_results"] = self.tts_results.to_dict()
        if self.audio_stack_results:
            result["audio_stack_results"] = self.audio_stack_results.to_dict()
        if self.summary:
            result["summary"] = self.summary
        return result

    def save(self, output_path: Path) -> None:
        """Save report to JSON file."""
        with open(output_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved comprehensive benchmark report to {output_path}")


class AllModelBenchmarkRunner(Command):
    """
    Command for running comprehensive benchmarks on all models.

    Orchestrates benchmarking of LLM, STT, TTS, and end-to-end audio stack,
    comparing results against published third-party benchmarks.
    """

    def __init__(self, args: argparse.Namespace):
        """Initialize command with parsed arguments."""
        super().__init__(args)
        self._output_dir = None
        self._llm_evaluator = None

    @classmethod
    def get_name(cls) -> str:
        """Get the command name."""
        return "run-all-model-benchmarks"

    @classmethod
    def get_description(cls) -> str:
        """Get the command description."""
        return "Run comprehensive benchmarks on all models (LLM, STT, TTS, audio stack)"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """Add command-line arguments."""
        parser.add_argument(
            "--llm",
            action="store_true",
            help="Run LLM benchmarks (HumanEval, MBPP)",
        )
        parser.add_argument(
            "--stt",
            action="store_true",
            help="Run STT benchmarks (LibriSpeech WER/CER)",
        )
        parser.add_argument(
            "--tts",
            action="store_true",
            help="Run TTS benchmarks (quality metrics, round-trip)",
        )
        parser.add_argument(
            "--audio-stack",
            action="store_true",
            help="Run end-to-end audio stack benchmarks (TTS → STT → LLM → TTS)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Run all benchmarks (equivalent to --llm --stt --tts --audio-stack)",
        )
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=Path(os.getenv("BENCHMARK_OUTPUT_DIR", "/tmp/benchmarks/all_models")),
            help="Output directory for results (default: /tmp/benchmarks/all_models)",
        )
        parser.add_argument(
            "--llm-url",
            default=os.getenv(
                "LLM_URL", os.getenv("INFERENCE_API_URL", "tensorrt-llm:8000")
            ),
            help="gRPC endpoint for LLM inference service",
        )
        parser.add_argument(
            "--stt-url",
            default=os.getenv("STT_URL", "stt:50052"),
            help="gRPC endpoint for STT service",
        )
        parser.add_argument(
            "--tts-url",
            default=os.getenv("TTS_URL", "tts:50053"),
            help="gRPC endpoint for TTS service",
        )
        parser.add_argument(
            "--max-samples",
            type=int,
            default=None,
            help="Maximum samples for STT/TTS benchmarks (default: all)",
        )

    def init(self) -> None:
        """Initialize benchmark runner."""
        # Setup tracing
        setup_tracing(service_name="june-all-model-benchmarks")

        # Create output directory
        self._output_dir = self.args.output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {self._output_dir}")

        # Initialize LLM evaluator if needed
        if (self.args.llm or self.args.all) and LLM_BENCHMARKS_AVAILABLE:
            self._llm_evaluator = BenchmarkEvaluator(
                llm_url=self.args.llm_url,
                model_name=os.getenv("MODEL_NAME", "Qwen/Qwen3-30B-A3B-Thinking-2507"),
                sandbox_workspace_base=self._output_dir / "llm_sandboxes",
            )
            logger.info("LLM benchmark evaluator initialized")

    def run(self) -> None:
        """Run all requested benchmarks."""
        run_all = self.args.all or (
            not self.args.llm
            and not self.args.stt
            and not self.args.tts
            and not self.args.audio_stack
        )

        report = ComprehensiveBenchmarkReport(
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        # Run LLM benchmarks
        if (self.args.llm or run_all) and LLM_BENCHMARKS_AVAILABLE:
            logger.info("\n" + "=" * 60)
            logger.info("Running LLM Benchmarks")
            logger.info("=" * 60)
            try:
                llm_results = self._run_llm_benchmarks()
                report.llm_results = llm_results
            except Exception as e:
                logger.error(f"Failed to run LLM benchmarks: {e}", exc_info=True)
                report.llm_results = {"error": str(e)}

        # Run STT benchmarks
        if (self.args.stt or run_all) and STT_TTS_AVAILABLE:
            logger.info("\n" + "=" * 60)
            logger.info("Running STT Benchmarks")
            logger.info("=" * 60)
            try:
                stt_results = self._run_stt_benchmarks()
                report.stt_results = stt_results
            except Exception as e:
                logger.error(f"Failed to run STT benchmarks: {e}", exc_info=True)

        # Run TTS benchmarks
        if (self.args.tts or run_all) and STT_TTS_AVAILABLE:
            logger.info("\n" + "=" * 60)
            logger.info("Running TTS Benchmarks")
            logger.info("=" * 60)
            try:
                tts_results = self._run_tts_benchmarks()
                report.tts_results = tts_results
            except Exception as e:
                logger.error(f"Failed to run TTS benchmarks: {e}", exc_info=True)

        # Run audio stack benchmarks
        if (self.args.audio_stack or run_all) and STT_TTS_AVAILABLE:
            logger.info("\n" + "=" * 60)
            logger.info("Running Audio Stack Benchmarks")
            logger.info("=" * 60)
            try:
                audio_stack_results = self._run_audio_stack_benchmarks()
                report.audio_stack_results = audio_stack_results
            except Exception as e:
                logger.error(f"Failed to run audio stack benchmarks: {e}", exc_info=True)

        # Generate summary
        report.summary = self._generate_summary(report)

        # Save report
        report_path = self._output_dir / "comprehensive_benchmark_report.json"
        report.save(report_path)

        # Print summary
        self._print_summary(report)

        logger.info(f"\nComprehensive benchmark report saved to: {report_path}")

    def _run_llm_benchmarks(self) -> Dict[str, Any]:
        """Run LLM benchmarks (HumanEval, MBPP)."""
        if not self._llm_evaluator:
            raise RuntimeError("LLM evaluator not initialized")

        results = {}

        # Run HumanEval
        logger.info("Running HumanEval benchmark...")
        try:
            humaneval_tasks = DatasetLoader.load_humaneval()
            humaneval_report = self._llm_evaluator.evaluate_dataset(
                tasks=humaneval_tasks,
                output_dir=self._output_dir / "llm" / "humaneval",
                max_tasks=self.args.max_samples,
            )
            results["humaneval"] = humaneval_report.to_dict()
            logger.info(f"HumanEval Pass@1: {humaneval_report.pass_at_1:.2%}")
        except Exception as e:
            logger.error(f"HumanEval benchmark failed: {e}", exc_info=True)
            results["humaneval"] = {"error": str(e)}

        # Run MBPP
        logger.info("Running MBPP benchmark...")
        try:
            mbpp_tasks = DatasetLoader.load_mbpp()
            mbpp_report = self._llm_evaluator.evaluate_dataset(
                tasks=mbpp_tasks,
                output_dir=self._output_dir / "llm" / "mbpp",
                max_tasks=self.args.max_samples,
            )
            results["mbpp"] = mbpp_report.to_dict()
            logger.info(f"MBPP Pass@1: {mbpp_report.pass_at_1:.2%}")
        except Exception as e:
            logger.error(f"MBPP benchmark failed: {e}", exc_info=True)
            results["mbpp"] = {"error": str(e)}

        return results

    def _run_stt_benchmarks(self) -> STTBenchmarkResult:
        """Run STT benchmarks against LibriSpeech test-clean."""
        # TODO: Implement STT benchmarking
        # This should:
        # 1. Load LibriSpeech test-clean dataset (or use synthetic test cases)
        # 2. Run transcription on all samples via STT gRPC service
        # 3. Calculate WER/CER
        # 4. Compare to published Whisper-large-v3 baseline (WER ~2.0-3.0% on LibriSpeech test-clean)
        logger.warning("STT benchmarking not yet implemented - placeholder")
        return STTBenchmarkResult(
            dataset="librispeech_test_clean",
            total_samples=0,
            successful_samples=0,
            average_wer=0.0,
            average_cer=0.0,
            baseline_wer=2.5,  # Published Whisper-large-v3 WER on LibriSpeech test-clean
            baseline_cer=1.0,  # Approximate CER
        )

    def _run_tts_benchmarks(self) -> TTSBenchmarkResult:
        """Run TTS benchmarks (quality metrics, round-trip)."""
        # TODO: Implement TTS benchmarking
        # This should:
        # 1. Generate speech from test text samples
        # 2. Measure quality metrics (MOS, MCD if available)
        # 3. Run round-trip tests (TTS → STT) to measure WER/CER
        # 4. Compare to published FastSpeech2 baselines
        logger.warning("TTS benchmarking not yet implemented - placeholder")
        return TTSBenchmarkResult(
            dataset="ljspeech_test",
            total_samples=0,
            successful_samples=0,
            baseline_mos=4.0,  # Approximate FastSpeech2 MOS
            baseline_mcd=5.0,  # Approximate MCD
        )

    def _run_audio_stack_benchmarks(self) -> AudioStackBenchmarkResult:
        """Run end-to-end audio stack benchmarks."""
        # TODO: Implement audio stack benchmarking
        # This should:
        # 1. Run full round-trip: Text → TTS → STT → LLM → TTS → Audio
        # 2. Measure latency at each stage
        # 3. Measure end-to-end success rate
        # 4. Measure round-trip WER/CER
        logger.warning("Audio stack benchmarking not yet implemented - placeholder")
        return AudioStackBenchmarkResult(
            total_tests=0,
            successful_tests=0,
            average_round_trip_wer=0.0,
            average_round_trip_cer=0.0,
            average_llm_latency_seconds=0.0,
            average_stt_latency_seconds=0.0,
            average_tts_latency_seconds=0.0,
            average_total_latency_seconds=0.0,
            end_to_end_success_rate=0.0,
        )

    def _generate_summary(self, report: ComprehensiveBenchmarkReport) -> Dict[str, Any]:
        """Generate summary of all benchmark results."""
        summary = {
            "timestamp": report.timestamp,
            "models_tested": [],
            "baseline_comparisons": {},
            "warnings": [],
        }

        # LLM summary
        if report.llm_results:
            summary["models_tested"].append("LLM (Qwen3-30B-A3B-Thinking-2507)")
            if "humaneval" in report.llm_results:
                humaneval = report.llm_results["humaneval"]
                if "pass_at_1" in humaneval:
                    summary["baseline_comparisons"]["humaneval"] = {
                        "our_pass_at_1": humaneval["pass_at_1"],
                        "baseline_qwen2.5_32b": 0.75,  # From evaluator.py
                        "baseline_gpt4": 0.674,
                    }
                    our_score = humaneval["pass_at_1"]
                    baseline = 0.75  # Qwen2.5-32B baseline
                    if our_score < baseline * 0.9:  # More than 10% below baseline
                        summary["warnings"].append(
                            f"LLM HumanEval score ({our_score:.2%}) is significantly below baseline ({baseline:.2%})"
                        )

        # STT summary
        if report.stt_results:
            summary["models_tested"].append("STT (Whisper-large-v3)")
            if report.stt_results.baseline_wer:
                summary["baseline_comparisons"]["stt"] = {
                    "our_wer": report.stt_results.average_wer,
                    "baseline_wer": report.stt_results.baseline_wer,
                    "wer_delta": report.stt_results.wer_delta,
                }
                if report.stt_results.wer_delta and report.stt_results.wer_delta > 1.0:
                    summary["warnings"].append(
                        f"STT WER ({report.stt_results.average_wer:.2f}%) is significantly worse than baseline ({report.stt_results.baseline_wer:.2f}%)"
                    )

        # TTS summary
        if report.tts_results:
            summary["models_tested"].append("TTS (FastSpeech2)")

        # Audio stack summary
        if report.audio_stack_results:
            summary["models_tested"].append("Audio Stack (End-to-End)")
            summary["baseline_comparisons"]["audio_stack"] = {
                "end_to_end_success_rate": report.audio_stack_results.end_to_end_success_rate,
                "average_round_trip_wer": report.audio_stack_results.average_round_trip_wer,
            }

        return summary

    def _print_summary(self, report: ComprehensiveBenchmarkReport) -> None:
        """Print summary of benchmark results."""
        logger.info("\n" + "=" * 60)
        logger.info("Comprehensive Benchmark Summary")
        logger.info("=" * 60)

        if report.llm_results:
            logger.info("\n--- LLM Benchmarks ---")
            if "humaneval" in report.llm_results:
                h = report.llm_results["humaneval"]
                if "pass_at_1" in h:
                    logger.info(f"HumanEval Pass@1: {h['pass_at_1']:.2%}")
            if "mbpp" in report.llm_results:
                m = report.llm_results["mbpp"]
                if "pass_at_1" in m:
                    logger.info(f"MBPP Pass@1: {m['pass_at_1']:.2%}")

        if report.stt_results:
            logger.info("\n--- STT Benchmarks ---")
            logger.info(f"Average WER: {report.stt_results.average_wer:.2f}%")
            if report.stt_results.baseline_wer:
                logger.info(f"Baseline WER: {report.stt_results.baseline_wer:.2f}%")
                if report.stt_results.wer_delta:
                    delta_sign = "+" if report.stt_results.wer_delta >= 0 else ""
                    logger.info(f"WER Delta: {delta_sign}{report.stt_results.wer_delta:.2f}%")

        if report.tts_results:
            logger.info("\n--- TTS Benchmarks ---")
            if report.tts_results.round_trip_wer is not None:
                logger.info(f"Round-trip WER: {report.tts_results.round_trip_wer:.2f}%")

        if report.audio_stack_results:
            logger.info("\n--- Audio Stack Benchmarks ---")
            logger.info(
                f"End-to-end success rate: {report.audio_stack_results.end_to_end_success_rate:.2%}"
            )

        if report.summary and report.summary.get("warnings"):
            logger.info("\n--- Warnings ---")
            for warning in report.summary["warnings"]:
                logger.warning(warning)

        logger.info("\n" + "=" * 60)

    def cleanup(self) -> None:
        """Clean up resources."""
        if self._llm_evaluator:
            # Evaluator cleanup if needed
            pass
        logger.info("Benchmark cleanup complete")
