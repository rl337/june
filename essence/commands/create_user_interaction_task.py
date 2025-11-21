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
        parser.add_argument(
            "--originator",
            type=str,
            help="User name/originator for the task (e.g., 'richard'). If not provided, will be determined from user_id",
        )

    def init(self) -> None:
        """Initialize the command"""
        pass

    def _get_user_name(self, user_id: str, platform: str) -> str:
        """Map user ID to user name. Owner users map to 'richard'."""
        from essence.chat.user_messages_sync import is_user_owner
        
        # Check if user is owner - owners are "richard"
        if is_user_owner(user_id, platform):
            return "richard"
        
        # For now, non-owner users use their user_id
        # Later, we can add a mapping for whitelisted users
        return f"user_{user_id}"
    
    def run(self) -> None:
        """Run the command to create a todorama task."""
        args = self.args
        
        # Determine originator/assignee
        if args.originator:
            user_name = args.originator
        else:
            user_name = self._get_user_name(args.user_id, args.platform)
        
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
        
        # Create task directly in todorama via HTTP API
        # This creates a human interaction task that the looping agent will process
        try:
            import requests
            import json
            
            # Get todorama service URL
            todo_service_url = os.getenv("TODO_SERVICE_URL", "http://todo-mcp-service:8004")
            if not todo_service_url.startswith("http"):
                todo_service_url = f"http://{todo_service_url}"
            
            # Get API key for authentication (if required)
            api_key = os.getenv("TODO_SERVICE_API_KEY") or os.getenv("TODORAMA_API_KEY")
            
            # Build task creation payload
            # Note: Todorama only supports "concrete", "abstract", "epic" for task_type
            # We use "concrete" and identify human_interface tasks by title pattern "User Interaction:"
            task_payload = {
                "project_id": args.project_id,
                "title": title,
                "description": instruction,
                "agent_type": "implementation",  # Agent type for the looping agent
                "task_type": "concrete",  # Use supported type - human_interface identified by title pattern
                "agent_id": "looping_agent",  # Agent that will work on this
                "originator": user_name,  # User who created the task
                "metadata": {
                    "interaction_type": "human_interface",  # Store intended type in metadata
                    "platform": args.platform,
                    "user_id": args.user_id,
                    "chat_id": args.chat_id,
                },
            }
            
            # Create task via HTTP API
            create_url = f"{todo_service_url}/tasks"
            logger.info(f"Creating todorama task via HTTP API: {title}")
            logger.debug(f"POST {create_url} with payload: {task_payload}")
            
            # Prepare headers with API key if available
            headers = {}
            if api_key:
                headers["X-API-Key"] = api_key
                logger.debug("Using API key for authentication")
            else:
                logger.warning("No API key found - request may fail if authentication is required")
            
            response = requests.post(
                create_url,
                json=task_payload,
                headers=headers,
                timeout=10,
            )
            
            if response.status_code in (200, 201):
                task_data = response.json()
                task_id = task_data.get("id") or task_data.get("task_id")
                logger.info(f"Successfully created todorama task: {title} (ID: {task_id})")
                
                # Output task details as JSON for the calling service to parse
                output_data = {
                    "success": True,
                    "task_id": task_id,
                    "task_data": task_data,
                }
                print(json.dumps(output_data))
            else:
                error_msg = response.text or f"HTTP {response.status_code}"
                logger.error(f"Failed to create todorama task: {error_msg}")
                output_data = {
                    "success": False,
                    "error": error_msg,
                }
                print(json.dumps(output_data))
                sys.exit(1)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request failed creating todorama task: {e}", exc_info=True)
            print(f"ERROR: HTTP request failed: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to create user interaction task: {e}", exc_info=True)
            print(f"ERROR: Failed to create user interaction task: {e}", file=sys.stderr)
            sys.exit(1)

    def cleanup(self) -> None:
        """Cleanup resources"""
        pass
