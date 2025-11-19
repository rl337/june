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
poetry run -m essence get-message-history --user-id <id> --limit 10

# Analyze rendering issues
poetry run -m essence get-message-history --analyze --platform telegram

# Compare expected vs actual
poetry run -m essence get-message-history --compare "expected text" --platform telegram

# Validate message text
poetry run -m essence get-message-history --validate "message text" --platform telegram
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
