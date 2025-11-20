"""
Benchmark Dataset Loaders

Loads benchmark datasets (HumanEval, MBPP, etc.) from various sources.
All datasets are loaded in containers - no host system pollution.
"""
import json
import logging
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Optional

from essence.agents.evaluator import BenchmarkTask

logger = logging.getLogger(__name__)


class DatasetLoader:
    """Loader for benchmark datasets."""

    @staticmethod
    def load_humaneval(
        data_path: Optional[Path] = None,
        download_if_missing: bool = True,
    ) -> List[BenchmarkTask]:
        """
        Load HumanEval dataset.

        Args:
            data_path: Path to HumanEval data file (JSONL format)
            download_if_missing: If True, download dataset if not found

        Returns:
            List of BenchmarkTask objects
        """
        if data_path is None:
            data_path = Path("/tmp/benchmarks/humaneval/data/HumanEval.jsonl")

        # Download if missing
        if not data_path.exists() and download_if_missing:
            logger.info("Downloading HumanEval dataset...")
            DatasetLoader._download_humaneval(data_path.parent)

        if not data_path.exists():
            raise FileNotFoundError(f"HumanEval dataset not found at {data_path}")

        tasks = []
        with open(data_path, "r") as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line.strip())
                    task = BenchmarkTask(
                        task_id=f"humaneval_{data['task_id']}",
                        dataset="humaneval",
                        prompt=data["prompt"],
                        canonical_solution=data.get("canonical_solution"),
                        test_code=data.get("test"),
                        entry_point=data.get("entry_point"),
                        metadata={
                            "original_task_id": data["task_id"],
                            "line_number": line_num,
                        },
                    )
                    tasks.append(task)
                except Exception as e:
                    logger.warning(f"Failed to parse HumanEval line {line_num}: {e}")

        logger.info(f"Loaded {len(tasks)} HumanEval tasks")
        return tasks

    @staticmethod
    def load_mbpp(
        data_path: Optional[Path] = None,
        download_if_missing: bool = True,
    ) -> List[BenchmarkTask]:
        """
        Load MBPP (Mostly Basic Python Problems) dataset.

        Args:
            data_path: Path to MBPP data file (JSON format)
            download_if_missing: If True, download dataset if not found

        Returns:
            List of BenchmarkTask objects
        """
        if data_path is None:
            data_path = Path("/tmp/benchmarks/mbpp/data/mbpp.json")

        # Download if missing
        if not data_path.exists() and download_if_missing:
            logger.info("Downloading MBPP dataset...")
            DatasetLoader._download_mbpp(data_path.parent)

        if not data_path.exists():
            raise FileNotFoundError(f"MBPP dataset not found at {data_path}")

        tasks = []
        with open(data_path, "r") as f:
            data = json.load(f)
            for item in data:
                try:
                    # MBPP format: each item has 'task_id', 'text', 'code', 'test_list'
                    task_id = item.get("task_id", str(item.get("id", "")))
                    prompt = item.get("text", "")
                    canonical_solution = item.get("code", "")
                    test_list = item.get("test_list", [])

                    # Combine test_list into test_code
                    test_code = "\n".join(test_list) if test_list else None

                    task = BenchmarkTask(
                        task_id=f"mbpp_{task_id}",
                        dataset="mbpp",
                        prompt=prompt,
                        canonical_solution=canonical_solution,
                        test_code=test_code,
                        entry_point=None,
                        metadata={
                            "original_task_id": task_id,
                            "test_count": len(test_list),
                        },
                    )
                    tasks.append(task)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse MBPP item {item.get('task_id', 'unknown')}: {e}"
                    )

        logger.info(f"Loaded {len(tasks)} MBPP tasks")
        return tasks

    @staticmethod
    def _download_humaneval(output_dir: Path) -> None:
        """Download HumanEval dataset from GitHub."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # HumanEval is available from OpenAI's GitHub
        url = "https://github.com/openai/human-eval/raw/master/data/HumanEval.jsonl.gz"

        try:
            logger.info(f"Downloading HumanEval from {url}...")

            # Download to temporary file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".jsonl.gz"
            ) as tmp_file:
                urllib.request.urlretrieve(url, tmp_file.name)

                # Extract gzip
                import gzip

                with gzip.open(tmp_file.name, "rb") as gz_file:
                    output_file = output_dir / "HumanEval.jsonl"
                    with open(output_file, "wb") as out_file:
                        out_file.write(gz_file.read())

                # Clean up
                Path(tmp_file.name).unlink()

            logger.info(f"Downloaded HumanEval to {output_dir}")
        except Exception as e:
            logger.error(f"Failed to download HumanEval: {e}")
            raise

    @staticmethod
    def _download_mbpp(output_dir: Path) -> None:
        """Download MBPP dataset."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # MBPP is available from various sources
        # For now, we'll use a placeholder URL - users should download manually
        # or provide their own path
        logger.warning(
            "MBPP dataset download not implemented. "
            "Please download MBPP manually and place it at the data_path, "
            "or use a dataset loader that supports MBPP."
        )

        # Create a placeholder file with instructions
        readme_file = output_dir / "README.md"
        readme_file.write_text(
            """
# MBPP Dataset

Please download the MBPP dataset from:
https://github.com/google-research/google-research/tree/master/mbpp

Or use the HuggingFace dataset:
https://huggingface.co/datasets/mbpp

Place the dataset file (mbpp.json) in this directory.
"""
        )

        raise FileNotFoundError(
            "MBPP dataset not found. Please download it manually or use a "
            "HuggingFace dataset loader."
        )
