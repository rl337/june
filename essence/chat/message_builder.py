"""
Message builder for creating structured messages from LLM responses.

This module provides a high-level interface for:
1. Parsing LLM markdown responses into structured widgets
2. Building Turn objects for logging
3. Rendering messages for specific platforms
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional
from .human_interface import Turn, Message, ContentWidget
from .markdown_parser import parse_markdown
from .platform_translators import get_translator, PlatformTranslator

logger = logging.getLogger(__name__)


class MessageBuilder:
    """
    Builder for creating structured messages from LLM responses.
    
    Usage:
        builder = MessageBuilder(service_name="telegram", user_id="123", chat_id="456")
        turn = builder.build_turn(user_request="Hello", llm_response="**Hi!** How can I help?")
        messages = builder.render_for_platform("telegram")
        turn.log_to_file()  # Log for debugging
    """
    
    def __init__(
        self,
        service_name: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        translator: Optional[PlatformTranslator] = None
    ):
        """
        Initialize the message builder.
        
        Args:
            service_name: Name of the service (e.g., "telegram", "discord")
            user_id: User ID for logging
            chat_id: Chat ID for logging
            translator: Optional platform translator (auto-detected if None)
        """
        self.service_name = service_name
        self.user_id = user_id
        self.chat_id = chat_id
        self.translator = translator or get_translator(service_name)
        self.current_turn: Optional[Turn] = None
    
    def build_turn(
        self,
        user_request: str,
        llm_response: str,
        metadata: Optional[dict] = None
    ) -> Turn:
        """
        Build a Turn object from user request and LLM response.
        
        Args:
            user_request: The user's original message
            llm_response: The raw markdown response from the LLM
            metadata: Optional additional metadata for logging
            
        Returns:
            Turn object containing parsed messages
        """
        # Parse markdown into widgets
        widgets = parse_markdown(llm_response)
        
        # Create message(s) from widgets
        # For now, create a single message with all widgets
        # In the future, we might split into multiple messages based on length
        message = Message(content=widgets, message_id=str(uuid.uuid4()))
        
        # Create turn
        turn = Turn(
            user_request=user_request,
            messages=[message],
            service_name=self.service_name,
            user_id=self.user_id,
            chat_id=self.chat_id,
            turn_id=str(uuid.uuid4()),
            metadata=metadata or {}
        )
        
        self.current_turn = turn
        return turn
    
    def render_message(self, message: Optional[Message] = None) -> str:
        """
        Render a message to platform-specific markdown.
        
        Args:
            message: Message to render (uses current turn's first message if None)
            
        Returns:
            Platform-specific markdown string
        """
        if message is None:
            if not self.current_turn or not self.current_turn.messages:
                return ""
            message = self.current_turn.messages[0]
        
        return self.translator.render_message(message.content)
    
    def render_all_messages(self) -> List[str]:
        """
        Render all messages from the current turn.
        
        Returns:
            List of platform-specific markdown strings, one per message
        """
        if not self.current_turn:
            return []
        
        return [
            self.translator.render_message(msg.content)
            for msg in self.current_turn.messages
        ]
    
    def split_message_if_needed(
        self,
        max_length: int = 4096,
        message: Optional[Message] = None
    ) -> List[str]:
        """
        Split a message into multiple parts if it exceeds max_length.
        
        Strategy:
        - If message is <= max_length: return as single message
        - If message is <= 2 * max_length: split into 2 messages
        - If message is > 2 * max_length: truncate to 2 messages with truncation indicator
        
        Args:
            max_length: Maximum length per message (default 4096 for Telegram)
            message: Message to split (uses current turn's first message if None)
            
        Returns:
            List of message strings, split if necessary
        """
        if message is None:
            if not self.current_turn or not self.current_turn.messages:
                return []
            message = self.current_turn.messages[0]
        
        rendered = self.render_message(message)
        
        # If within limit, return as single message
        if len(rendered) <= max_length:
            return [rendered]
        
        # If <= 2 * max_length, split into 2 messages
        if len(rendered) <= 2 * max_length:
            # Try to split at widget boundaries first
            parts = self._split_at_widget_boundaries(message, max_length)
            if parts:
                return parts
            
            # Fall back to character-based split at midpoint
            midpoint = len(rendered) // 2
            # Try to find a good split point (newline, space, etc.)
            split_point = self._find_split_point(rendered, midpoint, max_length)
            return [
                rendered[:split_point].rstrip(),
                rendered[split_point:].lstrip()
            ]
        
        # If > 2 * max_length, truncate to 2 messages
        # Try to split at widget boundaries for first message
        parts = self._split_at_widget_boundaries(message, max_length)
        if parts and len(parts) >= 1:
            first_part = parts[0]
            # Ensure first part doesn't exceed limit
            if len(first_part) > max_length:
                first_part = first_part[:max_length]
            # Truncate remaining content for second message
            remaining = rendered[len(first_part):]
            truncation_indicator = "\n\n... (message truncated)"
            max_remaining = max_length - len(truncation_indicator)
            if len(remaining) > max_remaining:
                remaining = remaining[:max_remaining] + truncation_indicator
            return [first_part, remaining]
        
        # Fall back to simple truncation
        truncation_indicator = "\n\n... (message truncated)"
        truncation_len = len(truncation_indicator)
        first_message = rendered[:max_length - truncation_len]
        # Second message: take from end of first to 2*max_length, but ensure it fits
        second_start = max_length - truncation_len
        second_end = min(second_start + max_length - truncation_len, len(rendered))
        second_content = rendered[second_start:second_end]
        second_message = second_content + truncation_indicator
        # Ensure second message doesn't exceed limit
        if len(second_message) > max_length:
            second_message = second_message[:max_length - truncation_len] + truncation_indicator
        return [first_message, second_message]
    
    def _split_at_widget_boundaries(self, message: Message, max_length: int) -> List[str]:
        """Try to split message at widget boundaries."""
        parts = []
        current_part = ""
        
        for widget in message.content:
            widget_text = self.translator.render_widget(widget)
            
            # If adding this widget would exceed limit, start new part
            if current_part and len(current_part) + len(widget_text) + 2 > max_length:
                if current_part:
                    parts.append(current_part)
                current_part = widget_text
            else:
                if current_part:
                    current_part += "\n\n" + widget_text
                else:
                    current_part = widget_text
        
        if current_part:
            parts.append(current_part)
        
        return parts if len(parts) > 1 else []
    
    def _find_split_point(self, text: str, start_pos: int, max_length: int) -> int:
        """Find a good split point near start_pos."""
        # Look for newline first
        for offset in range(0, min(200, len(text) - start_pos)):
            if start_pos + offset < len(text) and text[start_pos + offset] == '\n':
                return start_pos + offset + 1
            if start_pos - offset >= 0 and text[start_pos - offset] == '\n':
                return start_pos - offset + 1
        
        # Look for space
        for offset in range(0, min(100, len(text) - start_pos)):
            if start_pos + offset < len(text) and text[start_pos + offset] == ' ':
                return start_pos + offset + 1
            if start_pos - offset >= 0 and text[start_pos - offset] == ' ':
                return start_pos - offset + 1
        
        # Just split at start_pos
        return start_pos


def build_and_render(
    user_request: str,
    llm_response: str,
    service_name: str,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    max_message_length: int = 4096,
    log_turn: bool = True
) -> tuple[List[str], Turn]:
    """
    Convenience function to build a turn and render messages.
    
    Args:
        user_request: User's original message
        llm_response: Raw markdown response from LLM
        service_name: Service name (e.g., "telegram", "discord")
        user_id: User ID for logging
        chat_id: Chat ID for logging
        max_message_length: Maximum length per message
        log_turn: Whether to log the turn to file
        
    Returns:
        Tuple of (rendered_messages, turn)
    """
    builder = MessageBuilder(service_name, user_id, chat_id)
    turn = builder.build_turn(user_request, llm_response)
    
    # Render messages, splitting if needed
    rendered_messages = []
    for message in turn.messages:
        parts = builder.split_message_if_needed(max_message_length, message)
        rendered_messages.extend(parts)
    
    # Log turn if requested
    if log_turn:
        turn.log_to_file()
    
    return rendered_messages, turn

