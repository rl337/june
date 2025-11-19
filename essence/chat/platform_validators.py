"""
Platform-specific validators for markdown syntax.

These validators understand the limitations and nuances of each platform's
markdown parser. They can validate that rendered markdown will be accepted
by the platform and can be used to catch regressions.
"""

import re
import logging
from typing import List, Tuple, Optional
from abc import ABC, abstractmethod

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

    def __init__(self):
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


def get_validator(platform: str) -> PlatformValidator:
    """
    Get the appropriate validator for a platform.

    Args:
        platform: Platform name ('telegram', 'discord', etc.)

    Returns:
        PlatformValidator instance
    """
    platform_lower = platform.lower()

    if platform_lower == "telegram":
        return TelegramValidator()
    elif platform_lower == "discord":
        return DiscordValidator()
    else:
        logger.warning(
            f"Unknown platform '{platform}', using Telegram validator as fallback"
        )
        return TelegramValidator()
