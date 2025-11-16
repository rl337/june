"""
Markdown parser for extracting structured widgets from LLM markdown responses.

This parser converts raw markdown text from LLMs into structured ContentWidget
objects that can be safely rendered on different platforms.
"""

import re
import logging
from typing import List, Optional
from .human_interface import (
    ContentWidget, EscapedText, Paragraph, Heading, ListWidget, ListItem,
    TableWidget, TableRow, TableCell, CodeBlock, Blockquote,
    HorizontalRule, Link, ContentType
)

logger = logging.getLogger(__name__)


class MarkdownParser:
    """Parser for converting markdown text into structured widgets."""
    
    def __init__(self):
        # Patterns for different markdown elements
        # Heading pattern: allow optional space after # (some markdown allows ###Header or ### Header)
        self.heading_pattern = re.compile(r'^(#{1,6})\s*(.+)$', re.MULTILINE)
        self.code_block_pattern = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
        self.inline_code_pattern = re.compile(r'`([^`]+)`')
        self.bold_pattern = re.compile(r'\*\*([^*]+)\*\*')
        self.italic_pattern = re.compile(r'\*([^*]+)\*')
        self.link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        self.blockquote_pattern = re.compile(r'^>\s+(.+)$', re.MULTILINE)
        self.horizontal_rule_pattern = re.compile(r'^---+\s*$|^===\s*$', re.MULTILINE)
        self.list_item_pattern = re.compile(r'^(\s*)([-*+]|\d+\.)\s+(.+)$', re.MULTILINE)
        self.table_pattern = re.compile(r'^\|(.+)\|$', re.MULTILINE)
        self.table_separator_pattern = re.compile(r'^\|[-:\s|]+\|$', re.MULTILINE)
    
    def parse(self, markdown_text: str) -> List[ContentWidget]:
        """
        Parse markdown text into a list of ContentWidget objects.
        
        Args:
            markdown_text: Raw markdown text from LLM
            
        Returns:
            List of ContentWidget objects in order
        """
        if not markdown_text or not markdown_text.strip():
            return [EscapedText(text="")]
        
        widgets: List[ContentWidget] = []
        
        # Split into lines for processing
        lines = markdown_text.split('\n')
        
        # Track position in text for extracting remaining content
        processed_pos = 0
        text = markdown_text
        
        # First, extract code blocks (they take precedence)
        code_blocks = list(self.code_block_pattern.finditer(text))
        code_block_positions = [(m.start(), m.end(), m) for m in code_blocks]
        
        # Extract headings
        headings = list(self.heading_pattern.finditer(text))
        heading_positions = [(m.start(), m.end(), m) for m in headings]
        
        # Extract horizontal rules
        hr_matches = list(self.horizontal_rule_pattern.finditer(text))
        hr_positions = [(m.start(), m.end()) for m in hr_matches]
        
        # Extract blockquotes (multi-line)
        blockquotes = self._extract_blockquotes(text)
        
        # Extract tables
        tables = self._extract_tables(text)
        
        # Extract lists
        lists = self._extract_lists(text)
        
        # Combine all special elements and sort by position
        all_elements = []
        for start, end, match in code_block_positions:
            all_elements.append((start, end, 'code_block', match))
        for start, end, match in heading_positions:
            all_elements.append((start, end, 'heading', match))
        for start, end in hr_positions:
            all_elements.append((start, end, 'horizontal_rule', None))
        for start, end, content in blockquotes:
            all_elements.append((start, end, 'blockquote', content))
        for start, end, table in tables:
            all_elements.append((start, end, 'table', table))
        for start, end, list_widget in lists:
            all_elements.append((start, end, 'list', list_widget))
        
        # Sort by start position
        all_elements.sort(key=lambda x: x[0])
        
        # Process elements in order, extracting text between them
        current_pos = 0
        
        for start, end, element_type, element_data in all_elements:
            # Add any text before this element as paragraph/escaped text
            if start > current_pos:
                text_before = text[current_pos:start].strip()
                if text_before:
                    widgets.extend(self._parse_text_blocks(text_before))
            
            # Add the special element
            if element_type == 'code_block':
                match = element_data
                language = match.group(1) if match.group(1) else None
                code = match.group(2)
                widgets.append(CodeBlock(code=code, language=language))
            elif element_type == 'heading':
                match = element_data
                level = len(match.group(1))
                heading_text = match.group(2).strip()
                widgets.append(Heading(text=heading_text, level=level))
            elif element_type == 'horizontal_rule':
                widgets.append(HorizontalRule())
            elif element_type == 'blockquote':
                widgets.append(Blockquote(text=element_data))
            elif element_type == 'table':
                widgets.append(element_data)
            elif element_type == 'list':
                widgets.append(element_data)
            
            current_pos = end
        
        # Add any remaining text
        if current_pos < len(text):
            remaining = text[current_pos:].strip()
            if remaining:
                widgets.extend(self._parse_text_blocks(remaining))
        
        # If no widgets were created, create a single escaped text widget
        if not widgets:
            widgets.append(EscapedText(text=markdown_text))
        
        return widgets
    
    def _parse_text_blocks(self, text: str) -> List[ContentWidget]:
        """Parse a block of text into paragraphs, preserving inline formatting."""
        if not text.strip():
            return []
        
        # Split into paragraphs (double newline)
        paragraphs = re.split(r'\n\s*\n', text)
        widgets = []
        
        for para_text in paragraphs:
            para_text = para_text.strip()
            if not para_text:
                continue
            
            # Check if it's a simple escaped text (no markdown) or a paragraph with formatting
            has_formatting = (
                self.bold_pattern.search(para_text) or
                self.italic_pattern.search(para_text) or
                self.inline_code_pattern.search(para_text) or
                self.link_pattern.search(para_text)
            )
            
            if has_formatting:
                widgets.append(Paragraph(text=para_text))
            else:
                # Simple text - escape it
                widgets.append(EscapedText(text=para_text))
        
        return widgets if widgets else [EscapedText(text=text)]
    
    def _extract_blockquotes(self, text: str) -> List[tuple]:
        """Extract blockquote sections from text."""
        blockquotes = []
        lines = text.split('\n')
        in_quote = False
        quote_start = 0
        quote_lines = []
        
        for i, line in enumerate(lines):
            if line.strip().startswith('>'):
                if not in_quote:
                    in_quote = True
                    quote_start = i
                    quote_lines = []
                # Remove '>' prefix and any following space
                quote_line = re.sub(r'^>\s*', '', line)
                quote_lines.append(quote_line)
            else:
                if in_quote:
                    # End of blockquote
                    quote_text = '\n'.join(quote_lines)
                    # Calculate position
                    start_pos = sum(len(l) + 1 for l in lines[:quote_start])
                    end_pos = start_pos + sum(len(l) + 1 for l in quote_lines) - 1
                    blockquotes.append((start_pos, end_pos, quote_text))
                    in_quote = False
                    quote_lines = []
        
        # Handle blockquote at end of text
        if in_quote:
            quote_text = '\n'.join(quote_lines)
            start_pos = sum(len(l) + 1 for l in lines[:quote_start])
            end_pos = start_pos + sum(len(l) + 1 for l in quote_lines) - 1
            blockquotes.append((start_pos, end_pos, quote_text))
        
        return blockquotes
    
    def _extract_tables(self, text: str) -> List[tuple]:
        """Extract table structures from text."""
        tables = []
        lines = text.split('\n')
        
        table_start = None
        table_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith('|'):
                # Not a table line
                if table_start is not None:
                    # End of table - process it
                    table_widget = self._parse_table_lines(table_lines)
                    if table_widget:
                        start_pos = sum(len(l) + 1 for l in lines[:table_start])
                        end_pos = sum(len(l) + 1 for l in lines[:i])
                        tables.append((start_pos, end_pos, table_widget))
                    table_start = None
                    table_lines = []
                continue
            
            # Check if it's a separator line
            if self.table_separator_pattern.match(stripped):
                # Separator line - continue collecting
                continue
            
            # Table row
            if table_start is None:
                table_start = i
            table_lines.append(line)
        
        # Handle table at end
        if table_start is not None:
            table_widget = self._parse_table_lines(table_lines)
            if table_widget:
                start_pos = sum(len(l) + 1 for l in lines[:table_start])
                end_pos = sum(len(l) + 1 for l in lines)
                tables.append((start_pos, end_pos, table_widget))
        
        return tables
    
    def _parse_table_lines(self, lines: List[str]) -> Optional[TableWidget]:
        """Parse table lines into a TableWidget."""
        if not lines:
            return None
        
        rows = []
        header_processed = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith('|') or self.table_separator_pattern.match(stripped):
                continue
            
            # Split by | and clean up
            cells = [cell.strip() for cell in stripped.split('|')[1:-1]]
            if not cells:
                continue
            
            # First non-separator row is header
            is_header = not header_processed
            if is_header:
                header_processed = True
            
            table_cells = [TableCell(text=cell) for cell in cells]
            rows.append(TableRow(cells=table_cells, is_header=is_header))
        
        if not rows:
            return None
        
        return TableWidget(rows=rows)
    
    def _extract_lists(self, text: str) -> List[tuple]:
        """Extract list structures from text."""
        lists = []
        lines = text.split('\n')
        
        list_start = None
        list_items = []
        list_ordered = False
        
        for i, line in enumerate(lines):
            match = self.list_item_pattern.match(line)
            
            if match:
                indent, marker, content = match.groups()
                is_ordered = marker.strip().endswith('.')
                
                # Check if this starts a new list or continues current
                if list_start is None:
                    # New list
                    list_start = i
                    list_ordered = is_ordered
                    list_items = []
                
                # Check if list type matches
                if is_ordered != list_ordered:
                    # Different list type - end current, start new
                    if list_items:
                        list_widget = self._parse_list_items(list_items, list_ordered)
                        if list_widget:
                            start_pos = sum(len(l) + 1 for l in lines[:list_start])
                            end_pos = sum(len(l) + 1 for l in lines[:i])
                            lists.append((start_pos, end_pos, list_widget))
                    list_start = i
                    list_ordered = is_ordered
                    list_items = []
                
                # Add item
                list_items.append((len(indent), content.strip()))
            else:
                # Not a list line
                if list_start is not None:
                    # End of list - process it
                    list_widget = self._parse_list_items(list_items, list_ordered)
                    if list_widget:
                        start_pos = sum(len(l) + 1 for l in lines[:list_start])
                        end_pos = sum(len(l) + 1 for l in lines[:i])
                        lists.append((start_pos, end_pos, list_widget))
                    list_start = None
                    list_items = []
        
        # Handle list at end
        if list_start is not None and list_items:
            list_widget = self._parse_list_items(list_items, list_ordered)
            if list_widget:
                start_pos = sum(len(l) + 1 for l in lines[:list_start])
                end_pos = sum(len(l) + 1 for l in lines)
                lists.append((start_pos, end_pos, list_widget))
        
        return lists
    
    def _parse_list_items(self, items: List[tuple], ordered: bool) -> Optional[ListWidget]:
        """Parse list items into a ListWidget with proper nesting."""
        if not items:
            return None
        
        list_items = []
        stack = []  # Stack of (indent_level, ListItem) for nested items
        
        for indent_level, text in items:
            item = ListItem(text=text)
            
            # Find parent in stack
            while stack and stack[-1][0] >= indent_level:
                stack.pop()
            
            if stack:
                # Add as subitem of parent
                parent_item = stack[-1][1]
                parent_item.subitems.append(item)
            else:
                # Top-level item
                list_items.append(item)
            
            # Push to stack
            stack.append((indent_level, item))
        
        return ListWidget(items=list_items, ordered=ordered)


def parse_markdown(markdown_text: str) -> List[ContentWidget]:
    """
    Convenience function to parse markdown text into widgets.
    
    Args:
        markdown_text: Raw markdown text from LLM
        
    Returns:
        List of ContentWidget objects
    """
    parser = MarkdownParser()
    return parser.parse(markdown_text)

