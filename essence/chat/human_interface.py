"""
Human Interface Layer for structured messaging across platforms.

This module provides a structured approach to handling rich text responses
that are safe for various messaging services (Telegram, Discord, etc.).

The core concepts:
- Turn: A complete interaction (user request + bot response) for debugging/logging
- Message: A container for parsed markdown blocks that get sent to users
- Content: Either escaped text (safe) or markdown widgets (lists, tables, etc.)
- Translation: Platform-specific rendering of markdown widgets
"""

import gzip
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

logger = logging.getLogger(__name__)


class ContentType(str, Enum):
    """Types of content that can appear in a message."""

    ESCAPED_TEXT = "escaped_text"  # Plain text with special chars escaped
    PARAGRAPH = "paragraph"  # Paragraph of text (may contain inline formatting)
    HEADING = "heading"  # Heading (h1-h6)
    LIST = "list"  # Ordered or unordered list
    TABLE = "table"  # Table with rows and columns
    CODE_BLOCK = "code_block"  # Code block with language
    BLOCKQUOTE = "blockquote"  # Blockquote
    HORIZONTAL_RULE = "horizontal_rule"  # Horizontal rule/divider
    LINK = "link"  # Link with text and URL


@dataclass
class EscapedText:
    """Plain text content with platform-specific escaping applied."""

    text: str
    content_type: Literal[ContentType.ESCAPED_TEXT] = ContentType.ESCAPED_TEXT

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.content_type.value, "text": self.text}


@dataclass
class Paragraph:
    """A paragraph of text that may contain inline markdown formatting."""

    text: str  # May contain **bold**, *italic*, `code`, etc.
    content_type: Literal[ContentType.PARAGRAPH] = ContentType.PARAGRAPH

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.content_type.value, "text": self.text}


@dataclass
class Heading:
    """A heading element."""

    text: str
    level: int  # 1-6 for h1-h6
    content_type: Literal[ContentType.HEADING] = ContentType.HEADING

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.content_type.value, "text": self.text, "level": self.level}


@dataclass
class ListItem:
    """A single item in a list."""

    text: str  # May contain inline formatting
    subitems: List["ListItem"] = field(default_factory=list)


@dataclass
class ListWidget:
    """An ordered or unordered list."""

    items: List[ListItem]
    ordered: bool = False  # True for ordered list, False for unordered
    content_type: Literal[ContentType.LIST] = ContentType.LIST

    def to_dict(self) -> Dict[str, Any]:
        def item_to_dict(item: ListItem) -> Dict[str, Any]:
            return {
                "text": item.text,
                "subitems": [item_to_dict(sub) for sub in item.subitems],
            }

        return {
            "type": self.content_type.value,
            "ordered": self.ordered,
            "items": [item_to_dict(item) for item in self.items],
        }


@dataclass
class TableCell:
    """A single cell in a table."""

    text: str  # May contain inline formatting
    align: Optional[Literal["left", "center", "right"]] = None


@dataclass
class TableRow:
    """A row in a table."""

    cells: List[TableCell]
    is_header: bool = False


@dataclass
class TableWidget:
    """A table with rows and columns."""

    rows: List[TableRow]
    content_type: Literal[ContentType.TABLE] = ContentType.TABLE

    def to_dict(self) -> Dict[str, Any]:
        def row_to_dict(row: TableRow) -> Dict[str, Any]:
            return {
                "is_header": row.is_header,
                "cells": [
                    {"text": cell.text, "align": cell.align} for cell in row.cells
                ],
            }

        return {
            "type": self.content_type.value,
            "rows": [row_to_dict(row) for row in self.rows],
        }


@dataclass
class CodeBlock:
    """A code block with optional language."""

    code: str
    language: Optional[str] = None
    content_type: Literal[ContentType.CODE_BLOCK] = ContentType.CODE_BLOCK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.content_type.value,
            "code": self.code,
            "language": self.language,
        }


@dataclass
class Blockquote:
    """A blockquote."""

    text: str  # May contain inline formatting
    content_type: Literal[ContentType.BLOCKQUOTE] = ContentType.BLOCKQUOTE

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.content_type.value, "text": self.text}


@dataclass
class HorizontalRule:
    """A horizontal rule/divider."""

    content_type: Literal[ContentType.HORIZONTAL_RULE] = ContentType.HORIZONTAL_RULE

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.content_type.value}


@dataclass
class Link:
    """A link with text and URL."""

    text: str
    url: str
    content_type: Literal[ContentType.LINK] = ContentType.LINK

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.content_type.value, "text": self.text, "url": self.url}


@dataclass
class ErrorMessage:
    """
    Structured error message for error conditions.

    Contains:
    - User-friendly message (escaped text)
    - Underlying exception/error details (escaped text)
    - Error type/classification
    """

    user_message: str  # User-friendly error message
    error_details: str  # Underlying exception or raw error condition (escaped)
    error_type: str  # Error classification (e.g., "ParseError", "NetworkError", "ValidationError")
    content_type: Literal[ContentType.ESCAPED_TEXT] = ContentType.ESCAPED_TEXT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "error",
            "user_message": self.user_message,
            "error_details": self.error_details,
            "error_type": self.error_type,
        }

    @classmethod
    def from_exception(
        cls, exception: Exception, user_message: Optional[str] = None
    ) -> "ErrorMessage":
        """Create an ErrorMessage from an exception."""
        error_type = type(exception).__name__
        error_details = str(exception)
        if user_message is None:
            user_message = f"An error occurred: {error_type}"
        return cls(
            user_message=user_message,
            error_details=error_details,
            error_type=error_type,
        )


# Union type for all content widgets
ContentWidget = Union[
    EscapedText,
    Paragraph,
    Heading,
    ListWidget,
    TableWidget,
    CodeBlock,
    Blockquote,
    HorizontalRule,
    Link,
]


@dataclass
class Message:
    """
    A message container that holds parsed markdown blocks.

    A message represents a single message that will be sent to the user.
    It contains one or more content widgets that were parsed from the LLM's markdown response.
    """

    content: List[ContentWidget]
    message_id: Optional[str] = None  # Optional ID for tracking/editing

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "content": [widget.to_dict() for widget in self.content],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Reconstruct a Message from a dictionary."""
        content = []
        for item in data.get("content", []):
            widget = _widget_from_dict(item)
            if widget:
                content.append(widget)
        return cls(content=content, message_id=data.get("message_id"))


@dataclass
class Turn:
    """
    A complete interaction turn for debugging and logging.

    Contains:
    - User's request
    - Full bot response (all messages)
    - Metadata (timestamps, service name, user/chat IDs, etc.)

    Turns are logged to structured JSON files for debugging purposes.
    """

    user_request: str
    messages: List[Message]
    service_name: str
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turn_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert turn to dictionary for JSON serialization."""
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp.isoformat(),
            "service_name": self.service_name,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "user_request": self.user_request,
            "messages": [msg.to_dict() for msg in self.messages],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Turn":
        """Reconstruct a Turn from a dictionary."""
        return cls(
            turn_id=data.get("turn_id"),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data
            else datetime.now(timezone.utc),
            service_name=data["service_name"],
            user_id=data.get("user_id"),
            chat_id=data.get("chat_id"),
            user_request=data["user_request"],
            messages=[Message.from_dict(msg) for msg in data.get("messages", [])],
            metadata=data.get("metadata", {}),
        )

    def log_to_file(self, log_dir: Path = Path("/var/log/june")) -> Optional[Path]:
        """
        Log this turn to a structured JSON file.

        Files are organized as: <log_dir>/<service_name>/turns_YYYYMMDD.json.gz

        Args:
            log_dir: Base directory for logs (default: /var/log/june)

        Returns:
            Path to the log file if successful, None otherwise
        """
        try:
            # Create service-specific log directory
            service_log_dir = log_dir / self.service_name
            service_log_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with date
            date_str = self.timestamp.strftime("%Y%m%d")
            log_file = service_log_dir / f"turns_{date_str}.json.gz"

            # Read existing turns if file exists
            turns = []
            if log_file.exists():
                try:
                    with gzip.open(log_file, "rt", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                turns.append(json.loads(line))
                except Exception as e:
                    logger.warning(f"Error reading existing log file {log_file}: {e}")

            # Append this turn (one JSON object per line, gzipped)
            turn_dict = self.to_dict()
            with gzip.open(log_file, "at", encoding="utf-8") as f:
                f.write(json.dumps(turn_dict, ensure_ascii=False) + "\n")

            logger.debug(f"Logged turn {self.turn_id} to {log_file}")
            return log_file

        except Exception as e:
            logger.error(f"Failed to log turn to file: {e}", exc_info=True)
            return None


def _widget_from_dict(data: Dict[str, Any]) -> Optional[ContentWidget]:
    """Helper to reconstruct a widget from a dictionary."""
    widget_type = data.get("type")

    if widget_type == ContentType.ESCAPED_TEXT.value:
        return EscapedText(text=data["text"])
    elif widget_type == ContentType.PARAGRAPH.value:
        return Paragraph(text=data["text"])
    elif widget_type == ContentType.HEADING.value:
        return Heading(text=data["text"], level=data.get("level", 1))
    elif widget_type == ContentType.LIST.value:

        def dict_to_item(item_data: Dict[str, Any]) -> ListItem:
            return ListItem(
                text=item_data["text"],
                subitems=[dict_to_item(sub) for sub in item_data.get("subitems", [])],
            )

        return ListWidget(
            items=[dict_to_item(item) for item in data.get("items", [])],
            ordered=data.get("ordered", False),
        )
    elif widget_type == ContentType.TABLE.value:

        def dict_to_row(row_data: Dict[str, Any]) -> TableRow:
            return TableRow(
                cells=[
                    TableCell(text=cell["text"], align=cell.get("align"))
                    for cell in row_data.get("cells", [])
                ],
                is_header=row_data.get("is_header", False),
            )

        return TableWidget(rows=[dict_to_row(row) for row in data.get("rows", [])])
    elif widget_type == ContentType.CODE_BLOCK.value:
        return CodeBlock(code=data["code"], language=data.get("language"))
    elif widget_type == ContentType.BLOCKQUOTE.value:
        return Blockquote(text=data["text"])
    elif widget_type == ContentType.HORIZONTAL_RULE.value:
        return HorizontalRule()
    elif widget_type == ContentType.LINK.value:
        return Link(text=data["text"], url=data["url"])
    else:
        logger.warning(f"Unknown widget type: {widget_type}")
        return None
