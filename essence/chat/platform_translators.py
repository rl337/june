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
        # Join with double newline to preserve spacing between widgets
        # This ensures headings, paragraphs, etc. are properly separated
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
    # Note: Period (.) doesn't need escaping in normal text, only in special contexts
    # We'll escape it only when necessary (e.g., in code or when validation fails)
    TELEGRAM_ESCAPE_CHARS = r'_*[]()~`>#+-=|{}!'
    
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
            # Paragraph may contain inline formatting - preserve it as-is
            # Validation will happen on the full rendered message, not individual widgets
            return widget.text
        
        elif isinstance(widget, Heading):
            # Telegram doesn't have headings, use bold
            return f"*{widget.text}*"
        
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
            return f"_{widget.text}_"
        
        elif isinstance(widget, HorizontalRule):
            # Telegram doesn't support HR - use dashes
            return "---"
        
        elif isinstance(widget, Link):
            # Telegram supports links
            return f"[{widget.text}]({widget.url})"
        
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
            # Preserve inline formatting in list items - validation happens on full message
            lines.append(f"{marker} {item.text}")
            # Telegram doesn't support nested lists well - flatten them
            for subitem in item.subitems:
                lines.append(f"  • {subitem.text}")
        return '\n'.join(lines)
    
    def _render_table_as_text(self, widget: TableWidget) -> str:
        """Convert table to fixed-width ASCII table representation."""
        if not widget.rows:
            return ""
        
        # Extract all cell texts
        all_rows = []
        for row in widget.rows:
            all_rows.append([cell.text for cell in row.cells])
        
        if not all_rows:
            return ""
        
        # Calculate column widths (max width for each column)
        num_cols = len(all_rows[0])
        col_widths = [0] * num_cols
        for row in all_rows:
            for i, cell_text in enumerate(row):
                if i < num_cols:
                    col_widths[i] = max(col_widths[i], len(cell_text))
        
        # Build the table
        lines = []
        for row_idx, row in enumerate(all_rows):
            # Pad cells to column width
            padded_cells = []
            for i, cell_text in enumerate(row):
                if i < num_cols:
                    # Pad to column width (left-align for now)
                    padded = cell_text.ljust(col_widths[i])
                    padded_cells.append(padded)
            
            # Join with separators
            line = " | ".join(padded_cells)
            lines.append(line)
            
            # Add separator after header row
            if row_idx == 0 and widget.rows[0].is_header:
                separator_parts = ["-" * width for width in col_widths]
                separator = "-+-".join(separator_parts)
                lines.append(separator)
        
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


def get_translator(platform: str) -> PlatformTranslator:
    """
    Get the appropriate translator for a platform.
    
    Args:
        platform: Platform name ('telegram', 'discord', etc.)
        
    Returns:
        PlatformTranslator instance
    """
    platform_lower = platform.lower()
    
    if platform_lower == 'telegram':
        return TelegramTranslator()
    elif platform_lower == 'discord':
        return DiscordTranslator()
    else:
        logger.warning(f"Unknown platform '{platform}', using Telegram translator as fallback")
        return TelegramTranslator()

