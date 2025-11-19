"""
CLI command to retrieve message history for debugging.

Provides access to message history stored by Telegram and Discord handlers,
allowing inspection of what messages were actually sent to users.
"""
import json
import logging
from datetime import datetime
from typing import Optional
import argparse

from essence.command import Command
from essence.chat.message_history import get_message_history

logger = logging.getLogger(__name__)


class GetMessageHistoryCommand(Command):
    """Command to retrieve message history for debugging."""
    
    @classmethod
    def get_name(cls) -> str:
        return "get-message-history"
    
    def init(self) -> None:
        """Initialize the command."""
        pass
    
    def run(self) -> None:
        """Run the command."""
        parser = argparse.ArgumentParser(
            description="Retrieve message history for debugging Telegram and Discord rendering issues",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Get last 10 messages for a user
  poetry run -m essence get-message-history --user-id 12345 --limit 10

  # Get all messages for a chat/channel
  poetry run -m essence get-message-history --chat-id 67890

  # Get only error messages
  poetry run -m essence get-message-history --message-type error

  # Get messages in JSON format
  poetry run -m essence get-message-history --user-id 12345 --format json

  # Get statistics
  poetry run -m essence get-message-history --stats
            """
        )
        
        parser.add_argument(
            "--user-id",
            type=str,
            help="Filter by user ID"
        )
        parser.add_argument(
            "--chat-id",
            type=str,
            help="Filter by chat/channel ID"
        )
        parser.add_argument(
            "--platform",
            choices=["telegram", "discord"],
            help="Filter by platform"
        )
        parser.add_argument(
            "--message-type",
            choices=["text", "voice", "error", "status"],
            help="Filter by message type"
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of results to return (default: 50)"
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format (default: text)"
        )
        parser.add_argument(
            "--stats",
            action="store_true",
            help="Show statistics instead of messages"
        )
        
        args = parser.parse_args()
        
        history = get_message_history()
        
        if args.stats:
            stats = history.get_stats()
            if args.format == "json":
                print(json.dumps(stats, indent=2, default=str))
            else:
                print("Message History Statistics:")
                print(f"  Total messages: {stats['total_messages']}")
                print(f"  Max entries: {stats['max_entries']}")
                print(f"  Unique users: {stats['unique_users']}")
                print(f"  Unique chats: {stats['unique_chats']}")
                print("\nBy Platform:")
                for platform, count in stats['by_platform'].items():
                    print(f"  {platform}: {count}")
                print("\nBy Type:")
                for msg_type, count in stats['by_type'].items():
                    print(f"  {msg_type}: {count}")
            return
        
        # Get messages
        messages = history.get_messages(
            user_id=args.user_id,
            chat_id=args.chat_id,
            platform=args.platform,
            message_type=args.message_type,
            limit=args.limit or 50
        )
        
        if not messages:
            print("No messages found matching criteria.")
            return
        
        if args.format == "json":
            # Output as JSON
            output = []
            for msg in messages:
                output.append({
                    "timestamp": msg.timestamp.isoformat(),
                    "platform": msg.platform,
                    "user_id": msg.user_id,
                    "chat_id": msg.chat_id,
                    "message_content": msg.message_content,
                    "message_type": msg.message_type,
                    "message_id": msg.message_id,
                    "raw_text": msg.raw_text,
                    "formatted_text": msg.formatted_text,
                    "rendering_metadata": msg.rendering_metadata
                })
            print(json.dumps(output, indent=2, default=str))
        else:
            # Output as formatted text
            print(f"Found {len(messages)} message(s):\n")
            for i, msg in enumerate(messages, 1):
                print(f"--- Message {i} ---")
                print(f"Timestamp: {msg.timestamp.isoformat()}")
                print(f"Platform: {msg.platform}")
                print(f"User ID: {msg.user_id}")
                print(f"Chat ID: {msg.chat_id}")
                print(f"Message Type: {msg.message_type}")
                if msg.message_id:
                    print(f"Message ID: {msg.message_id}")
                print(f"\nContent ({len(msg.message_content)} chars):")
                print(f"{msg.message_content[:500]}{'...' if len(msg.message_content) > 500 else ''}")
                if msg.raw_text and msg.raw_text != msg.message_content:
                    print(f"\nRaw Text ({len(msg.raw_text)} chars):")
                    print(f"{msg.raw_text[:500]}{'...' if len(msg.raw_text) > 500 else ''}")
                if msg.formatted_text and msg.formatted_text != msg.message_content:
                    print(f"\nFormatted Text ({len(msg.formatted_text)} chars):")
                    print(f"{msg.formatted_text[:500]}{'...' if len(msg.formatted_text) > 500 else ''}")
                if msg.rendering_metadata:
                    print(f"\nRendering Metadata:")
                    for key, value in msg.rendering_metadata.items():
                        print(f"  {key}: {value}")
                print()
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        pass
