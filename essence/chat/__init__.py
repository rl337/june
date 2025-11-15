"""
Chat module for structured messaging and human interface.

This module provides:
- Human interface structures (Turn, Message, ContentWidgets)
- Markdown parsing from LLM responses
- Platform-specific translators (Telegram, Discord)
- Message builder for easy integration
"""

from .human_interface import (
    Turn, Message, ContentWidget,
    EscapedText, Paragraph, Heading, ListWidget, ListItem,
    TableWidget, TableRow, TableCell, CodeBlock, Blockquote,
    HorizontalRule, Link, ContentType
)
from .markdown_parser import MarkdownParser, parse_markdown
from .platform_translators import (
    PlatformTranslator, TelegramTranslator, DiscordTranslator, get_translator
)
from .message_builder import MessageBuilder, build_and_render

__all__ = [
    # Core structures
    "Turn", "Message", "ContentWidget",
    "EscapedText", "Paragraph", "Heading", "ListWidget", "ListItem",
    "TableWidget", "TableRow", "TableCell", "CodeBlock", "Blockquote",
    "HorizontalRule", "Link", "ContentType",
    # Parsing
    "MarkdownParser", "parse_markdown",
    # Translation
    "PlatformTranslator", "TelegramTranslator", "DiscordTranslator", "get_translator",
    # Builder
    "MessageBuilder", "build_and_render",
]
