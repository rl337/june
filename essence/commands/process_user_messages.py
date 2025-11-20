"""
Command to process NEW messages from USER_MESSAGES.md.

Reads messages with status "NEW", processes them, generates responses,
sends via Message API, and updates status accordingly.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from essence.command import Command
from essence.chat.user_messages_sync import (
    read_user_messages,
    update_message_status,
)

logger = logging.getLogger(__name__)


@dataclass
class UserMessage:
    """Represents a message from USER_MESSAGES.md"""

    timestamp: str
    message_type: str
    user_id: str
    chat_id: str
    platform: str
    content: str
    message_id: Optional[str] = None
    username: Optional[str] = None
    status: str = "NEW"
    raw_entry: str = ""  # Full markdown entry for status updates


def parse_user_messages_file(file_path: Path) -> List[UserMessage]:
    """
    Parse USER_MESSAGES.md and extract all messages.

    Args:
        file_path: Path to USER_MESSAGES.md

    Returns:
        List of UserMessage objects
    """
    messages = []

    if not file_path.exists():
        logger.warning(f"USER_MESSAGES.md not found at {file_path}")
        return messages

    content = read_user_messages()
    if not content:
        return messages

    # Split by message headers (## [TIMESTAMP] Message Type)
    # Pattern: ## [YYYY-MM-DD HH:MM:SS] MessageType
    message_pattern = r"^## \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+)$"

    entries = re.split(message_pattern, content, flags=re.MULTILINE)

    # Process entries (pattern returns groups + text between)
    # entries[0] = text before first match
    # entries[1] = timestamp, entries[2] = message_type, entries[3] = text until next match
    # entries[4] = next timestamp, etc.
    i = 1  # Start after initial text
    while i < len(entries) - 2:
        timestamp = entries[i].strip()
        message_type = entries[i + 1].strip()
        entry_text = entries[i + 2] if i + 2 < len(entries) else ""

        # Parse entry fields
        user_id = None
        chat_id = None
        platform = None
        content = None
        message_id = None
        username = None
        status = "NEW"

        # Extract fields from entry text
        user_match = re.search(r"- \*\*User:\*\* (.+?) \(user_id: (\d+)\)", entry_text)
        if user_match:
            username = user_match.group(1).strip().replace("@", "")
            user_id = user_match.group(2).strip()

        platform_match = re.search(r"- \*\*Platform:\*\* (.+)", entry_text)
        if platform_match:
            platform = platform_match.group(1).strip()

        content_match = re.search(r"- \*\*Content:\*\* (.+?)(?:\n- \*\*|$)", entry_text, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()

        message_id_match = re.search(r"- \*\*Message ID:\*\* (.+)", entry_text)
        if message_id_match:
            message_id = message_id_match.group(1).strip()

        chat_id_match = re.search(r"- \*\*Chat ID:\*\* (.+)", entry_text)
        if chat_id_match:
            chat_id = chat_id_match.group(1).strip()

        status_match = re.search(r"- \*\*Status:\*\* (.+)", entry_text)
        if status_match:
            status = status_match.group(1).strip()

        if user_id and content:
            messages.append(
                UserMessage(
                    timestamp=timestamp,
                    message_type=message_type,
                    user_id=user_id,
                    chat_id=chat_id or "",
                    platform=platform or "",
                    content=content,
                    message_id=message_id,
                    username=username,
                    status=status,
                    raw_entry=entry_text,
                )
            )

        i += 3  # Move to next entry

    return messages


def get_new_messages(file_path: Optional[Path] = None) -> List[UserMessage]:
    """
    Get all NEW messages from USER_MESSAGES.md.

    Args:
        file_path: Optional path to USER_MESSAGES.md (defaults to /var/data/USER_MESSAGES.md)

    Returns:
        List of UserMessage objects with status "NEW"
    """
    from essence.chat.user_messages_sync import USER_MESSAGES_FILE

    if file_path is None:
        file_path = USER_MESSAGES_FILE

    all_messages = parse_user_messages_file(file_path)
    new_messages = [msg for msg in all_messages if msg.status == "NEW"]

    logger.info(f"Found {len(new_messages)} NEW messages out of {len(all_messages)} total")
    return new_messages


class ProcessUserMessagesCommand(Command):
    """
    Command to process NEW messages from USER_MESSAGES.md.

    Reads messages with status "NEW", processes them, generates responses,
    sends via Message API, and updates status accordingly.
    """

    @classmethod
    def get_name(cls) -> str:
        """Get the command name."""
        return "process-user-messages"

    @classmethod
    def get_description(cls) -> str:
        """Get the command description."""
        return "Process NEW messages from USER_MESSAGES.md and send responses via Message API"

    def init(self) -> None:
        """Initialize the command."""
        logger.info("Initializing process-user-messages command")

    def run(self) -> None:
        """Run the command to process NEW messages."""
        from essence.chat.message_api_client import send_message_via_api

        logger.info("Processing NEW messages from USER_MESSAGES.md")

        # Get NEW messages
        new_messages = get_new_messages()

        if not new_messages:
            logger.info("No NEW messages to process")
            print("No NEW messages found in USER_MESSAGES.md")
            return

        logger.info(f"Processing {len(new_messages)} NEW messages")

        processed_count = 0
        error_count = 0

        for message in new_messages:
            try:
                logger.info(
                    f"Processing message from user {message.user_id} on {message.platform}: {message.content[:100]}"
                )

                # Update status to PROCESSING
                update_message_status(
                    user_id=message.user_id,
                    message_id=message.message_id,
                    timestamp=message.timestamp,
                    new_status="PROCESSING",
                )

                # Generate response (placeholder for now - will use LLM when inference engines are running)
                # TODO: When inference engines are running, generate actual response using LLM
                response_text = (
                    f"✅ I received your message: '{message.content[:100]}...'\n\n"
                    f"I'm currently processing it. When inference engines are running, "
                    f"I'll generate a proper response using the LLM."
                )

                # Send response via Message API
                try:
                    result = send_message_via_api(
                        user_id=message.user_id,
                        chat_id=message.chat_id,
                        message=response_text,
                        platform=message.platform.lower(),
                        message_type="text",
                    )

                    if result.get("success"):
                        # Update status to RESPONDED
                        update_message_status(
                            user_id=message.user_id,
                            message_id=message.message_id,
                            timestamp=message.timestamp,
                            new_status="RESPONDED",
                        )
                        logger.info(
                            f"Successfully processed and responded to message from user {message.user_id}"
                        )
                        processed_count += 1
                    else:
                        error_msg = result.get("error", "Unknown error")
                        logger.error(
                            f"Failed to send response via Message API: {error_msg}"
                        )
                        # Update status to ERROR
                        update_message_status(
                            user_id=message.user_id,
                            message_id=message.message_id,
                            timestamp=message.timestamp,
                            new_status="ERROR",
                        )
                        error_count += 1

                except Exception as api_error:
                    logger.error(
                        f"Error sending response via Message API: {api_error}",
                        exc_info=True,
                    )
                    # Update status to ERROR
                    update_message_status(
                        user_id=message.user_id,
                        message_id=message.message_id,
                        timestamp=message.timestamp,
                        new_status="ERROR",
                    )
                    error_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing message from user {message.user_id}: {e}",
                    exc_info=True,
                )
                # Update status to ERROR
                try:
                    update_message_status(
                        user_id=message.user_id,
                        message_id=message.message_id,
                        timestamp=message.timestamp,
                        new_status="ERROR",
                    )
                except Exception as update_error:
                    logger.error(
                        f"Failed to update message status to ERROR: {update_error}"
                    )
                error_count += 1

        # Summary
        logger.info(
            f"Processing complete: {processed_count} processed, {error_count} errors"
        )
        print(f"\n✅ Processed {processed_count} messages successfully")
        if error_count > 0:
            print(f"❌ {error_count} messages had errors")

    def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("Cleaning up process-user-messages command")
