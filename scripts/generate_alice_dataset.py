#!/usr/bin/env python3
"""
Generate Alice's Adventures in Wonderland Dataset
Extracts random 2-3 sentence passages for audio testing.
"""
import os
import re
import random
import json
import urllib.request
from pathlib import Path
from typing import List, Dict
from datetime import datetime

def download_book(url: str, output_path: str) -> bool:
    """Download the book from Project Gutenberg."""
    try:
        print(f"Downloading book from {url}...")
        urllib.request.urlretrieve(url, output_path)
        print(f"✅ Book downloaded to {output_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to download book: {e}")
        return False

def load_book(file_path: str) -> str:
    """Load the book text from file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"✅ Loaded book from {file_path}")
        return content
    except Exception as e:
        print(f"❌ Failed to load book: {e}")
        return ""

def clean_text(text: str) -> str:
    """Clean the Project Gutenberg text to extract just the story."""
    # Remove Project Gutenberg header/footer
    # Look for "*** START OF THE PROJECT GUTENBERG EBOOK"
    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"
    
    start_idx = text.find(start_marker)
    end_idx = text.find(end_marker)
    
    if start_idx != -1 and end_idx != -1:
        text = text[start_idx:end_idx]
    
    # Remove Project Gutenberg markers
    text = re.sub(r'\*\*\* START.*?\*\*\*', '', text, flags=re.DOTALL)
    text = re.sub(r'\*\*\* END.*?\*\*\*', '', text, flags=re.DOTALL)
    
    # Remove illustration markers
    text = re.sub(r'\[Illustration\]', '', text)
    
    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    
    return text.strip()

def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    # Simple sentence splitting - can be improved
    # Look for sentence endings followed by space and capital letter
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    
    # Filter out very short fragments and clean up
    cleaned = []
    for sent in sentences:
        sent = sent.strip()
        # Remove sentences that are too short (likely fragments)
        if len(sent) > 20 and not sent.startswith('CHAPTER'):
            cleaned.append(sent)
    
    return cleaned

def extract_passages(sentences: List[str], num_passages: int = 100, min_sentences: int = 2, max_sentences: int = 3) -> List[Dict[str, str]]:
    """Extract random passages of 2-3 sentences."""
    passages = []
    
    if len(sentences) < max_sentences:
        print(f"⚠️  Not enough sentences in book (found {len(sentences)})")
        return passages
    
    print(f"Extracting {num_passages} random passages...")
    
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
        passage_text = ' '.join(passage_sentences)
        
        # Filter out passages that are too short or too long
        if 50 <= len(passage_text) <= 500:
            # Check for duplicates
            if passage_text not in [p['text'] for p in passages]:
                passages.append({
                    'id': len(passages) + 1,
                    'text': passage_text,
                    'num_sentences': len(passage_sentences),
                    'char_count': len(passage_text),
                    'word_count': len(passage_text.split())
                })
    
    print(f"✅ Generated {len(passages)} unique passages")
    return passages

def save_dataset(passages: List[Dict], dataset_dir: Path):
    """Save the dataset to JSON file."""
    dataset_file = dataset_dir / 'alice_dataset.json'
    
    dataset = {
        'metadata': {
            'source': 'Alice\'s Adventures in Wonderland by Lewis Carroll',
            'source_url': 'https://www.gutenberg.org/cache/epub/11/pg11.txt',
            'generated_at': datetime.now().isoformat(),
            'total_passages': len(passages),
            'extraction_params': {
                'min_sentences': 2,
                'max_sentences': 3,
                'min_length': 50,
                'max_length': 500
            }
        },
        'passages': passages
    }
    
    with open(dataset_file, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Dataset saved to {dataset_file}")
    return dataset_file

def main():
    """Main function."""
    # Get data directory from environment
    data_dir = os.getenv('JUNE_DATA_DIR', '/home/rlee/june_data')
    dataset_dir = Path(data_dir) / 'datasets' / 'alice_in_wonderland'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Dataset directory: {dataset_dir}")
    
    # Book file path
    book_file = dataset_dir / 'alice_adventures_in_wonderland.txt'
    book_url = 'https://www.gutenberg.org/cache/epub/11/pg11.txt'
    
    # Download book if it doesn't exist
    if not book_file.exists():
        if not download_book(book_url, str(book_file)):
            print("❌ Failed to download book. Exiting.")
            return 1
    
    # Load and clean book
    print("\nLoading and cleaning book...")
    book_text = load_book(str(book_file))
    if not book_text:
        print("❌ Failed to load book. Exiting.")
        return 1
    
    cleaned_text = clean_text(book_text)
    print(f"✅ Cleaned text: {len(cleaned_text)} characters")
    
    # Split into sentences
    print("\nSplitting into sentences...")
    sentences = split_into_sentences(cleaned_text)
    print(f"✅ Found {len(sentences)} sentences")
    
    # Extract passages
    print("\nExtracting random passages...")
    passages = extract_passages(sentences, num_passages=100, min_sentences=2, max_sentences=3)
    
    if len(passages) < 100:
        print(f"⚠️  Warning: Only generated {len(passages)} passages (requested 100)")
    
    # Save dataset
    print("\nSaving dataset...")
    dataset_file = save_dataset(passages, dataset_dir)
    
    # Print summary
    print("\n" + "=" * 60)
    print("DATASET GENERATION SUMMARY")
    print("=" * 60)
    print(f"Total passages: {len(passages)}")
    print(f"Average passage length: {sum(p['char_count'] for p in passages) / len(passages):.1f} characters")
    print(f"Average word count: {sum(p['word_count'] for p in passages) / len(passages):.1f} words")
    print(f"Dataset file: {dataset_file}")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    exit(main())





