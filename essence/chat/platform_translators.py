"""
Platform-specific translators for rendering ContentWidgets to platform markdown.

Each platform (Telegram, Discord, etc.) has different markdown syntax and limitations.
These translators convert our structured widgets into safe, platform-specific markdown.
"""

import re
import logging
from typing import List
from .human_interface import (
    ContentWidget, EscapedText, Paragraph, Heading, ListWidget, ListItem,
    TableWidget, TableRow, TableCell, CodeBlock, Blockquote,
    HorizontalRule, Link, ContentType
)

logger = logging.getLogger(__name__)


class PlatformTranslator:
    """Base class for platform-specific markdown translators."""
    
    def escape_text(self, text: str) -> str:
        """Escape special characters for safe display."""
        raise NotImplementedError
    
    def render_widget(self, widget: ContentWidget) -> str:
        """Render a widget to platform-specific markdown."""
        raise NotImplementedError
    
    def render_message(self, widgets: List[ContentWidget]) -> str:
        """Render a list of widgets into a single message."""
        parts = []
        for widget in widgets:
            rendered = self.render_widget(widget)
            if rendered:
                parts.append(rendered)
        return '\n\n'.join(parts) if parts else ''
    
    def _render_list_item(self, item: ListItem, ordered: bool, level: int = 0) -> str:
        """Recursively render a list item and its subitems."""
        indent = '  ' * level
        marker = f"{level + 1}." if ordered else "•"
        text = item.text
        
        # Render subitems
        subitems_text = ''
        if item.subitems:
            subitems_parts = []
            for subitem in item.subitems:
                subitems_parts.append(self._render_list_item(subitem, ordered, level + 1))
            subitems_text = '\n'.join(subitems_parts)
        
        result = f"{indent}{marker} {text}"
        if subitems_text:
            result += '\n' + subitems_text
        
        return result


class TelegramTranslator(PlatformTranslator):
    """
    Translator for Telegram's markdown format.
    
    Telegram supports:
    - *bold* and _italic_
    - `code` and ```code blocks```
    - [text](url) for links
    - Limited support for lists (basic formatting)
    
    Telegram does NOT support:
    - Tables (must be converted to text)
    - Nested lists (flattened)
    - Blockquotes (converted to italic)
    """
    
    # Characters that need escaping in Telegram
    # Note: Period (.), exclamation (!), and tilde (~) don't need escaping in normal text
    # Telegram doesn't support strikethrough (~~text~~), so ~ is not a markdown character
    TELEGRAM_ESCAPE_CHARS = r'_*[]()`>#+-=|{}'
    
    def escape_text(self, text: str) -> str:
        """Escape special characters for Telegram."""
        # Escape all special markdown characters
        for char in self.TELEGRAM_ESCAPE_CHARS:
            text = text.replace(char, f'\\{char}')
        return text
    
    def render_widget(self, widget: ContentWidget) -> str:
        """Render widget to Telegram markdown."""
        if isinstance(widget, EscapedText):
            return self.escape_text(widget.text)
        
        elif isinstance(widget, Paragraph):
            # Paragraph may contain inline formatting - preserve it but validate
            return self._sanitize_telegram_markdown(widget.text)
        
        elif isinstance(widget, Heading):
            # Telegram doesn't have headings, use bold
            return f"*{self._sanitize_telegram_markdown(widget.text)}*"
        
        elif isinstance(widget, ListWidget):
            return self._render_list(widget)
        
        elif isinstance(widget, TableWidget):
            # Telegram doesn't support tables - convert to text
            return self._render_table_as_text(widget)
        
        elif isinstance(widget, CodeBlock):
            # Telegram supports code blocks
            language = f"{widget.language}\n" if widget.language else ""
            return f"```{language}{widget.code}```"
        
        elif isinstance(widget, Blockquote):
            # Telegram doesn't support blockquotes - use italic
            return f"_{self._sanitize_telegram_markdown(widget.text)}_"
        
        elif isinstance(widget, HorizontalRule):
            # Telegram doesn't support HR - use dashes
            return "---"
        
        elif isinstance(widget, Link):
            # Telegram supports links
            return f"[{self._sanitize_telegram_markdown(widget.text)}]({widget.url})"
        
        else:
            logger.warning(f"Unknown widget type: {type(widget)}")
            return str(widget)
    
    def _sanitize_telegram_markdown(self, text: str) -> str:
        """
        Sanitize markdown text for Telegram.
        
        Validates that markdown is properly balanced and escapes problematic sequences.
        """
        # Check for unbalanced markdown
        # Count bold markers
        bold_count = text.count('**')
        if bold_count % 2 != 0:
            # Unbalanced - escape all asterisks
            text = text.replace('*', '\\*')
        
        # Count italic markers (single asterisk, not part of bold)
        # This is tricky - we need to handle **bold** and *italic* separately
        # Simple approach: if we have odd number of single asterisks (not part of **), escape them
        single_asterisks = len(re.findall(r'(?<!\*)\*(?!\*)', text))
        if single_asterisks % 2 != 0:
            # Unbalanced - escape single asterisks
            text = re.sub(r'(?<!\*)\*(?!\*)', r'\\*', text)
        
        # Check for unbalanced underscores
        underscore_count = text.count('_')
        if underscore_count % 2 != 0:
            text = text.replace('_', '\\_')
        
        # Check for unbalanced backticks
        backtick_count = text.count('`')
        if backtick_count % 2 != 0:
            text = text.replace('`', '\\`')
        
        # Check for unbalanced brackets (links)
        open_brackets = text.count('[')
        close_brackets = text.count(']')
        if open_brackets != close_brackets:
            # Unbalanced - escape brackets
            text = text.replace('[', '\\[').replace(']', '\\]')
        
        return text
    
    def _render_list(self, widget: ListWidget) -> str:
        """Render a list widget for Telegram."""
        lines = []
        for i, item in enumerate(widget.items):
            if widget.ordered:
                marker = f"{i + 1}."
            else:
                marker = "•"
            text = self._sanitize_telegram_markdown(item.text)
            lines.append(f"{marker} {text}")
            # Telegram doesn't support nested lists well - flatten them
            for subitem in item.subitems:
                subtext = self._sanitize_telegram_markdown(subitem.text)
                lines.append(f"  • {subtext}")
        return '\n'.join(lines)
    
    def _render_table_as_text(self, widget: TableWidget) -> str:
        """Convert table to plain text representation."""
        if not widget.rows:
            return ""
        
        lines = []
        for row in widget.rows:
            if row.is_header:
                # Header row
                cells = [self._sanitize_telegram_markdown(cell.text) for cell in row.cells]
                lines.append(" | ".join(cells))
                lines.append(" | ".join(["---"] * len(cells)))
            else:
                cells = [self._sanitize_telegram_markdown(cell.text) for cell in row.cells]
                lines.append(" | ".join(cells))
        
        return '\n'.join(lines)


class DiscordTranslator(PlatformTranslator):
    """
    Translator for Discord's markdown format.
    
    Discord supports:
    - **bold** and *italic*
    - `code` and ```code blocks```
    - [text](url) for links
    - Basic lists
    - Blockquotes with >
    
    Discord does NOT support:
    - Tables (must be converted to code blocks or text)
    - Headings (converted to bold)
    """
    
    # Characters that need escaping in Discord
    DISCORD_ESCAPE_CHARS = r'_*`~'
    
    def escape_text(self, text: str) -> str:
        """Escape special characters for Discord."""
        for char in self.DISCORD_ESCAPE_CHARS:
            text = text.replace(char, f'\\{char}')
        return text
    
    def render_widget(self, widget: ContentWidget) -> str:
        """Render widget to Discord markdown."""
        if isinstance(widget, EscapedText):
            return self.escape_text(widget.text)
        
        elif isinstance(widget, Paragraph):
            return self._sanitize_discord_markdown(widget.text)
        
        elif isinstance(widget, Heading):
            # Discord doesn't have headings - use bold
            return f"**{self._sanitize_discord_markdown(widget.text)}**"
        
        elif isinstance(widget, ListWidget):
            return self._render_list(widget)
        
        elif isinstance(widget, TableWidget):
            # Discord doesn't support tables - convert to code block
            return self._render_table_as_code(widget)
        
        elif isinstance(widget, CodeBlock):
            language = widget.language or ""
            return f"```{language}\n{widget.code}\n```"
        
        elif isinstance(widget, Blockquote):
            # Discord supports blockquotes
            lines = widget.text.split('\n')
            return '\n'.join(f"> {line}" for line in lines)
        
        elif isinstance(widget, HorizontalRule):
            # Discord doesn't support HR - use dashes
            return "---"
        
        elif isinstance(widget, Link):
            return f"[{self._sanitize_discord_markdown(widget.text)}]({widget.url})"
        
        else:
            logger.warning(f"Unknown widget type: {type(widget)}")
            return str(widget)
    
    def _sanitize_discord_markdown(self, text: str) -> str:
        """Sanitize markdown text for Discord."""
        # Check for unbalanced markdown
        bold_count = text.count('**')
        if bold_count % 2 != 0:
            text = text.replace('**', '\\*\\*')
        
        italic_count = len(re.findall(r'(?<!\*)\*(?!\*)', text))
        if italic_count % 2 != 0:
            text = re.sub(r'(?<!\*)\*(?!\*)', r'\\*', text)
        
        backtick_count = text.count('`')
        if backtick_count % 2 != 0:
            text = text.replace('`', '\\`')
        
        return text
    
    def _render_list(self, widget: ListWidget) -> str:
        """Render a list widget for Discord."""
        lines = []
        for i, item in enumerate(widget.items):
            if widget.ordered:
                marker = f"{i + 1}."
            else:
                marker = "-"
            text = self._sanitize_discord_markdown(item.text)
            lines.append(f"{marker} {text}")
            # Discord supports nested lists better than Telegram
            for subitem in item.subitems:
                subtext = self._sanitize_discord_markdown(subitem.text)
                lines.append(f"  - {subtext}")
        return '\n'.join(lines)
    
    def _render_table_as_code(self, widget: TableWidget) -> str:
        """Convert table to code block representation."""
        if not widget.rows:
            return ""
        
        lines = []
        for row in widget.rows:
            cells = [cell.text for cell in row.cells]
            lines.append(" | ".join(cells))
            if row.is_header:
                # Add separator after header
                lines.append(" | ".join(["---"] * len(cells)))
        
        table_text = '\n'.join(lines)
        return f"```\n{table_text}\n```"


class TelegramHTMLTranslator(PlatformTranslator):
    """
    Translator for Telegram's HTML format.
    
    Telegram HTML supports:
    - <b>bold</b> or <strong>bold</strong>
    - <i>italic</i> or <em>italic</em>
    - <u>underline</u>
    - <s>strikethrough</s> or <strike>strikethrough</strike> or <del>strikethrough</del>
    - <code>inline code</code>
    - <pre>code block</pre>
    - <pre><code class="language">code block</code></pre>
    - <a href="URL">link text</a>
    """
    
    # Characters that need escaping in HTML
    HTML_ESCAPE_CHARS = {
        '<': '&lt;',
        '>': '&gt;',
        '&': '&amp;',
    }
    
    def escape_text(self, text: str) -> str:
        """Escape special characters for HTML."""
        for char, entity in self.HTML_ESCAPE_CHARS.items():
            text = text.replace(char, entity)
        return text
    
    def render_widget(self, widget: ContentWidget) -> str:
        """Render widget to Telegram HTML."""
        if isinstance(widget, EscapedText):
            # Even escaped text might contain markdown formatting (like standalone strikethrough)
            # Check if it looks like it has formatting and parse it
            text = widget.text
            if any(marker in text for marker in ['**', '*', '`', '[', '~~']):
                return self._parse_inline_formatting(text)
            else:
                return self.escape_text(text)
        
        elif isinstance(widget, Paragraph):
            # Parse inline formatting and convert to HTML
            return self._parse_inline_formatting(widget.text)
        
        elif isinstance(widget, Heading):
            # Headings as bold
            return f"<b>{self._parse_inline_formatting(widget.text)}</b>"
        
        elif isinstance(widget, ListWidget):
            return self._render_list(widget)
        
        elif isinstance(widget, TableWidget):
            # Telegram doesn't support tables - convert to text
            return self._render_table_as_text(widget)
        
        elif isinstance(widget, CodeBlock):
            # Telegram supports code blocks
            if widget.language:
                return f"<pre><code class=\"language-{widget.language}\">{self.escape_text(widget.code)}</code></pre>"
            else:
                return f"<pre>{self.escape_text(widget.code)}</pre>"
        
        elif isinstance(widget, Blockquote):
            # Telegram doesn't support blockquotes - use italic
            return f"<i>{self._parse_inline_formatting(widget.text)}</i>"
        
        elif isinstance(widget, HorizontalRule):
            # Telegram doesn't support HR - use dashes
            return "---"
        
        elif isinstance(widget, Link):
            # Telegram supports links
            return f"<a href=\"{widget.url}\">{self._parse_inline_formatting(widget.text)}</a>"
        
        else:
            logger.warning(f"Unknown widget type: {type(widget)}")
            return self.escape_text(str(widget))
    
    def _parse_inline_formatting(self, text: str) -> str:
        """Parse inline markdown formatting and convert to HTML."""
        import re
        
        # Escape HTML first
        text = self.escape_text(text)
        
        # Process strikethrough (~~text~~) - must come before bold/italic
        text = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', text)
        
        # Process bold (**text**)
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        
        # Process italic (*text* but not **text**)
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)
        
        # Process inline code (`code`)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # Process links ([text](url))
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        
        return text
    
    def _render_list(self, widget: ListWidget) -> str:
        """Render a list widget for Telegram HTML."""
        lines = []
        for i, item in enumerate(widget.items):
            if widget.ordered:
                marker = f"{i + 1}."
            else:
                marker = "•"
            text = self._parse_inline_formatting(item.text)
            lines.append(f"{marker} {text}")
            # Telegram doesn't support nested lists well - flatten them
            for subitem in item.subitems:
                subtext = self._parse_inline_formatting(subitem.text)
                lines.append(f"  • {subtext}")
        return '\n'.join(lines)
    
    def _render_table_as_text(self, widget: TableWidget) -> str:
        """Convert table to plain text representation."""
        if not widget.rows:
            return ""
        
        lines = []
        for row in widget.rows:
            if row.is_header:
                # Header row
                cells = [self._parse_inline_formatting(cell.text) for cell in row.cells]
                lines.append(" | ".join(cells))
                lines.append(" | ".join(["---"] * len(cells)))
            else:
                cells = [self._parse_inline_formatting(cell.text) for cell in row.cells]
                lines.append(" | ".join(cells))
        
        return '\n'.join(lines)


def get_translator(platform: str, format: str = "markdown") -> PlatformTranslator:
    """
    Get the appropriate translator for a platform.
    
    Args:
        platform: Platform name ('telegram', 'discord', etc.)
        format: Format to use ('markdown' or 'html' for telegram)
    
    Returns:
        PlatformTranslator instance
    """
    platform_lower = platform.lower()
    format_lower = format.lower()
    
    if platform_lower == 'telegram':
        if format_lower == 'html':
            return TelegramHTMLTranslator()
        else:
            return TelegramTranslator()
    elif platform_lower == 'discord':
        return DiscordTranslator()
    else:
        logger.warning(f"Unknown platform '{platform}', using Telegram translator as fallback")
        return TelegramTranslator()

