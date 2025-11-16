# Chat Service Base Agent Tests

## Overview

This test suite provides comprehensive data-driven testing for:
1. **Chunk Appending**: Validates that assistant message chunks are correctly accumulated to match the final result message
2. **Markdown Translation**: Validates that markdown from the LLM is correctly translated to platform-specific formats (Telegram, Discord)

## Test Data

Test data is captured from real `cursor-agent` interactions and stored in `test_data/`:

- `test_headers.json` - Headers (h1-h6)
- `test_lists.json` - Bullet and numbered lists
- `test_code_block.json` - Code blocks with syntax highlighting
- `test_formatting.json` - Bold, italic, bold+italic formatting
- `test_table.json` - Tables
- `test_links.json` - Links [text](url)
- `test_inline_code.json` - Inline code with backticks
- `test_blockquote.json` - Blockquotes (>)
- `test_strikethrough.json` - Strikethrough (~~)
- `test_mixed.json` - Mixed markdown (all types together)

## Test Coverage

### Chunk Appending Tests
- Validates that assistant message chunks are correctly appended
- Detects when a chunk contains the full accumulated message (replaces instead of appends)
- Ensures appended chunks match the final result message

### Markdown Translation Tests
- Validates translation for all markdown types
- Ensures unsupported features (e.g., blockquotes, strikethrough) are handled gracefully
- Verifies that platform-specific limitations are respected

## Running Tests

```bash
# Run all tests
pytest services/chat-service-base/agent/tests/test_chunk_appending.py -v

# Run specific test
pytest services/chat-service-base/agent/tests/test_chunk_appending.py::test_chunk_appending_matches_result -v

# Run with coverage
pytest services/chat-service-base/agent/tests/test_chunk_appending.py --cov=essence.chat --cov-report=html
```

## Adding New Test Cases

1. Generate test data by running `cursor-agent` with a specific query:
   ```bash
   cd /home/rlee/dev/agenticness
   export CURSOR_AGENT_EXE="${CURSOR_AGENT_EXE:-/home/rlee/.local/share/cursor-agent/versions/2025.11.06-8fe8a63/cursor-agent}"
   export AGENTICNESS_STATE_DIR="${AGENTICNESS_STATE_DIR:-/home/rlee/june_data/agenticness-state}"
   export AGENT_MODE="telegram-response"
   export TELEGRAM_USER_ID="testN"
   export TELEGRAM_CHAT_ID="testN"
   bash scripts/telegram_response_agent.sh testN testN "Your query here" 2>&1 | \
     grep -v "^\[" | grep -v "SUCCESS\|Using\|Running\|Executing\|Command\|Created" > \
     /home/rlee/dev/june/services/chat-service-base/agent/tests/test_data/test_new.json
   ```

2. Add the test file to `TEST_FILES` in `test_chunk_appending.py`

3. Capture the expected translation:
   ```python
   from essence.chat.markdown_parser import parse_markdown
   from essence.chat.platform_translators import get_translator
   
   # Load result from JSON
   result = extract_result_message(json_lines)
   widgets = parse_markdown(result)
   translator = get_translator("telegram")
   rendered = translator.render_message(widgets)
   ```

4. Add the expected translation to `EXPECTED_TRANSLATIONS` in `test_chunk_appending.py`

## Current Limitations

- **Strikethrough**: Not currently parsed as a separate widget type; treated as escaped text (Telegram doesn't support strikethrough natively)
- **Blockquotes**: Converted to italic for Telegram (not natively supported)
- **Mixed Content**: Complex mixed markdown tests validate rendering without errors but don't have strict expected output

## Future Enhancements

- Add strikethrough widget type for better handling
- Add metadata to Turn/Message for rendering hints (e.g., "unsupported_feature_used")
- Add tests for edge cases (nested formatting, malformed markdown, etc.)
- Add Discord-specific translation tests

