"""
Platform-specific validators for markdown syntax.

These validators understand the limitations and nuances of each platform's
markdown parser. They can validate that rendered markdown will be accepted
by the platform and can be used to catch regressions.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class PlatformValidator(ABC):
    """Base class for platform-specific markdown validators."""

    @abstractmethod
    def validate(self, markdown: str, lenient: bool = False) -> Tuple[bool, List[str]]:
        """
        Validate markdown syntax for this platform.

        Args:
            markdown: Markdown text to validate
            lenient: If True, skip checks for incomplete markdown (e.g., during streaming)

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        pass

    @abstractmethod
    def get_limitations(self) -> List[str]:
        """Get a list of known limitations for this platform."""
        pass


class TelegramValidator(PlatformValidator):
    """
    Validator for Telegram markdown syntax.

    Telegram supports:
    - *bold* and _italic_
    - `code` and ```code blocks```
    - [text](url) for links

    Known limitations:
    - Unbalanced markdown causes parsing errors
    - Nested formatting is not supported
    - Tables are not supported
    - Headings are not supported (must use bold)
    - Blockquotes are not supported
    """

    def __init__(self) -> None:
        # Patterns for Telegram markdown
        self.bold_pattern = re.compile(r"\*([^*]+)\*")
        self.italic_pattern = re.compile(r"_([^_]+)_")
        self.code_pattern = re.compile(r"`([^`]+)`")
        self.code_block_pattern = re.compile(r"```([^`]*)```", re.DOTALL)
        self.link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

        # Characters that need escaping
        self.special_chars = r"_*[]()~`>#+-=|{}.!"

    def validate(self, markdown: str, lenient: bool = False) -> Tuple[bool, List[str]]:
        """
        Validate Telegram markdown syntax.

        Args:
            markdown: Markdown text to validate
            lenient: If True, skip checks for incomplete markdown (e.g., during streaming)

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        if not lenient:
            # Check for unbalanced bold markers
            bold_count = markdown.count("*")
            if bold_count % 2 != 0:
                errors.append("Unbalanced bold markers (*) - must be even number")

            # Check for unbalanced italic markers (underscores)
            italic_count = markdown.count("_")
            if italic_count % 2 != 0:
                errors.append("Unbalanced italic markers (_) - must be even number")

            # Check for unbalanced code markers
            code_count = markdown.count("`")
            if code_count % 2 != 0:
                errors.append("Unbalanced code markers (`) - must be even number")

            # Check for unbalanced brackets (links)
            open_brackets = markdown.count("[")
            close_brackets = markdown.count("]")
            if open_brackets != close_brackets:
                errors.append("Unbalanced link brackets ([ ]) - must match")

            open_parens = markdown.count("(")
            close_parens = markdown.count(")")
            if open_parens != close_parens:
                errors.append("Unbalanced parentheses ( ) - must match")

        # Check for nested formatting (not supported)
        # Look for bold inside italic or vice versa
        if self._has_nested_formatting(markdown):
            errors.append(
                "Nested formatting detected - Telegram does not support nested bold/italic"
            )

        # Check for unsupported table syntax
        if "|" in markdown and markdown.count("|") > 2:
            # Might be a table - Telegram doesn't support tables
            lines_with_pipes = [line for line in markdown.split("\n") if "|" in line]
            if len(lines_with_pipes) > 1:
                errors.append(
                    "Table syntax detected - Telegram does not support tables"
                )

        # Check for heading syntax (not supported, should use bold)
        if re.search(r"^#{1,6}\s+", markdown, re.MULTILINE):
            errors.append(
                "Heading syntax (#) detected - Telegram does not support headings, use bold instead"
            )

        # Check for blockquote syntax (not supported)
        if re.search(r"^>\s+", markdown, re.MULTILINE):
            errors.append(
                "Blockquote syntax (>) detected - Telegram does not support blockquotes"
            )

        return len(errors) == 0, errors

    def _has_nested_formatting(self, text: str) -> bool:
        """Check if text has nested formatting (e.g., bold inside italic)."""
        # Look for patterns like *_text_* or _*text*_
        if re.search(r"\*_[^*_]+_\*", text) or re.search(r"_\*[^*_]+\*_", text):
            return True
        return False

    def get_limitations(self) -> List[str]:
        """Get list of known Telegram markdown limitations."""
        return [
            "Unbalanced markdown causes parsing errors",
            "Nested formatting (bold inside italic) is not supported",
            "Tables are not supported",
            "Headings (#) are not supported - use bold instead",
            "Blockquotes (>) are not supported",
            "Code blocks must have balanced ``` markers",
            "Links must have balanced [text](url) format",
        ]


class TelegramHTMLValidator(PlatformValidator):
    """
    Validator for Telegram HTML syntax.

    Telegram HTML supports:
    - <b>bold</b> or <strong>bold</strong>
    - <i>italic</i> or <em>italic</em>
    - <u>underline</u>
    - <s>strikethrough</s> or <strike>strikethrough</strike> or <del>strikethrough</del>
    - <code>inline code</code>
    - <pre>code block</pre>
    - <pre><code class="language">code block</code></pre>
    - <a href="URL">link text</a>

    Known limitations:
    - All tags must be properly closed
    - Unescaped & characters may cause issues (use &amp;, &lt;, &gt;)
    - Unclosed tags will cause parsing errors
    - Nested tags must be properly ordered (e.g., <b><i>text</i></b> not <b><i>text</b></i>)
    """

    def __init__(self) -> None:
        # Allowed HTML tags for Telegram
        self.allowed_tags = {
            "b",
            "strong",
            "i",
            "em",
            "u",
            "s",
            "strike",
            "del",
            "code",
            "pre",
            "a",
        }
        # Self-closing tags (Telegram doesn't use these, but check for completeness)
        self.self_closing_tags = set()

    def validate(self, html: str, lenient: bool = False) -> Tuple[bool, List[str]]:
        """
        Validate Telegram HTML syntax.

        Args:
            html: HTML text to validate
            lenient: If True, skip checks for incomplete HTML (e.g., during streaming)

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        if not lenient:
            # Check for unclosed tags
            tag_errors = self._check_tag_balance(html)
            errors.extend(tag_errors)

            # Check for unescaped special characters
            unescaped = self._check_unescaped_chars(html)
            errors.extend(unescaped)

            # Check for invalid tags
            invalid_tags = self._check_invalid_tags(html)
            errors.extend(invalid_tags)

            # Check for improperly nested tags
            nesting_errors = self._check_tag_nesting(html)
            errors.extend(nesting_errors)

        return len(errors) == 0, errors

    def _check_tag_balance(self, html: str) -> List[str]:
        """Check that all HTML tags are properly closed."""
        errors: List[str] = []
        # Find all tags
        tag_pattern = re.compile(r"<([^>]+)>")
        tags = tag_pattern.findall(html)

        open_tags: List[str] = []
        for tag_content in tags:
            # Skip self-closing tags and comments
            if tag_content.startswith("!") or tag_content.endswith("/"):
                continue

            # Check if it's a closing tag
            if tag_content.startswith("/"):
                tag_name = tag_content[1:].split()[0].lower()
                if not open_tags or open_tags[-1] != tag_name:
                    errors.append(
                        f"Unmatched closing tag: </{tag_name}> (expected: </{open_tags[-1] if open_tags else 'none'}>)"
                    )
                else:
                    open_tags.pop()
            else:
                # Opening tag
                tag_name = tag_content.split()[0].lower()
                if tag_name in self.allowed_tags:
                    open_tags.append(tag_name)

        # Check for unclosed tags
        if open_tags:
            errors.append(
                f"Unclosed tags: {', '.join(f'<{tag}>' for tag in open_tags)}"
            )

        return errors

    def _check_unescaped_chars(self, html: str) -> List[str]:
        """Check for unescaped special characters that should be escaped."""
        errors: List[str] = []

        # Check for unescaped & characters (should be &amp; unless part of entity)
        # Simple check: & not followed by # or letters (entity pattern)
        unescaped_amp = re.findall(r"&(?![#a-zA-Z])", html)
        if unescaped_amp:
            # More sophisticated: check if inside tag attributes (allowed) or in text
            # For now, just warn about potential issues
            # This is lenient because & might be in URLs or attributes
            pass

        # Check for unescaped < and > outside of tags
        # This is complex - for now, we rely on tag balance checking
        return errors

    def _check_invalid_tags(self, html: str) -> List[str]:
        """Check for tags that are not allowed in Telegram HTML."""
        errors: List[str] = []
        tag_pattern = re.compile(r"<([^/>]+)>")
        tags = tag_pattern.findall(html)

        for tag_content in tags:
            # Skip comments and self-closing
            if tag_content.startswith("!") or tag_content.endswith("/"):
                continue

            # Get tag name
            tag_name = tag_content.split()[0].lower()
            # Remove / if it's a closing tag
            if tag_name.startswith("/"):
                tag_name = tag_name[1:]

            # Check if tag is allowed
            if tag_name and tag_name not in self.allowed_tags:
                errors.append(
                    f"Invalid tag: <{tag_name}> (not supported by Telegram HTML)"
                )

        return errors

    def _check_tag_nesting(self, html: str) -> List[str]:
        """Check that tags are properly nested (e.g., <b><i>text</i></b> not <b><i>text</b></i>)."""
        errors: List[str] = []
        # This is already checked by _check_tag_balance, but we can add more specific checks
        # For now, tag balance checking is sufficient
        return errors

    def get_limitations(self) -> List[str]:
        """Get list of known Telegram HTML limitations."""
        return [
            "All tags must be properly closed",
            "Unescaped & characters may cause issues (use &amp;, &lt;, &gt;)",
            "Unclosed tags will cause parsing errors",
            "Nested tags must be properly ordered",
            "Only specific tags are supported: b, strong, i, em, u, s, strike, del, code, pre, a",
        ]


class DiscordValidator(PlatformValidator):
    """
    Validator for Discord markdown syntax.

    Discord supports:
    - **bold** and *italic*
    - `code` and ```code blocks```
    - [text](url) for links
    - > blockquotes

    Known limitations:
    - Unbalanced markdown causes parsing errors
    - Tables are not supported (must use code blocks)
    - Headings are not supported (must use bold)
    """

    def __init__(self):
        # Patterns for Discord markdown
        self.bold_pattern = re.compile(r"\*\*([^*]+)\*\*")
        self.italic_pattern = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
        self.code_pattern = re.compile(r"`([^`]+)`")
        self.code_block_pattern = re.compile(r"```([^`]*)```", re.DOTALL)
        self.link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        self.blockquote_pattern = re.compile(r"^>\s+", re.MULTILINE)

    def validate(self, markdown: str, lenient: bool = False) -> Tuple[bool, List[str]]:
        """
        Validate Discord markdown syntax.

        Args:
            markdown: Markdown text to validate
            lenient: If True, skip checks for incomplete markdown (e.g., during streaming)

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        if not lenient:
            # Check for unbalanced bold markers (must be **)
            # Count ** pairs
            bold_pairs = len(re.findall(r"\*\*", markdown))
            if bold_pairs % 2 != 0:
                errors.append("Unbalanced bold markers (**) - must be even number")

            # Check for unbalanced italic markers (single *)
            # Need to exclude ** from single * count
            text_without_bold = re.sub(r"\*\*", "", markdown)
            italic_count = text_without_bold.count("*")
            if italic_count % 2 != 0:
                errors.append("Unbalanced italic markers (*) - must be even number")

            # Check for unbalanced code markers
            code_count = markdown.count("`")
            if code_count % 2 != 0:
                errors.append("Unbalanced code markers (`) - must be even number")

            # Check for unbalanced brackets (links)
            open_brackets = markdown.count("[")
            close_brackets = markdown.count("]")
            if open_brackets != close_brackets:
                errors.append("Unbalanced link brackets ([ ]) - must match")

            open_parens = markdown.count("(")
            close_parens = markdown.count(")")
            if open_parens != close_parens:
                errors.append("Unbalanced parentheses ( ) - must match")

        # Check for unsupported table syntax
        if "|" in markdown and markdown.count("|") > 2:
            lines_with_pipes = [line for line in markdown.split("\n") if "|" in line]
            if len(lines_with_pipes) > 1:
                # Check if it's in a code block (allowed) or plain text (not supported)
                if not self._is_in_code_block(markdown, markdown.find("|")):
                    errors.append(
                        "Table syntax detected - Discord does not support tables outside code blocks"
                    )

        # Check for heading syntax (not supported, should use bold)
        if re.search(r"^#{1,6}\s+", markdown, re.MULTILINE):
            errors.append(
                "Heading syntax (#) detected - Discord does not support headings, use bold instead"
            )

        return len(errors) == 0, errors

    def _is_in_code_block(self, text: str, position: int) -> bool:
        """Check if a position in text is inside a code block."""
        before = text[:position]
        code_block_starts = len(re.findall(r"```", before))
        return code_block_starts % 2 == 1

    def get_limitations(self) -> List[str]:
        """Get list of known Discord markdown limitations."""
        return [
            "Unbalanced markdown causes parsing errors",
            "Tables are not supported (use code blocks for table-like content)",
            "Headings (#) are not supported - use bold instead",
            "Code blocks must have balanced ``` markers",
            "Links must have balanced [text](url) format",
        ]


def get_validator(platform: str, parse_mode: Optional[str] = None) -> PlatformValidator:
    """
    Get the appropriate validator for a platform.

    Args:
        platform: Platform name ('telegram', 'discord', etc.)
        parse_mode: Parse mode for Telegram ('HTML' or 'Markdown') (optional)

    Returns:
        PlatformValidator instance
    """
    platform_lower = platform.lower()

    if platform_lower == "telegram":
        if parse_mode and parse_mode.upper() == "HTML":
            return TelegramHTMLValidator()
        else:
            return TelegramValidator()
    elif platform_lower == "discord":
        return DiscordValidator()
    else:
        logger.warning(
            f"Unknown platform '{platform}', using Telegram validator as fallback"
        )
        return TelegramValidator()
