"""
Chat module for structured messaging and human interface.

This module provides:
- Human interface structures (Turn, Message, ContentWidgets)
- Markdown parsing from LLM responses
- Platform-specific translators (Telegram, Discord)
- Message builder for easy integration
"""

from .human_interface import (
    Blockquote,
    CodeBlock,
    ContentType,
    ContentWidget,
    EscapedText,
    Heading,
    HorizontalRule,
    Link,
    ListItem,
    ListWidget,
    Message,
    Paragraph,
    TableCell,
    TableRow,
    TableWidget,
    Turn,
)
from .markdown_parser import MarkdownParser, parse_markdown
from .message_builder import MessageBuilder, build_and_render
from .platform_translators import (
    DiscordTranslator,
    PlatformTranslator,
    TelegramTranslator,
    get_translator,
)

# Agent communication (optional import to avoid circular dependencies)
try:
    from .agent_communication import (  # noqa: F401
        AgentCommunicationError,
        ChannelUnavailableError,
        CommunicationChannel,
        ServiceRunningError,
        ask_for_clarification,
        ask_for_feedback,
        report_progress,
        request_help,
        send_message_to_user,
    )

    AGENT_COMMUNICATION_AVAILABLE = True
except ImportError:
    AGENT_COMMUNICATION_AVAILABLE = False

__all__ = [
    # Core structures
    "Turn",
    "Message",
    "ContentWidget",
    "EscapedText",
    "Paragraph",
    "Heading",
    "ListWidget",
    "ListItem",
    "TableWidget",
    "TableRow",
    "TableCell",
    "CodeBlock",
    "Blockquote",
    "HorizontalRule",
    "Link",
    "ContentType",
    # Parsing
    "MarkdownParser",
    "parse_markdown",
    # Translation
    "PlatformTranslator",
    "TelegramTranslator",
    "DiscordTranslator",
    "get_translator",
    # Builder
    "MessageBuilder",
    "build_and_render",
]

# Add agent communication exports if available
if AGENT_COMMUNICATION_AVAILABLE:
    __all__.extend(
        [
            "send_message_to_user",
            "ask_for_clarification",
            "request_help",
            "report_progress",
            "ask_for_feedback",
            "CommunicationChannel",
            "AgentCommunicationError",
            "ServiceRunningError",
            "ChannelUnavailableError",
        ]
    )
