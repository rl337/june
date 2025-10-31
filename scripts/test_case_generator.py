#!/usr/bin/env python3
"""
Test Case Generator for TTS/STT Validation

Generates diverse test cases organized by:
- Short phrases (1-3 words)
- Medium phrases (4-10 words)
- Long phrases (11+ words)

Target: ~1000 test cases total with good coverage.
"""
import random
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class TestCase:
    """A single test case."""
    text: str
    category: str  # "short", "medium", "long"
    subcategory: str  # e.g., "greetings", "numbers", "questions"


class TestCaseGenerator:
    """Generates diverse test cases for TTS/STT validation."""
    
    def __init__(self):
        # Common single words (high frequency)
        self.single_words = [
            "Hello", "World", "Test", "Yes", "No", "Good", "Bad", "Up", "Down",
            "Left", "Right", "Start", "Stop", "Go", "Run", "Walk", "Jump",
            "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Red", "Blue", "Green", "Yellow", "Black", "White", "Big", "Small",
            "Hot", "Cold", "Fast", "Slow", "High", "Low", "New", "Old", "Day", "Night"
        ]
        
        # Common two-word phrases
        self.two_word_phrases = [
            "Hello world", "Good morning", "Good night", "Thank you", "Please stop",
            "Yes please", "No thanks", "Very good", "Not bad", "How are",
            "What time", "Where is", "Who are", "Why do", "When will",
            "Red car", "Blue sky", "Big house", "Small dog", "Hot water",
            "Cold wind", "Fast car", "Slow walk", "High tower", "Low ground",
            "New book", "Old tree", "Day time", "Night sky", "Good day"
        ]
        
        # Common three-word phrases
        self.three_word_phrases = [
            "The quick brown", "How are you", "What is that", "Where are we",
            "Who is there", "Why did you", "When can we", "Please come here",
            "Thank you very", "Yes I can", "No I cannot", "Very good morning",
            "Good night sleep", "Hello my friend", "See you later", "Have a nice",
            "What is this", "How do you", "Where is the", "Who is this",
            "Red white blue", "One two three", "Start the engine", "Stop the music",
            "Turn it on", "Turn it off", "Make it work", "Let it go"
        ]
        
        # Template phrases for medium-length
        self.medium_templates = [
            "The {adjective} {noun} {verb} over the {noun}",
            "I {verb} to the {place} every {time}",
            "This is a {adjective} {noun} that {verb} very {adverb}",
            "We need to {verb} the {noun} before {time}",
            "The {noun} {verb} {adjective} in the {place}",
            "{Number} {noun} went to {place}",
            "Can you {verb} the {noun} please",
            "I want to {verb} a {adjective} {noun}",
            "The {color} {noun} is {adjective}",
            "Please {verb} the {noun} now"
        ]
        
        # Template phrases for long sentences
        self.long_templates = [
            "The {adjective} {noun} {verb} over the {adjective} {noun} in the {place}",
            "I {verb} to the {place} every {time} to {verb} the {noun}",
            "This is a {adjective} {noun} that {verb} very {adverb} in the {place}",
            "We need to {verb} the {noun} before {time} so we can {verb} properly",
            "The {noun} {verb} {adjective} in the {place} while the {noun} {verb}",
            "{Number} {noun} went to {place} to {verb} and {verb}",
            "Can you {verb} the {noun} please so we can {verb} together",
            "I want to {verb} a {adjective} {noun} because it is {adjective}",
            "The {color} {noun} is {adjective} and it {verb} very {adverb}",
            "Please {verb} the {noun} now because we need to {verb} soon"
        ]
        
        # Vocabulary for templates
        self.adjectives = [
            "quick", "brown", "lazy", "smart", "fast", "slow", "big", "small",
            "red", "blue", "green", "yellow", "hot", "cold", "new", "old",
            "good", "bad", "nice", "great", "wonderful", "amazing", "beautiful"
        ]
        self.nouns = [
            "fox", "dog", "cat", "car", "house", "tree", "book", "pen",
            "computer", "phone", "door", "window", "table", "chair", "desk",
            "person", "child", "man", "woman", "friend", "teacher", "student"
        ]
        self.verbs = [
            "jumps", "runs", "walks", "flies", "swims", "goes", "comes", "stays",
            "works", "plays", "reads", "writes", "speaks", "listens", "watches",
            "eats", "drinks", "sleeps", "wakes", "starts", "stops", "opens", "closes"
        ]
        self.adverbs = [
            "quickly", "slowly", "carefully", "quietly", "loudly", "softly",
            "easily", "hardly", "well", "badly", "nicely", "properly"
        ]
        self.places = [
            "store", "school", "park", "home", "office", "library", "restaurant",
            "hospital", "museum", "theater", "beach", "mountain", "forest"
        ]
        self.times = [
            "morning", "afternoon", "evening", "night", "day", "week", "month",
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
        ]
        self.colors = [
            "red", "blue", "green", "yellow", "orange", "purple", "pink", "brown",
            "black", "white", "gray", "silver", "gold"
        ]
        self.numbers = [
            "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
            "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen"
        ]
    
    def generate_short_cases(self, count: int = 300) -> List[TestCase]:
        """Generate short phrase test cases (1-3 words)."""
        cases = []
        
        # Single words
        for word in self.single_words:
            cases.append(TestCase(word, "short", "single_word"))
        
        # Two-word phrases
        for phrase in self.two_word_phrases:
            cases.append(TestCase(phrase, "short", "two_words"))
        
        # Three-word phrases
        for phrase in self.three_word_phrases:
            cases.append(TestCase(phrase, "short", "three_words"))
        
        # Generate additional random combinations
        remaining = count - len(cases)
        for _ in range(remaining):
            if random.random() < 0.4:  # 40% single words
                word = random.choice(self.single_words)
                cases.append(TestCase(word, "short", "single_word_random"))
            elif random.random() < 0.7:  # 30% two words
                word1 = random.choice(self.single_words)
                word2 = random.choice(self.single_words)
                cases.append(TestCase(f"{word1} {word2}", "short", "two_words_random"))
            else:  # 30% three words
                word1 = random.choice(self.single_words)
                word2 = random.choice(self.single_words)
                word3 = random.choice(self.single_words)
                cases.append(TestCase(f"{word1} {word2} {word3}", "short", "three_words_random"))
        
        return cases[:count]
    
    def generate_medium_cases(self, count: int = 400) -> List[TestCase]:
        """Generate medium phrase test cases (4-10 words)."""
        cases = []
        
        # Use templates with random vocabulary
        for template in self.medium_templates:
            for _ in range(count // len(self.medium_templates)):
                # Fill template with random words
                text = template.format(
                    adjective=random.choice(self.adjectives),
                    noun=random.choice(self.nouns),
                    verb=random.choice(self.verbs),
                    adverb=random.choice(self.adverbs),
                    place=random.choice(self.places),
                    time=random.choice(self.times),
                    color=random.choice(self.colors),
                    Number=random.choice(self.numbers)
                )
                cases.append(TestCase(text, "medium", "template"))
        
        # Generate random combinations
        remaining = count - len(cases)
        for _ in range(remaining):
            num_words = random.randint(4, 10)
            words = []
            for _ in range(num_words):
                if random.random() < 0.3:
                    words.append(random.choice(self.adjectives))
                elif random.random() < 0.5:
                    words.append(random.choice(self.nouns))
                elif random.random() < 0.7:
                    words.append(random.choice(self.verbs))
                else:
                    words.append(random.choice(self.single_words))
            cases.append(TestCase(" ".join(words), "medium", "random"))
        
        return cases[:count]
    
    def generate_long_cases(self, count: int = 300) -> List[TestCase]:
        """Generate long phrase test cases (11+ words)."""
        cases = []
        
        # Use long templates
        for template in self.long_templates:
            for _ in range(count // len(self.long_templates)):
                text = template.format(
                    adjective=random.choice(self.adjectives),
                    noun=random.choice(self.nouns),
                    verb=random.choice(self.verbs),
                    adverb=random.choice(self.adverbs),
                    place=random.choice(self.places),
                    time=random.choice(self.times),
                    color=random.choice(self.colors),
                    Number=random.choice(self.numbers)
                )
                cases.append(TestCase(text, "long", "template"))
        
        # Generate random long combinations
        remaining = count - len(cases)
        for _ in range(remaining):
            num_words = random.randint(11, 20)
            words = []
            for _ in range(num_words):
                if random.random() < 0.25:
                    words.append(random.choice(self.adjectives))
                elif random.random() < 0.45:
                    words.append(random.choice(self.nouns))
                elif random.random() < 0.65:
                    words.append(random.choice(self.verbs))
                elif random.random() < 0.75:
                    words.append(random.choice(self.adverbs))
                else:
                    words.append(random.choice(self.single_words))
            cases.append(TestCase(" ".join(words), "long", "random"))
        
        return cases[:count]
    
    def generate_all(self, short_count: int = 300, medium_count: int = 400, long_count: int = 300) -> List[TestCase]:
        """Generate all test cases across all categories."""
        all_cases = []
        all_cases.extend(self.generate_short_cases(short_count))
        all_cases.extend(self.generate_medium_cases(medium_count))
        all_cases.extend(self.generate_long_cases(long_count))
        return all_cases
    
    def get_statistics(self, cases: List[TestCase]) -> dict:
        """Get statistics about generated test cases."""
        stats = {
            "total": len(cases),
            "by_category": {},
            "by_subcategory": {},
            "word_counts": []
        }
        
        for case in cases:
            stats["by_category"][case.category] = stats["by_category"].get(case.category, 0) + 1
            stats["by_subcategory"][case.subcategory] = stats["by_subcategory"].get(case.subcategory, 0) + 1
            stats["word_counts"].append(len(case.text.split()))
        
        stats["avg_words"] = sum(stats["word_counts"]) / len(stats["word_counts"]) if stats["word_counts"] else 0
        stats["min_words"] = min(stats["word_counts"]) if stats["word_counts"] else 0
        stats["max_words"] = max(stats["word_counts"]) if stats["word_counts"] else 0
        
        return stats


def main():
    """Generate and display test cases."""
    generator = TestCaseGenerator()
    
    # Generate ~1000 test cases
    cases = generator.generate_all(short_count=300, medium_count=400, long_count=300)
    
    # Display statistics
    stats = generator.get_statistics(cases)
    print(f"Generated {stats['total']} test cases")
    print(f"\nBy category:")
    for cat, count in sorted(stats["by_category"].items()):
        print(f"  {cat}: {count}")
    print(f"\nWord count: min={stats['min_words']}, max={stats['max_words']}, avg={stats['avg_words']:.1f}")
    
    # Display sample cases
    print(f"\nSample cases (first 10):")
    for i, case in enumerate(cases[:10], 1):
        print(f"  {i}. [{case.category}] {case.text}")


if __name__ == "__main__":
    main()

