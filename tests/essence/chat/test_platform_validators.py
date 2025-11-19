"""
Data-driven tests for platform validators.

These tests capture known edge cases and regressions for each platform's
markdown parsing limitations.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from essence.chat.platform_validators import (
    DiscordValidator,
    TelegramHTMLValidator,
    TelegramValidator,
    get_validator,
)


class TestTelegramValidator:
    """Tests for Telegram markdown validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = TelegramValidator()

    @pytest.mark.parametrize(
        "markdown,should_be_valid,expected_errors",
        [
            # Valid cases
            ("Hello world", True, []),
            ("*bold* text", True, []),
            ("_italic_ text", True, []),
            ("`code` text", True, []),
            ("```code block```", True, []),
            ("[link](https://example.com)", True, []),
            # Unbalanced markdown
            ("*unbalanced bold", False, ["Unbalanced bold markers"]),
            ("_unbalanced italic", False, ["Unbalanced italic markers"]),
            ("`unbalanced code", False, ["Unbalanced code markers"]),
            ("[unbalanced link", False, ["Unbalanced link brackets"]),
            ("(unbalanced parens", False, ["Unbalanced parentheses"]),
            # Nested formatting (not supported)
            ("*_nested_*", False, ["Nested formatting"]),
            ("_*nested*_", False, ["Nested formatting"]),
            # Unsupported features
            ("# Heading", False, ["Heading syntax"]),
            ("> Blockquote", False, ["Blockquote syntax"]),
            ("| Table |\n| --- |\n| Cell |", False, ["Table syntax"]),
            # Code snippet edge cases (known issues)
            (
                "```python\ncode with *asterisk*\n```",
                True,
                [],
            ),  # Code blocks should escape content
            ("Text with `code *with* asterisk`", True, []),  # Inline code should escape
            ("Text with **bold** and `code`", True, []),  # Mixed formatting
            # Real-world problematic cases
            ("*Bold text with *nested* issue", False, ["Unbalanced bold markers"]),
            ("Text with _italic_ and *bold*", True, []),  # Should be valid
            ("Text with `code` and *bold*", True, []),  # Should be valid
        ],
    )
    def test_validation(self, markdown, should_be_valid, expected_errors):
        """Test markdown validation with various edge cases."""
        is_valid, errors = self.validator.validate(markdown)

        assert (
            is_valid == should_be_valid
        ), f"Validation failed for: {markdown}\nErrors: {errors}"

        if expected_errors:
            # Check that at least one expected error is present
            error_text = " ".join(errors).lower()
            found_expected = any(
                expected.lower() in error_text for expected in expected_errors
            )
            assert (
                found_expected
            ), f"Expected one of {expected_errors} in errors: {errors}"

    def test_limitations(self):
        """Test that limitations are documented."""
        limitations = self.validator.get_limitations()
        assert len(limitations) > 0
        assert isinstance(limitations, list)


class TestDiscordValidator:
    """Tests for Discord markdown validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = DiscordValidator()

    @pytest.mark.parametrize(
        "markdown,should_be_valid,expected_errors",
        [
            # Valid cases
            ("Hello world", True, []),
            ("**bold** text", True, []),
            ("*italic* text", True, []),
            ("`code` text", True, []),
            ("```code block```", True, []),
            ("[link](https://example.com)", True, []),
            ("> Blockquote", True, []),  # Discord supports blockquotes
            # Unbalanced markdown
            ("**unbalanced bold", False, ["Unbalanced bold markers"]),
            ("*unbalanced italic", False, ["Unbalanced italic markers"]),
            ("`unbalanced code", False, ["Unbalanced code markers"]),
            ("[unbalanced link", False, ["Unbalanced link brackets"]),
            ("(unbalanced parens", False, ["Unbalanced parentheses"]),
            # Unsupported features
            ("# Heading", False, ["Heading syntax"]),
            (
                "| Table |\n| --- |\n| Cell |",
                False,
                ["Table syntax"],
            ),  # Outside code block
            (
                "```\n| Table |\n| --- |\n| Cell |\n```",
                True,
                [],
            ),  # Inside code block is OK
            # Code snippet edge cases
            (
                "```python\ncode with **bold**\n```",
                True,
                [],
            ),  # Code blocks should escape content
            ("Text with `code *with* asterisk`", True, []),  # Inline code should escape
            ("Text with **bold** and `code`", True, []),  # Mixed formatting
            # Real-world problematic cases
            ("**Bold text with **nested** issue", False, ["Unbalanced bold markers"]),
            ("Text with *italic* and **bold**", True, []),  # Should be valid
            ("Text with `code` and **bold**", True, []),  # Should be valid
        ],
    )
    def test_validation(self, markdown, should_be_valid, expected_errors):
        """Test markdown validation with various edge cases."""
        is_valid, errors = self.validator.validate(markdown)

        assert (
            is_valid == should_be_valid
        ), f"Validation failed for: {markdown}\nErrors: {errors}"

        if expected_errors:
            # Check that at least one expected error is present
            error_text = " ".join(errors).lower()
            found_expected = any(
                expected.lower() in error_text for expected in expected_errors
            )
            assert (
                found_expected
            ), f"Expected one of {expected_errors} in errors: {errors}"

    def test_limitations(self):
        """Test that limitations are documented."""
        limitations = self.validator.get_limitations()
        assert len(limitations) > 0
        assert isinstance(limitations, list)


class TestPlatformValidatorFactory:
    """Tests for the validator factory function."""

    def test_get_telegram_validator(self):
        """Test getting Telegram validator."""
        validator = get_validator("telegram")
        assert isinstance(validator, TelegramValidator)

    def test_get_discord_validator(self):
        """Test getting Discord validator."""
        validator = get_validator("discord")
        assert isinstance(validator, DiscordValidator)

    def test_get_unknown_validator_fallback(self):
        """Test that unknown platform falls back to Telegram."""
        validator = get_validator("unknown")
        assert isinstance(validator, TelegramValidator)

    def test_get_telegram_html_validator(self):
        """Test getting Telegram HTML validator."""
        validator = get_validator("telegram", parse_mode="HTML")
        assert isinstance(validator, TelegramHTMLValidator)

    def test_get_telegram_markdown_validator_default(self):
        """Test that Telegram defaults to Markdown validator."""
        validator = get_validator("telegram")
        assert isinstance(validator, TelegramValidator)
        validator = get_validator("telegram", parse_mode="Markdown")
        assert isinstance(validator, TelegramValidator)


class TestTelegramHTMLValidator:
    """Tests for Telegram HTML validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = TelegramHTMLValidator()

    @pytest.mark.parametrize(
        "html,should_be_valid,expected_errors",
        [
            # Valid cases
            ("Hello world", True, []),
            ("<b>bold</b> text", True, []),
            ("<strong>bold</strong> text", True, []),
            ("<i>italic</i> text", True, []),
            ("<em>italic</em> text", True, []),
            ("<code>code</code> text", True, []),
            ("<pre>code block</pre>", True, []),
            ('<a href="https://example.com">link</a>', True, []),
            ("<b><i>bold italic</i></b>", True, []),  # Properly nested
            # Unclosed tags
            ("<b>unclosed bold", False, ["Unclosed tags"]),
            ("<i>unclosed italic</b>", False, ["Unmatched closing tag"]),
            ("<b>text</i>", False, ["Unmatched closing tag"]),
            # Invalid tags
            ("<div>invalid tag</div>", False, ["Invalid tag"]),
            ("<span>invalid tag</span>", False, ["Invalid tag"]),
            ("<p>invalid tag</p>", False, ["Invalid tag"]),
            # Properly nested
            ("<b><i>text</i></b>", True, []),
            ("<i><b>text</b></i>", True, []),
            # Multiple tags
            ("<b>bold</b> and <i>italic</i>", True, []),
            # Empty tags
            ("<b></b>", True, []),
            ("<i></i>", True, []),
        ],
    )
    def test_validation(self, html, should_be_valid, expected_errors):
        """Test HTML validation with various edge cases."""
        is_valid, errors = self.validator.validate(html)

        assert (
            is_valid == should_be_valid
        ), f"Validation failed for: {html}\nErrors: {errors}"

        if expected_errors:
            # Check that at least one expected error is present
            error_text = " ".join(errors).lower()
            found_expected = any(
                expected.lower() in error_text for expected in expected_errors
            )
            assert (
                found_expected
            ), f"Expected one of {expected_errors} in errors: {errors}"

    def test_limitations(self):
        """Test that limitations are documented."""
        limitations = self.validator.get_limitations()
        assert len(limitations) > 0
        assert isinstance(limitations, list)
