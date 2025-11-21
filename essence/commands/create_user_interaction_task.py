"""
Command to create a todorama task for a user interaction.

This command is called by Telegram/Discord services when they receive messages
from owner users, replacing the previous USER_MESSAGES.md file-based approach.
"""
import argparse
import logging
import os
import sys

from essence.command import Command

logger = logging.getLogger(__name__)


class CreateUserInteractionTaskCommand(Command):
    """
    Command to create a todorama task for a user interaction.
    
    This replaces the USER_MESSAGES.md file-based approach with todorama task management.
    """

    @classmethod
    def get_name(cls) -> str:
        """Get the command name."""
        return "create-user-interaction-task"

    @classmethod
    def get_description(cls) -> str:
        """Get the command description."""
        return "Create a todorama task for a user interaction (Telegram/Discord)"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """Add command-line arguments."""
        parser.add_argument(
            "--user-id",
            type=str,
            required=True,
            help="User ID",
        )
        parser.add_argument(
            "--chat-id",
            type=str,
            required=True,
            help="Chat/channel ID",
        )
        parser.add_argument(
            "--platform",
            type=str,
            required=True,
            choices=["telegram", "discord"],
            help="Platform (telegram or discord)",
        )
        parser.add_argument(
            "--content",
            type=str,
            required=True,
            help="Message content",
        )
        parser.add_argument(
            "--message-id",
            type=str,
            help="Optional platform message ID",
        )
        parser.add_argument(
            "--username",
            type=str,
            help="Optional username",
        )
        parser.add_argument(
            "--project-id",
            type=int,
            default=int(os.getenv("TODORAMA_PROJECT_ID", "1")),
            help="Todorama project ID (default: 1)",
        )

    def run(self) -> None:
        """Run the command to create a todorama task."""
        args = self.args
        
        # Format task title
        username_str = f"@{args.username} " if args.username else ""
        title = f"User Interaction: {args.platform.capitalize()} - {username_str}({args.user_id})"
        
        # Format task instruction with full context
        instruction = f"""User message from {args.platform.capitalize()}:
- User: {username_str}(user_id: {args.user_id})
- Chat ID: {args.chat_id}
- Message ID: {args.message_id or 'N/A'}
- Platform: {args.platform.capitalize()}
- Content: {args.content}

Please process this user interaction and respond appropriately."""
        
        verification = f"""Verify response by:
1. Agent has processed the user message
2. Agent has sent a response via {args.platform.capitalize()}
3. Task can be marked as complete"""
        
        # Create task via MCP todorama
        # We'll write to a queue file that the agent loop will process
        # The agent loop has access to MCP todorama and will create the actual tasks
        try:
            import json
            from pathlib import Path
            
            # Create queue file path
            data_dir = os.getenv("JUNE_DATA_DIR", "/home/rlee/june_data")
            task_queue_file = Path(f"{data_dir}/var-data/user_interaction_tasks.jsonl")
            
            # Ensure directory exists
            task_queue_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Append task to queue file (JSONL format)
            task_data = {
                "user_id": args.user_id,
                "chat_id": args.chat_id,
                "platform": args.platform,
                "content": args.content,
                "message_id": args.message_id,
                "username": args.username,
                "title": title,
                "instruction": instruction,
                "verification": verification,
                "project_id": args.project_id,
            }
            
            with open(task_queue_file, "a") as f:
                f.write(json.dumps(task_data) + "\n")
            
            logger.info(f"Added user interaction task to queue: {title}")
            print(f"Task queued: {title}")
            print(f"Queue file: {task_queue_file}")
            print("Note: The agent loop will process this queue and create todorama tasks.")
            
        except Exception as e:
            logger.error(f"Failed to create user interaction task: {e}", exc_info=True)
            print(f"ERROR: Failed to create user interaction task: {e}", file=sys.stderr)
            sys.exit(1)
