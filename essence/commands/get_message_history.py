"""
CLI command to retrieve message history for debugging.

Provides access to message history stored by Telegram and Discord handlers,
allowing inspection of what messages were actually sent to users.

Also provides programmatic access for agents via essence.chat.message_history_analysis module.
"""
import argparse
import json
import logging
import sys
from typing import Optional

from essence.chat.message_history import get_message_history
from essence.chat.message_history_analysis import (
    analyze_rendering_issues,
    compare_expected_vs_actual,
    get_message_statistics,
    validate_message_for_platform,
)
from essence.command import Command

logger = logging.getLogger(__name__)


class GetMessageHistoryCommand(Command):
    """Command to retrieve message history for debugging."""

    @classmethod
    def get_name(cls) -> str:
        return "get-message-history"

    @classmethod
    def get_description(cls) -> str:
        return "Retrieve and analyze message history for debugging Telegram and Discord rendering issues"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--user-id", type=str, help="Filter by user ID")
        parser.add_argument("--chat-id", type=str, help="Filter by chat/channel ID")
        parser.add_argument(
            "--platform", choices=["telegram", "discord"], help="Filter by platform"
        )
        parser.add_argument(
            "--message-type",
            choices=["text", "voice", "error", "status"],
            help="Filter by message type",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of results to return (default: 50)",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format (default: text)",
        )
        parser.add_argument(
            "--stats", action="store_true", help="Show statistics instead of messages"
        )
        parser.add_argument(
            "--analyze",
            action="store_true",
            help="Analyze messages for rendering issues",
        )
        parser.add_argument(
            "--compare",
            type=str,
            metavar="TEXT",
            help="Compare expected text with actual sent message",
        )
        parser.add_argument(
            "--validate",
            type=str,
            metavar="TEXT",
            help="Validate message text for platform (requires --platform)",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Number of hours to look back for analysis (default: 24)",
        )

    def init(self) -> None:
        """Initialize the command."""
        pass

    def run(self) -> None:
        """Run the command."""
        history = get_message_history()

        # Handle validation request
        if self.args.validate:
            if not self.args.platform:
                print("Error: --validate requires --platform to be specified", file=sys.stderr)
                print("Usage: poetry run python -m essence get-message-history --validate 'TEXT' --platform telegram", file=sys.stderr)
                sys.exit(1)

            result = validate_message_for_platform(
                self.args.validate,
                self.args.platform,
                getattr(self.args, "parse_mode", None),
            )

            if self.args.format == "json":
                print(json.dumps(result, indent=2, default=str))
            else:
                print(f"Validation for {self.args.platform}:")
                print(f"  Valid: {result['valid']}")
                print(f"  Length: {result['length']}/{result['max_length']}")
                print(f"  Within limit: {result['within_length_limit']}")
                if result["warnings"]:
                    print(f"  Warnings: {len(result['warnings'])}")
                    for warning in result["warnings"]:
                        print(f"    - {warning}")
                if result["errors"]:
                    print(f"  Errors: {len(result['errors'])}")
                    for error in result["errors"]:
                        print(f"    - {error}")
            return

        # Handle comparison request
        if self.args.compare:
            result = compare_expected_vs_actual(
                self.args.compare,
                user_id=self.args.user_id,
                chat_id=self.args.chat_id,
                platform=self.args.platform,
                hours=self.args.hours,
            )

            if not result:
                print("No matching message found in recent history.")
                return

            if self.args.format == "json":
                print(json.dumps(result, indent=2, default=str))
            else:
                print("Expected vs Actual Comparison:")
                print(f"  Expected: {result['expected_length']} chars")
                print(f"  Actual: {result['actual_length']} chars")
                print(f"  Raw: {result['raw_length']} chars")
                print(f"  Similarity: {result['similarity']:.2%}")
                if result["differences"]:
                    print(f"  Differences: {len(result['differences'])}")
                    for diff in result["differences"]:
                        print(f"    - {diff['type']}: {diff['description']}")
            return

        # Handle analysis request
        if self.args.analyze:
            result = analyze_rendering_issues(
                user_id=self.args.user_id,
                chat_id=self.args.chat_id,
                platform=self.args.platform,
                hours=self.args.hours,
            )

            if self.args.format == "json":
                print(json.dumps(result, indent=2, default=str))
            else:
                print("Rendering Issues Analysis:")
                print(f"  Total messages: {result['total_messages']}")
                print(f"  Split messages: {result['split_messages']}")
                print(f"  Truncated messages: {result['truncated_messages']}")
                print(f"  Format mismatches: {result['format_mismatches']}")
                print(f"  Exceeded limit: {result['exceeded_limit']}")
                if result["issues"]:
                    print(f"\n  Issues found: {len(result['issues'])}")
                    for issue in result["issues"][:10]:  # Show first 10
                        print(f"    - {issue['type']}: {issue.get('description', '')}")
            return

        # Handle stats request
        if self.args.stats:
            stats = history.get_stats()
            if self.args.format == "json":
                print(json.dumps(stats, indent=2, default=str))
            else:
                print("Message History Statistics:")
                print(f"  Total messages: {stats['total_messages']}")
                print(f"  Max entries: {stats['max_entries']}")
                print(f"  Unique users: {stats['unique_users']}")
                print(f"  Unique chats: {stats['unique_chats']}")
                print("\nBy Platform:")
                for platform, count in stats["by_platform"].items():
                    print(f"  {platform}: {count}")
                print("\nBy Type:")
                for msg_type, count in stats["by_type"].items():
                    print(f"  {msg_type}: {count}")
            return

        # Default: Get messages
        messages = history.get_messages(
            user_id=self.args.user_id,
            chat_id=self.args.chat_id,
            platform=self.args.platform,
            message_type=self.args.message_type,
            limit=self.args.limit or 50,
        )

        if not messages:
            print("No messages found matching criteria.")
            return

        if self.args.format == "json":
            # Output as JSON
            output = []
            for msg in messages:
                output.append(
                    {
                        "timestamp": msg.timestamp.isoformat(),
                        "platform": msg.platform,
                        "user_id": msg.user_id,
                        "chat_id": msg.chat_id,
                        "message_content": msg.message_content,
                        "message_type": msg.message_type,
                        "message_id": msg.message_id,
                        "raw_text": msg.raw_text,
                        "formatted_text": msg.formatted_text,
                        "rendering_metadata": msg.rendering_metadata,
                    }
                )
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
                print(
                    f"{msg.message_content[:500]}{'...' if len(msg.message_content) > 500 else ''}"
                )
                if msg.raw_text and msg.raw_text != msg.message_content:
                    print(f"\nRaw Text ({len(msg.raw_text)} chars):")
                    print(
                        f"{msg.raw_text[:500]}{'...' if len(msg.raw_text) > 500 else ''}"
                    )
                if msg.formatted_text and msg.formatted_text != msg.message_content:
                    print(f"\nFormatted Text ({len(msg.formatted_text)} chars):")
                    print(
                        f"{msg.formatted_text[:500]}{'...' if len(msg.formatted_text) > 500 else ''}"
                    )
                if msg.rendering_metadata:
                    print(f"\nRendering Metadata:")
                    for key, value in msg.rendering_metadata.items():
                        print(f"  {key}: {value}")
                print()

    def cleanup(self) -> None:
        """Cleanup resources."""
        pass
