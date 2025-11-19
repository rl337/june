"""
Data-driven tests for chunk appending and markdown translation.

These tests validate that:
1. Assistant message chunks are correctly appended together
2. The appended chunks match the result message (full accumulated text)
3. The markdown translation produces the expected Telegram-formatted output

NOTE: This test only validates accumulation logic. For end-to-end streaming
behavior (including handler logic and result message overwriting), see
test_e2e_streaming.py. The accumulation test might pass trivially if we
just use the result message, but the e2e test ensures the full flow works.
"""

import json
import os

# Add parent directories to path
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "essence"))

from essence.chat.markdown_parser import parse_markdown
from essence.chat.platform_translators import get_translator


def load_test_data(filename):
    """Load JSON test data from file."""
    # Test data is now in tests/data at the root
    test_data_dir = Path(__file__).parent.parent.parent.parent.parent / "data"
    file_path = test_data_dir / filename

    if not file_path.exists():
        pytest.skip(f"Test data file not found: {file_path}")

    with open(file_path, "r") as f:
        lines = [
            line.strip() for line in f if line.strip() and line.strip().startswith("{")
        ]

    return lines


def extract_assistant_chunks(json_lines):
    """Extract all assistant message chunks from JSON lines."""
    chunks = []
    for line in json_lines:
        try:
            obj = json.loads(line)
            if obj.get("type") == "assistant":
                content = obj.get("message", {}).get("content", [])
                if content and len(content) > 0:
                    text = content[0].get("text", "")
                    if text:
                        chunks.append(text)
        except (json.JSONDecodeError, KeyError):
            continue
    return chunks


def extract_result_message(json_lines):
    """Extract the result message (full accumulated text) from JSON lines."""
    for line in json_lines:
        try:
            obj = json.loads(line)
            if obj.get("type") == "result" and obj.get("subtype") == "success":
                result = obj.get("result", "")
                if result:
                    return result
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def append_chunks_directly(chunks):
    """
    Append chunks together directly without adding separators.

    This mimics the simplified logic: just concatenate chunks as-is.
    However, if a chunk contains the accumulated message, it's the full accumulated
    and should replace (not append). Also skip chunks that are prefixes of what we already have.

    Additionally, if a chunk is significantly longer and appears to be a full restart
    (starts with the same pattern as the first chunk), it's likely the full accumulated message.
    """
    if not chunks:
        return ""

    accumulated = chunks[0]
    first_chunk_start = (
        chunks[0][:20] if len(chunks[0]) >= 20 else chunks[0]
    )  # First 20 chars as pattern

    for chunk in chunks[1:]:
        # If chunk contains accumulated, it's the full accumulated message - replace
        if accumulated in chunk:
            accumulated = chunk
        elif chunk in accumulated:
            # This chunk is a prefix/substring of what we already have - skip it (duplicate/restart)
            continue
        elif len(chunk) > len(accumulated) * 0.8 and chunk.startswith(
            first_chunk_start
        ):
            # Chunk is significantly long and starts with the same pattern - likely full accumulated
            # This handles cases where cursor-agent sends the full message after sending partial chunks
            accumulated = chunk
        else:
            # Otherwise, append
            accumulated = accumulated + chunk

    return accumulated


# Test data files - comprehensive markdown coverage
TEST_FILES = [
    "test_headers.json",  # Headers (h1-h6)
    "test_lists.json",  # Bullet and numbered lists
    "test_code_block.json",  # Code blocks with syntax
    "test_formatting.json",  # Bold, italic, bold+italic
    "test_table.json",  # Tables
    "test_links.json",  # Links [text](url)
    "test_inline_code.json",  # Inline code with backticks
    "test_blockquote.json",  # Blockquotes (>)
    "test_strikethrough.json",  # Strikethrough (~~)
    "test_mixed.json",  # Mixed markdown (all types together)
    "test_duplication_headers.json",  # Headers with duplication issue (real-world case)
]


@pytest.mark.parametrize("test_file", TEST_FILES)
def test_chunk_appending_matches_result(test_file):
    """Test that appended assistant chunks match the result message."""
    json_lines = load_test_data(test_file)

    # Extract chunks and result
    assistant_chunks = extract_assistant_chunks(json_lines)
    result_message = extract_result_message(json_lines)

    # Skip if no data
    if not assistant_chunks:
        pytest.skip(f"No assistant chunks found in {test_file}")
    if not result_message:
        pytest.skip(f"No result message found in {test_file}")

    # Append chunks using our logic (direct concatenation with duplicate detection)
    appended = append_chunks_directly(assistant_chunks)

    # Normalize for comparison (handle potential newline differences)
    appended_normalized = appended.replace("\n\n", "\n").strip()
    result_normalized = result_message.replace("\n\n", "\n").strip()

    # Assert they match
    assert appended_normalized == result_normalized, (
        f"Appended chunks don't match result message.\n"
        f"Appended length: {len(appended)}, Result length: {len(result_message)}\n"
        f"Appended: {repr(appended[:200])}\n"
        f"Result: {repr(result_message[:200])}"
    )

    # Special check for duplication test: ensure no repeated content
    if "duplication" in test_file:
        # Check that the result doesn't contain the same header sequence multiple times
        # This test case captures a real-world scenario where cursor-agent sends
        # a full accumulated message (chunk 20) that should replace accumulated, not append
        header_sequence = "# Header 1\n\n## Header 2"
        occurrences = result_normalized.count(header_sequence)
        assert occurrences <= 1, (
            f"Found {occurrences} occurrences of header sequence - indicates duplication issue.\n"
            f"Result: {repr(result_normalized[:300])}"
        )


# Expected Telegram markdown translations (captured from actual translations)
EXPECTED_TRANSLATIONS = {
    "test_headers.json": """Markdown headers from H1 to H6:

*Header 1*

*Header 2*

*Header 3*

*Header 4*

*Header 5*

*Header 6*

Syntax:

• `# Header 1` — one hash
• `## Header 2` — two hashes
• `### Header 3` — three hashes
• `#### Header 4` — four hashes
• `##### Header 5` — five hashes
• `###### Header 6` — six hashes

Note: Add a space after the hashes. These are supported in Telegram when using markdown formatting.""",
    "test_lists.json": """Here are examples of bullet points and numbered lists:

**Bullet points:**

• First item
• Second item
• Third item
  • Nested bullet
  • Another nested item

**Numbered list:**

1. First numbered item
2. Second numbered item
3. Third numbered item
  • Nested numbered item
  • Another nested item

**Mixed example:**

1. Main task one

• Subtask A
• Subtask B

1. Main task two

• Subtask C
• Subtask D

Need help with tasks, projects, or documentation? I can show lists from those services.""",
    "test_code_block.json": """Python code block example:

```python
def greet_user(name: str) -> str:
    \"\"\"Greet a user with a personalized message.\"\"\"
    return f"Hello, {name}! Welcome to the system."

def calculate_sum(numbers: list[int]) -> int:
    \"\"\"Calculate the sum of a list of integers.\"\"\"
    total = 0
    for num in numbers:
        total += num
    return total

# Example usage
if __name__ == "__main__":
    user_name = "Alice"
    greeting = greet_user(user_name)
    print(greeting)
    
    numbers = [1, 2, 3, 4, 5]
    result = calculate_sum(numbers)
    print(f"The sum is: {result}")
```

*Example usage*

if \\_\\_name\\_\\_ \\=\\= "\\_\\_main\\_\\_":
    user\\_name \\= "Alice"
    greeting \\= greet\\_user\\(user\\_name\\)
    print\\(greeting\\)

numbers \\= \\[1, 2, 3, 4, 5\\]
    result \\= calculate\\_sum\\(numbers\\)
    print\\(f"The sum is: \\{result\\}"\\)
\\`\\`\\`

This shows:

• Function definitions with type hints
• Docstrings
• A main block
• Basic Python syntax

Need a different example or a specific use case?""",
    "test_formatting.json": """Here are examples of bold and italic formatting in markdown:

**Bold text:**

• `**bold**` → **bold**
• `__bold__` → **bold**

*Italic text:*

• `*italic*` → *italic*
• `_italic_` → *italic*

***Bold and italic:***

• `***bold italic***` → ***bold italic***
• `___bold italic___` → ***bold italic***

**Examples:**

• This is **bold**
• This is *italic*
• This is ***bold and italic***

Telegram supports these markdown styles. Use them in your messages.""",
    "test_table.json": """Here's a table with Name, Age, and City:

Name  | Age | City    
------+-----+---------
Alice | 28  | New York
Bob   | 35  | London  
Carol | 42  | Tokyo   
David | 31  | Paris   
Emma  | 29  | Sydney  

Want me to add specific rows or change the columns?""",
    "test_links.json": """Markdown link examples:

**Basic format:**

```[Link text](https://example.com)
```

**Examples:**

• `[Google](https://www.google.com)` → [Google](https://www.google.com)
• `[GitHub](https://github.com)` → [GitHub](https://github.com)
• `[Documentation](https://docs.example.com)` → [Documentation](https://docs.example.com)

**With title (hover text):**

```[Link text](https://example.com "Optional title")
```

**Reference-style links:**

```[Link text][1]

[1]: https://example.com
```

**Inline example:**

```Check out the [official documentation](https://docs.example.com) for more details.
```

Telegram supports this markdown format, so links will be clickable.""",
    "test_inline_code.json": """Here are examples of inline code with backticks:

**Single backticks for inline code:**

• `variable_name`
• `function_name()`
• `import os`
• `const x = 10`

**In sentences:**

• Use the `get_user()` function to fetch user data.
• Set the `DEBUG` environment variable to `true`.
• The `config.json` file contains the settings.

**For code blocks (multiple lines), use triple backticks:**

```def hello():
    print("Hello, world!")
```

**In Telegram/Markdown:**

• Single backticks: `code`
• Triple backticks for blocks:

```  code block
  ```

Want a specific example or help formatting something?""",
    "test_blockquote.json": """Here's a blockquote example:

_This is a blockquote. It's used to highlight quoted text or important information._

n.

You can also nest blockquotes:

_This is the outer quote

> This is a nested quote inside_

inside

And include multiple paragraphs:

_This is the first paragraph of a blockquote.

This is the second paragraph, still part of the same blockquote._

quote.

In markdown, blockquotes are created using the `>` character at the start of each line. For Telegram, the formatting depends on your bot's parse mode (Markdown or HTML).

Need help formatting something specific?""",
    "test_strikethrough.json": """Strikethrough in markdown uses double tildes: `~~text~~`

Here's an example:

\\~\\~This text is struck through\\~\\~

**How it works:**

• `~~text~~` renders as strikethrough
• Works in Telegram when markdown is enabled

**Examples:**

• `~~deleted text~~` → ~~deleted text~~
• `~~old price~~` → ~~old price~~
• `~~completed task~~` → ~~completed task~~

Useful for showing deleted or outdated information, marking completed items, or indicating changes.""",
    "test_mixed.json": None,  # Complex mixed content - will validate it renders without errors
}


@pytest.mark.parametrize("test_file", TEST_FILES)
def test_markdown_translation(test_file):
    """Test that markdown is correctly translated to Telegram format."""
    json_lines = load_test_data(test_file)

    # Get the result message (full accumulated text)
    result_message = extract_result_message(json_lines)
    if not result_message:
        pytest.skip(f"No result message found in {test_file}")

    # Parse markdown and translate
    widgets = parse_markdown(result_message)
    translator = get_translator("telegram")
    rendered = translator.render_message(widgets)

    # Check if we have an expected translation
    expected = EXPECTED_TRANSLATIONS.get(test_file)
    if expected is not None:
        # Normalize for comparison (handle character encoding differences like curly vs straight apostrophes)
        # Also normalize Unicode quotes and apostrophes
        import unicodedata

        def normalize_text(text):
            # Normalize Unicode characters
            text = unicodedata.normalize("NFKD", text)
            # Replace various quote/apostrophe variants with standard ASCII ones
            # U+2019 (right single quotation mark) -> U+0027 (apostrophe)
            # U+2018 (left single quotation mark) -> U+0027 (apostrophe)
            text = text.replace("\u2019", "'").replace("\u2018", "'")
            text = text.replace("\u201C", '"').replace("\u201D", '"')  # Smart quotes
            return text.strip()

        rendered_normalized = normalize_text(rendered)
        expected_normalized = normalize_text(expected)

        assert rendered_normalized == expected_normalized, (
            f"Translation doesn't match expected.\n"
            f"Rendered: {repr(rendered[:200])}\n"
            f"Expected: {repr(expected[:200])}"
        )
    else:
        # Just validate that translation produces valid output
        assert len(rendered) > 0, "Translation produced empty output"
        # Log the output so we can hand-translate it later
        print(f"\n{test_file} translation output:\n{rendered}\n")


def test_chunk_count_and_sizes():
    """Test that we're getting reasonable chunk counts and sizes."""
    for test_file in TEST_FILES:
        json_lines = load_test_data(test_file)
        chunks = extract_assistant_chunks(json_lines)
        result = extract_result_message(json_lines)

        if chunks and result:
            print(f"\n{test_file}:")
            print(f"  Chunks: {len(chunks)}")
            print(f"  Total chunk length: {sum(len(c) for c in chunks)}")
            print(f"  Result length: {len(result)}")
            print(
                f"  Average chunk size: {sum(len(c) for c in chunks) / len(chunks):.1f} chars"
            )
