"""
Message history storage for debugging Telegram and Discord rendering issues.

Provides in-memory storage for all sent messages, allowing inspection of what
was actually rendered and sent to users.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class MessageHistoryEntry:
    """Represents a single message history entry."""
    timestamp: datetime
    platform: str  # "telegram" or "discord"
    user_id: str
    chat_id: str  # chat_id for Telegram, channel_id for Discord
    message_content: str
    message_type: str  # "text", "voice", "error", "status"
    message_id: Optional[str] = None  # Platform-specific message ID if available
    raw_text: Optional[str] = None  # Raw text before formatting
    formatted_text: Optional[str] = None  # Formatted text (HTML/markdown)
    rendering_metadata: Dict[str, Any] = field(default_factory=dict)  # Truncation, formatting applied, etc.


class MessageHistory:
    """
    In-memory storage for message history.
    
    Stores all sent messages for debugging rendering issues. Uses in-memory
    storage consistent with MVP architecture, but designed to allow future
    migration to persistent storage if needed.
    """
    
    def __init__(self, max_entries: int = 10000):
        """
        Initialize message history storage.
        
        Args:
            max_entries: Maximum number of entries to store (FIFO eviction)
        """
        self._messages: List[MessageHistoryEntry] = []
        self._max_entries = max_entries
        self._by_user: Dict[str, List[int]] = defaultdict(list)  # user_id -> list of indices
        self._by_chat: Dict[str, List[int]] = defaultdict(list)  # chat_id -> list of indices
    
    def add_message(
        self,
        platform: str,
        user_id: str,
        chat_id: str,
        message_content: str,
        message_type: str = "text",
        message_id: Optional[str] = None,
        raw_text: Optional[str] = None,
        formatted_text: Optional[str] = None,
        rendering_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a message to history.
        
        Args:
            platform: Platform name ("telegram" or "discord")
            user_id: User ID
            chat_id: Chat/channel ID
            message_content: The actual message content sent
            message_type: Type of message ("text", "voice", "error", "status")
            message_id: Platform-specific message ID if available
            raw_text: Raw text before formatting (optional)
            formatted_text: Formatted text with HTML/markdown (optional)
            rendering_metadata: Additional metadata about rendering (optional)
        """
        entry = MessageHistoryEntry(
            timestamp=datetime.now(),
            platform=platform,
            user_id=str(user_id),
            chat_id=str(chat_id),
            message_content=message_content,
            message_type=message_type,
            message_id=message_id,
            raw_text=raw_text,
            formatted_text=formatted_text,
            rendering_metadata=rendering_metadata or {}
        )
        
        # Add to main list
        index = len(self._messages)
        self._messages.append(entry)
        
        # Update indices
        self._by_user[entry.user_id].append(index)
        self._by_chat[entry.chat_id].append(index)
        
        # Evict oldest entries if over limit
        if len(self._messages) > self._max_entries:
            self._evict_oldest()
        
        logger.debug(
            f"Added message to history: platform={platform}, user_id={user_id}, "
            f"chat_id={chat_id}, type={message_type}, content_length={len(message_content)}"
        )
    
    def _evict_oldest(self) -> None:
        """Evict oldest entries when over limit."""
        num_to_evict = len(self._messages) - self._max_entries
        
        # Remove oldest entries
        for _ in range(num_to_evict):
            if not self._messages:
                break
            
            entry = self._messages.pop(0)
            
            # Remove from indices
            if entry.user_id in self._by_user:
                indices = self._by_user[entry.user_id]
                if indices:
                    indices.pop(0)
                if not indices:
                    del self._by_user[entry.user_id]
            
            if entry.chat_id in self._by_chat:
                indices = self._by_chat[entry.chat_id]
                if indices:
                    indices.pop(0)
                if not indices:
                    del self._by_chat[entry.chat_id]
        
        # Rebuild indices (shift all indices down by num_to_evict)
        for user_id in self._by_user:
            self._by_user[user_id] = [idx - num_to_evict for idx in self._by_user[user_id] if idx >= num_to_evict]
        
        for chat_id in self._by_chat:
            self._by_chat[chat_id] = [idx - num_to_evict for idx in self._by_chat[chat_id] if idx >= num_to_evict]
    
    def get_messages(
        self,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        platform: Optional[str] = None,
        message_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[MessageHistoryEntry]:
        """
        Retrieve messages matching criteria.
        
        Args:
            user_id: Filter by user ID (optional)
            chat_id: Filter by chat/channel ID (optional)
            platform: Filter by platform ("telegram" or "discord") (optional)
            message_type: Filter by message type (optional)
            limit: Maximum number of results to return (optional)
            
        Returns:
            List of matching MessageHistoryEntry objects, ordered by timestamp (newest first)
        """
        # Use indices for efficient filtering
        if user_id:
            indices = self._by_user.get(str(user_id), [])
        elif chat_id:
            indices = self._by_chat.get(str(chat_id), [])
        else:
            indices = list(range(len(self._messages)))
        
        # Get entries and filter
        results = []
        for idx in reversed(indices):  # Newest first
            if idx >= len(self._messages):
                continue
            
            entry = self._messages[idx]
            
            # Apply filters
            if platform and entry.platform != platform:
                continue
            if message_type and entry.message_type != message_type:
                continue
            
            results.append(entry)
            
            if limit and len(results) >= limit:
                break
        
        return results
    
    def clear(self) -> None:
        """Clear all message history."""
        self._messages.clear()
        self._by_user.clear()
        self._by_chat.clear()
        logger.info("Message history cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored messages.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "total_messages": len(self._messages),
            "max_entries": self._max_entries,
            "by_platform": {
                platform: sum(1 for m in self._messages if m.platform == platform)
                for platform in ["telegram", "discord"]
            },
            "by_type": {
                msg_type: sum(1 for m in self._messages if m.message_type == msg_type)
                for msg_type in ["text", "voice", "error", "status"]
            },
            "unique_users": len(self._by_user),
            "unique_chats": len(self._by_chat)
        }


# Global singleton instance
_message_history: Optional[MessageHistory] = None


def get_message_history() -> MessageHistory:
    """
    Get the global message history instance.
    
    Returns:
        MessageHistory instance
    """
    global _message_history
    if _message_history is None:
        _message_history = MessageHistory()
    return _message_history


def reset_message_history() -> None:
    """Reset the global message history (useful for testing)."""
    global _message_history
    _message_history = None
