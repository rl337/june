# Message Format Requirements and Limitations

This document describes the message format requirements, limitations, and best practices for Telegram and Discord platforms. Use this guide when debugging rendering issues or implementing new message formatting features.

## Overview

Both Telegram and Discord have specific requirements and limitations for message formatting. Understanding these is critical for:
- Debugging rendering issues
- Preventing message truncation
- Ensuring proper markdown parsing
- Avoiding API errors

## Telegram Message Requirements

### Length Limits

- **Maximum message length:** 4096 characters
- **Recommended limit:** ~3600 characters (90% of max) to leave room for formatting
- **Automatic handling:** Messages exceeding 4096 characters are automatically split or truncated

### Supported Markdown Syntax

Telegram supports a limited subset of Markdown:

#### Supported Formatting

- **Bold:** `*bold text*` or `**bold text**`
- **Italic:** `_italic text_`
- **Code (inline):** `` `code` ``
- **Code blocks:** ` ```code block``` ``
- **Links:** `[text](url)`

#### Unsupported Features

- ❌ **Nested formatting:** Cannot nest bold inside italic or vice versa (e.g., `*_text_*` or `_*text*_`)
- ❌ **Tables:** Table syntax (`| col1 | col2 |`) is not supported
- ❌ **Headings:** Heading syntax (`# Heading`) is not supported - use bold instead
- ❌ **Blockquotes:** Blockquote syntax (`> quote`) is not supported
- ❌ **Strikethrough:** Not supported in standard markdown mode
- ❌ **Underline:** Not supported

### Validation Rules

1. **Balanced markers:** All markdown markers must be balanced:
   - Bold markers (`*`) must be even number
   - Italic markers (`_`) must be even number
   - Code markers (`` ` ``) must be even number
   - Link brackets (`[` and `]`) must match
   - Link parentheses (`(` and `)`) must match

2. **No nested formatting:** Bold and italic cannot be nested

3. **Special characters:** The following characters may need escaping in certain contexts:
   - `_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!`

### HTML Mode

Telegram also supports HTML mode with different syntax:

- **Bold:** `<b>text</b>` or `<strong>text</strong>`
- **Italic:** `<i>text</i>` or `<em>text</em>`
- **Code:** `<code>text</code>`
- **Pre-formatted:** `<pre>text</pre>`
- **Links:** `<a href="url">text</a>`

**Important:** When using HTML mode:
- All tags must be properly closed
- Unescaped `&` characters may cause issues (use `&amp;`, `&lt;`, `&gt;`)
- Unclosed tags will cause parsing errors

### Message Splitting

When a message exceeds 4096 characters:

1. **If message is ≤ 8192 characters (2x limit):**
   - Message is split into 2 parts at widget boundaries (if possible)
   - Split point is chosen to avoid breaking formatting

2. **If message is > 8192 characters:**
   - Message is truncated to 2 parts
   - First part: up to 4096 characters
   - Second part: continuation with truncation indicator
   - Original message is preserved in `raw_text` for debugging

### Rendering Metadata

Each message includes rendering metadata:

```python
{
    "message_length": 1234,
    "telegram_max_length": 4096,
    "within_limit": True,
    "was_truncated": False,
    "is_split": False,
    "total_parts": 1,
    "part_number": 1,
    "parse_mode": "Markdown",
    "split_info": {...}
}
```

## Discord Message Requirements

### Length Limits

- **Maximum message length:** 2000 characters
- **Recommended limit:** ~1800 characters (90% of max) to leave room for formatting
- **Automatic handling:** Messages exceeding 2000 characters are automatically split or truncated

### Supported Markdown Syntax

Discord supports a more extensive subset of Markdown:

#### Supported Formatting

- **Bold:** `**bold text**`
- **Italic:** `*italic text*` (single asterisk, not double)
- **Bold Italic:** `***bold italic***`
- **Code (inline):** `` `code` ``
- **Code blocks:** ` ```code block``` ``
- **Links:** `[text](url)`
- **Blockquotes:** `> quote text`
- **Multi-line blockquotes:** `>>> quote text`

#### Unsupported Features

- ❌ **Tables:** Table syntax (`| col1 | col2 |`) is not supported outside code blocks
- ❌ **Headings:** Heading syntax (`# Heading`) is not supported - use bold instead
- ❌ **Strikethrough:** Not supported in standard markdown mode
- ❌ **Underline:** Not supported

### Validation Rules

1. **Balanced markers:** All markdown markers must be balanced:
   - Bold markers (`**`) must be even number of pairs
   - Italic markers (`*`) must be even number (excluding `**` pairs)
   - Code markers (`` ` ``) must be even number
   - Link brackets (`[` and `]`) must match
   - Link parentheses (`(` and `)`) must match

2. **Bold syntax:** Discord uses `**` for bold (not single `*` like Telegram)
   - Single `*` is for italic
   - `**` is for bold
   - `***` is for bold italic

3. **Code blocks:** Tables can be placed inside code blocks (```) but not in plain text

### Message Splitting

When a message exceeds 2000 characters:

1. **If message is ≤ 4000 characters (2x limit):**
   - Message is split into 2 parts at widget boundaries (if possible)
   - Split point is chosen to avoid breaking formatting

2. **If message is > 4000 characters:**
   - Message is truncated to 2 parts
   - First part: up to 2000 characters
   - Second part: continuation with truncation indicator
   - Original message is preserved in `raw_text` for debugging

### Rendering Metadata

Each message includes rendering metadata:

```python
{
    "message_length": 1234,
    "discord_max_length": 2000,
    "within_limit": True,
    "was_truncated": False,
    "is_split": False,
    "total_parts": 1,
    "part_number": 1,
    "format": "markdown",
    "split_info": {...}
}
```

## Common Issues and Solutions

### Issue: Unbalanced Markdown

**Symptoms:**
- Message appears with visible markdown markers (e.g., `*text*` instead of **text**)
- Telegram/Discord API errors about invalid markdown

**Solution:**
- Use `validate_message_for_platform()` to check messages before sending
- Ensure all markdown markers are balanced
- Use the platform validators (`TelegramValidator`, `DiscordValidator`) to catch issues

### Issue: Message Truncation

**Symptoms:**
- Long messages are cut off
- Truncation indicator (`...`) appears unexpectedly

**Solution:**
- Check message length before sending: `len(message) <= max_length`
- Use `get_message_history()` to inspect what was actually sent
- Use `compare_expected_vs_actual()` to compare expected vs actual output
- Consider splitting very long messages proactively

### Issue: Formatting Not Applied

**Symptoms:**
- Markdown syntax appears as plain text
- Formatting works in one platform but not the other

**Solution:**
- Verify platform-specific syntax (Telegram uses `*bold*`, Discord uses `**bold**`)
- Check for nested formatting (not supported in Telegram)
- Use platform validators to ensure syntax is correct
- Check `rendering_metadata` in message history to see what was sent

### Issue: Nested Formatting Errors

**Symptoms:**
- Telegram errors about invalid markdown
- Formatting breaks unexpectedly

**Solution:**
- Avoid nested formatting (e.g., `*_text_*` or `_*text*_`)
- Use `TelegramValidator._has_nested_formatting()` to detect issues
- Simplify formatting to avoid nesting

## Debugging Tools

### Message History Analysis

Use `get_message_history()` command to inspect messages:

```bash
# Get recent messages
poetry run python -m essence get-message-history --user-id <id> --limit 10

# Analyze rendering issues
poetry run python -m essence get-message-history --analyze --platform telegram

# Compare expected vs actual
poetry run python -m essence get-message-history --compare "expected text" --platform telegram

# Validate message text
poetry run python -m essence get-message-history --validate "message text" --platform telegram
```

### Programmatic Access

Use `essence.chat.message_history_analysis` module:

```python
from essence.chat.message_history_analysis import (
    analyze_rendering_issues,
    compare_expected_vs_actual,
    validate_message_for_platform,
    get_message_statistics
)

# Analyze rendering issues
issues = analyze_rendering_issues(platform="telegram", hours=24)

# Validate message
result = validate_message_for_platform(
    text="*bold text*",
    platform="telegram",
    parse_mode="Markdown"
)

# Compare expected vs actual
comparison = compare_expected_vs_actual(
    expected_text="expected message",
    platform="telegram",
    hours=1
)
```

### Platform Validators

Use platform validators to check markdown syntax:

```python
from essence.chat.platform_validators import get_validator

validator = get_validator("telegram")
is_valid, errors = validator.validate("*bold text*")

if not is_valid:
    print(f"Errors: {errors}")

# Get limitations
limitations = validator.get_limitations()
```

## Best Practices

1. **Always validate before sending:**
   - Use `validate_message_for_platform()` to check messages
   - Use platform validators for markdown syntax validation

2. **Monitor message length:**
   - Check length before sending: `len(message) <= max_length`
   - Use 90% of max length as a safe limit (3600 for Telegram, 1800 for Discord)

3. **Handle splitting proactively:**
   - For very long messages, split them before sending
   - Use `MessageBuilder.split_message_if_needed()` for automatic splitting

4. **Use platform-specific syntax:**
   - Telegram: `*bold*` and `_italic_`
   - Discord: `**bold**` and `*italic*`

5. **Avoid unsupported features:**
   - Don't use tables, headings, or blockquotes in Telegram
   - Don't use nested formatting in Telegram
   - Place tables in code blocks for Discord

6. **Debug with message history:**
   - Use `get_message_history()` to inspect what was actually sent
   - Compare expected vs actual output using analysis tools
   - Check `rendering_metadata` for split/truncation information

7. **Test both platforms:**
   - Test messages on both Telegram and Discord
   - Use platform validators to catch platform-specific issues
   - Verify rendering metadata is correct for each platform

## Using the Debugging Tools

The message history debugging tools provide programmatic access to inspect what messages were actually sent and identify rendering issues. This section provides practical examples for using these tools.

### Command-Line Usage

The `get-message-history` command provides a CLI interface for debugging:

#### Basic Message Retrieval

```bash
# Get recent messages (last 24 hours, default limit: 50)
poetry run python -m essence get-message-history

# Get messages for a specific user
poetry run python -m essence get-message-history --user-id "123456789"

# Get messages for a specific chat/channel
poetry run python -m essence get-message-history --chat-id "-1001234567890"

# Filter by platform
poetry run python -m essence get-message-history --platform telegram

# Filter by message type
poetry run python -m essence get-message-history --message-type text

# Limit number of results
poetry run python -m essence get-message-history --limit 10

# Output as JSON for programmatic processing
poetry run python -m essence get-message-history --format json
```

#### Analyzing Rendering Issues

```bash
# Analyze all messages for rendering issues (last 24 hours)
poetry run python -m essence get-message-history --analyze

# Analyze messages for a specific platform
poetry run python -m essence get-message-history --analyze --platform telegram

# Analyze messages for a specific user
poetry run python -m essence get-message-history --analyze --user-id "123456789"

# Analyze messages from last hour
poetry run python -m essence get-message-history --analyze --hours 1

# Output analysis as JSON
poetry run python -m essence get-message-history --analyze --format json
```

#### Comparing Expected vs Actual

```bash
# Compare expected text with what was actually sent
poetry run python -m essence get-message-history --compare "Expected message text here"

# Compare with platform filter
poetry run python -m essence get-message-history --compare "Expected text" --platform telegram

# Compare for specific user/chat
poetry run python -m essence get-message-history --compare "Expected text" --user-id "123456789" --chat-id "-1001234567890"

# Look back further in time (default: 1 hour)
poetry run python -m essence get-message-history --compare "Expected text" --hours 24
```

#### Validating Messages

```bash
# Validate a message for Telegram
poetry run python -m essence get-message-history --validate "Message text" --platform telegram

# Validate a message for Discord
poetry run python -m essence get-message-history --validate "Message text" --platform discord

# Output validation as JSON
poetry run python -m essence get-message-history --validate "Message text" --platform telegram --format json
```

#### Getting Statistics

```bash
# Get message history statistics
poetry run python -m essence get-message-history --stats

# Get statistics as JSON
poetry run python -m essence get-message-history --stats --format json
```

### Programmatic Usage

For programmatic access, use the `essence.chat.message_history_analysis` module:

```python
from essence.chat.message_history_analysis import (
    get_recent_messages,
    analyze_rendering_issues,
    compare_expected_vs_actual,
    get_message_statistics,
    validate_message_for_platform,
)

# Get recent messages
messages = get_recent_messages(
    user_id="123456789",
    platform="telegram",
    hours=1,
    limit=10
)

# Analyze rendering issues
issues = analyze_rendering_issues(
    user_id="123456789",
    platform="telegram",
    hours=24
)
print(f"Found {issues['total_messages']} messages")
print(f"Split messages: {issues['split_messages']}")
print(f"Truncated messages: {issues['truncated_messages']}")

# Compare expected vs actual
comparison = compare_expected_vs_actual(
    expected_text="Expected message text",
    user_id="123456789",
    platform="telegram",
    hours=1
)
if comparison:
    print(f"Similarity: {comparison['similarity']:.2%}")
    print(f"Differences: {len(comparison['differences'])}")

# Validate a message
validation = validate_message_for_platform(
    "Message text to validate",
    platform="telegram",
    parse_mode="Markdown"
)
if not validation['valid']:
    print(f"Errors: {validation['errors']}")
    print(f"Warnings: {validation['warnings']}")

# Get statistics
stats = get_message_statistics()
print(f"Total messages: {stats['total_messages']}")
print(f"By platform: {stats['by_platform']}")
```

### Common Debugging Workflows

#### Workflow 1: Debug a Specific Message

1. **Get the message from history:**
   ```bash
   poetry run python -m essence get-message-history --user-id "123456789" --limit 5
   ```

2. **Compare expected vs actual:**
   ```bash
   poetry run python -m essence get-message-history --compare "Expected message text" --user-id "123456789"
   ```

3. **Check rendering metadata:**
   - Look for `rendering_metadata` in the output
   - Check for `was_truncated`, `is_split`, `total_parts`

#### Workflow 2: Find All Rendering Issues

1. **Analyze all messages:**
   ```bash
   poetry run python -m essence get-message-history --analyze --hours 24
   ```

2. **Review issues:**
   - Check `split_messages` count
   - Check `truncated_messages` count
   - Review individual issues in the output

3. **Investigate specific issues:**
   ```bash
   poetry run python -m essence get-message-history --user-id "123456789" --analyze
   ```

#### Workflow 3: Validate Before Sending

1. **Test message validation:**
   ```bash
   poetry run python -m essence get-message-history --validate "Your message text" --platform telegram
   ```

2. **Fix any errors or warnings:**
   - Address length issues
   - Fix markdown syntax errors
   - Remove unsupported features

3. **Re-validate:**
   ```bash
   poetry run python -m essence get-message-history --validate "Fixed message text" --platform telegram
   ```

### Interpreting Results

#### Analysis Results

- **`total_messages`**: Total number of messages in the time window
- **`split_messages`**: Messages that were split into multiple parts
- **`truncated_messages`**: Messages that were truncated
- **`format_mismatches`**: Messages with formatting issues
- **`exceeded_limit`**: Messages that exceeded platform limits
- **`issues`**: List of specific issues found

#### Comparison Results

- **`similarity`**: Similarity score (0.0 to 1.0) between expected and actual
- **`expected_length`**: Length of expected text
- **`actual_length`**: Length of actual sent message
- **`raw_length`**: Length of raw text (before formatting)
- **`differences`**: List of differences found (truncation, splits, etc.)

#### Validation Results

- **`valid`**: Whether the message is valid for the platform
- **`length`**: Current message length
- **`max_length`**: Maximum allowed length for platform
- **`within_length_limit`**: Whether message is within length limit
- **`errors`**: List of validation errors
- **`warnings`**: List of validation warnings

## Reference

### Constants

- `TELEGRAM_MAX_MESSAGE_LENGTH = 4096`
- `DISCORD_MAX_MESSAGE_LENGTH = 2000` (implicit, used in code)

### Key Files

- `essence/chat/platform_validators.py` - Platform-specific validators
- `essence/chat/message_history_analysis.py` - Analysis and validation tools
- `essence/chat/message_builder.py` - Message building and splitting logic
- `essence/services/telegram/message_history_helpers.py` - Telegram message helpers
- `essence/services/discord/message_history_helpers.py` - Discord message helpers

### Related Commands

- `get-message-history` - Inspect message history and analyze rendering issues
- `verify-tensorrt-llm` - Verify LLM service (for debugging LLM response formatting)
