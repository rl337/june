"""
Generate Alice's Adventures in Wonderland dataset command.

Usage:
    poetry run -m essence generate-alice-dataset [--output-dir DIR] [--num-passages N]

This command generates a dataset of random 2-3 sentence passages from Alice's Adventures
in Wonderland for audio testing purposes.
"""
import argparse
import json
import logging
import os
import random
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from essence.command import Command

logger = logging.getLogger(__name__)


def download_book(url: str, output_path: Path) -> bool:
    """Download the book from Project Gutenberg."""
    try:
        logger.info(f"Downloading book from {url}...")
        urllib.request.urlretrieve(url, str(output_path))
        logger.info(f"Book downloaded to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to download book: {e}")
        return False


def load_book(file_path: Path) -> str:
    """Load the book text from file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Loaded book from {file_path}")
        return content
    except Exception as e:
        logger.error(f"Failed to load book: {e}")
        return ""


def clean_text(text: str) -> str:
    """Clean the Project Gutenberg text to extract just the story."""
    # Remove Project Gutenberg header/footer
    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"

    start_idx = text.find(start_marker)
    end_idx = text.find(end_marker)

    if start_idx != -1 and end_idx != -1:
        text = text[start_idx:end_idx]

    # Remove Project Gutenberg markers
    text = re.sub(r"\*\*\* START.*?\*\*\*", "", text, flags=re.DOTALL)
    text = re.sub(r"\*\*\* END.*?\*\*\*", "", text, flags=re.DOTALL)

    # Remove illustration markers
    text = re.sub(r"\[Illustration\]", "", text)

    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)

    return text.strip()


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    # Simple sentence splitting
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)

    # Filter out very short fragments and clean up
    cleaned = []
    for sent in sentences:
        sent = sent.strip()
        # Remove sentences that are too short (likely fragments)
        if len(sent) > 20 and not sent.startswith("CHAPTER"):
            cleaned.append(sent)

    return cleaned


def extract_passages(
    sentences: List[str],
    num_passages: int = 100,
    min_sentences: int = 2,
    max_sentences: int = 3,
) -> List[Dict[str, str]]:
    """Extract random passages of 2-3 sentences."""
    passages = []

    if len(sentences) < max_sentences:
        logger.warning(f"Not enough sentences in book (found {len(sentences)})")
        return passages

    logger.info(f"Extracting {num_passages} random passages...")

    # Generate random passages
    attempts = 0
    max_attempts = num_passages * 10

    while len(passages) < num_passages and attempts < max_attempts:
        attempts += 1

        # Random starting position
        start_idx = random.randint(0, len(sentences) - max_sentences)

        # Random number of sentences (2 or 3)
        num_sent = random.randint(min_sentences, max_sentences)

        # Extract passage
        end_idx = min(start_idx + num_sent, len(sentences))
        passage_sentences = sentences[start_idx:end_idx]

        # Combine into passage
        passage_text = " ".join(passage_sentences)

        # Filter out passages that are too short or too long
        if 50 <= len(passage_text) <= 500:
            # Check for duplicates
            if passage_text not in [p["text"] for p in passages]:
                passages.append(
                    {
                        "id": len(passages) + 1,
                        "text": passage_text,
                        "num_sentences": len(passage_sentences),
                        "char_count": len(passage_text),
                        "word_count": len(passage_text.split()),
                    }
                )

    logger.info(f"Generated {len(passages)} unique passages")
    return passages


def save_dataset(passages: List[Dict], dataset_dir: Path) -> Path:
    """Save the dataset to JSON file."""
    dataset_file = dataset_dir / "alice_dataset.json"

    dataset = {
        "metadata": {
            "source": "Alice's Adventures in Wonderland by Lewis Carroll",
            "source_url": "https://www.gutenberg.org/cache/epub/11/pg11.txt",
            "generated_at": datetime.now().isoformat(),
            "total_passages": len(passages),
            "extraction_params": {
                "min_sentences": 2,
                "max_sentences": 3,
                "min_length": 50,
                "max_length": 500,
            },
        },
        "passages": passages,
    }

    with open(dataset_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    logger.info(f"Dataset saved to {dataset_file}")
    return dataset_file


class GenerateAliceDatasetCommand(Command):
    """
    Command for generating Alice's Adventures in Wonderland dataset.

    Downloads the full text of Alice's Adventures in Wonderland from Project Gutenberg,
    processes it into passages of configurable length, and saves it as a JSON dataset
    for use in audio testing (STT/TTS evaluation).

    The dataset consists of random passages extracted from the book, with configurable
    sentence counts per passage. Useful for testing speech-to-text and text-to-speech
    systems with natural language content.
    """

    def __init__(self, args: argparse.Namespace):
        """
        Initialize command with parsed arguments.

        Args:
            args: Parsed command-line arguments containing dataset generation configuration
        """
        super().__init__(args)
        self._dataset_dir = None

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "generate-alice-dataset"
        """
        return "generate-alice-dataset"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Generate Alice's Adventures in Wonderland dataset for audio testing"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures dataset generation parameters including output directory,
        number of passages, sentence counts per passage, and download options.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=Path(os.getenv("JUNE_DATA_DIR", "/home/rlee/june_data"))
            / "datasets"
            / "alice_in_wonderland",
            help="Output directory for dataset (default: $JUNE_DATA_DIR/datasets/alice_in_wonderland)",
        )
        parser.add_argument(
            "--num-passages",
            type=int,
            default=int(os.getenv("ALICE_DATASET_NUM_PASSAGES", "100")),
            help="Number of passages to generate (default: 100)",
        )
        parser.add_argument(
            "--min-sentences",
            type=int,
            default=2,
            help="Minimum sentences per passage (default: 2)",
        )
        parser.add_argument(
            "--max-sentences",
            type=int,
            default=3,
            help="Maximum sentences per passage (default: 3)",
        )
        parser.add_argument(
            "--force-download",
            action="store_true",
            help="Force re-download of book even if it exists",
        )

    def init(self) -> None:
        """
        Initialize dataset generation.

        Creates the output directory if it doesn't exist and sets up the dataset
        directory path for file operations.
        """
        # Create output directory
        self._dataset_dir = self.args.output_dir
        self._dataset_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Dataset directory: {self._dataset_dir}")

    def run(self) -> None:
        """
        Generate the dataset.

        Performs the complete dataset generation workflow:
        1. Downloads Alice's Adventures in Wonderland from Project Gutenberg (if needed)
        2. Loads and cleans the book text
        3. Splits text into sentences
        4. Extracts random passages with configured sentence counts
        5. Saves the dataset as JSON to the output directory

        Raises:
            RuntimeError: If book download or loading fails
        """
        # Book file path
        book_file = self._dataset_dir / "alice_adventures_in_wonderland.txt"
        book_url = "https://www.gutenberg.org/cache/epub/11/pg11.txt"

        # Download book if it doesn't exist or force download
        if not book_file.exists() or self.args.force_download:
            if not download_book(book_url, book_file):
                raise RuntimeError("Failed to download book. Exiting.")

        # Load and clean book
        logger.info("Loading and cleaning book...")
        book_text = load_book(book_file)
        if not book_text:
            raise RuntimeError("Failed to load book. Exiting.")

        cleaned_text = clean_text(book_text)
        logger.info(f"Cleaned text: {len(cleaned_text)} characters")

        # Split into sentences
        logger.info("Splitting into sentences...")
        sentences = split_into_sentences(cleaned_text)
        logger.info(f"Found {len(sentences)} sentences")

        # Extract passages
        logger.info("Extracting random passages...")
        passages = extract_passages(
            sentences,
            num_passages=self.args.num_passages,
            min_sentences=self.args.min_sentences,
            max_sentences=self.args.max_sentences,
        )

        if len(passages) < self.args.num_passages:
            logger.warning(
                f"Only generated {len(passages)} passages (requested {self.args.num_passages})"
            )

        # Save dataset
        logger.info("Saving dataset...")
        dataset_file = save_dataset(passages, self._dataset_dir)

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("DATASET GENERATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total passages: {len(passages)}")
        if passages:
            avg_chars = sum(p["char_count"] for p in passages) / len(passages)
            avg_words = sum(p["word_count"] for p in passages) / len(passages)
            logger.info(f"Average passage length: {avg_chars:.1f} characters")
            logger.info(f"Average word count: {avg_words:.1f} words")
        logger.info(f"Dataset file: {dataset_file}")
        logger.info("=" * 60)

    def cleanup(self) -> None:
        """Clean up dataset generation resources."""
        # No cleanup needed
        pass
