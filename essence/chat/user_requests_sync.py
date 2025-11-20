"""
User Requests Synchronization

Handles syncing all messages between whitelisted users and the looping agent to USER_REQUESTS.md.
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Path to USER_REQUESTS.md (in project root)
USER_REQUESTS_FILE = Path(__file__).parent.parent.parent / "USER_REQUESTS.md"


def get_whitelisted_users(platform: str) -> List[str]:
    """
    Get list of whitelisted user IDs for direct agent communication.

    Args:
        platform: Platform name ("telegram" or "discord")

    Returns:
        List of user IDs as strings
    """
    env_var = f"{platform.upper()}_WHITELISTED_USERS"
    whitelist_str = os.getenv(env_var, "")
    if not whitelist_str:
        return []

    # Parse comma-separated user IDs
    user_ids = [uid.strip() for uid in whitelist_str.split(",") if uid.strip()]
    return user_ids


def is_user_whitelisted(user_id: str, platform: str) -> bool:
    """
    Check if a user is whitelisted for direct agent communication.

    Args:
        user_id: User ID to check
        platform: Platform name ("telegram" or "discord")

    Returns:
        True if user is whitelisted, False otherwise
    """
    whitelisted = get_whitelisted_users(platform)
    return str(user_id) in whitelisted


def sync_message_to_user_requests(
    user_id: str,
    chat_id: str,
    platform: str,
    message_type: str,
    content: str,
    message_id: Optional[str] = None,
    status: str = "Pending",
    username: Optional[str] = None,
) -> bool:
    """
    Sync a message to USER_REQUESTS.md.

    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        platform: Platform ("telegram" or "discord")
        message_type: Type of message ("Request", "Response", "Clarification", "Help Request", "Progress Update")
        content: Message content
        message_id: Optional platform message ID
        status: Message status ("Pending", "Responded", "Timeout")
        username: Optional username (e.g., "@username")

    Returns:
        True if synced successfully, False otherwise
    """
    try:
        # Ensure file exists
        if not USER_REQUESTS_FILE.exists():
            _initialize_user_requests_file()

        # Read current content
        current_content = USER_REQUESTS_FILE.read_text(encoding="utf-8")

        # Format new entry
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        username_str = f"@{username} " if username else ""
        message_id_str = f"\n- **Message ID:** {message_id}" if message_id else ""
        chat_id_str = f"\n- **Chat ID:** {chat_id}" if chat_id else ""

        entry = f"""
## [{timestamp}] {message_type}
- **User:** {username_str}(user_id: {user_id})
- **Platform:** {platform.capitalize()}
- **Type:** {message_type}
- **Content:** {content}
{message_id_str}{chat_id_str}
- **Status:** {status}

"""

        # Append to file (before the "<!-- Messages will be synced here automatically -->" comment)
        if "<!-- Messages will be synced here automatically -->" in current_content:
            new_content = current_content.replace(
                "<!-- Messages will be synced here automatically -->", entry + "<!-- Messages will be synced here automatically -->"
            )
        else:
            # If comment not found, append to end
            new_content = current_content.rstrip() + "\n" + entry

        # Write back to file
        USER_REQUESTS_FILE.write_text(new_content, encoding="utf-8")
        logger.debug(f"Synced {message_type} message to USER_REQUESTS.md for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to sync message to USER_REQUESTS.md: {e}")
        return False


def update_message_status(
    user_id: str,
    message_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    new_status: str = "Responded",
) -> bool:
    """
    Update the status of a message in USER_REQUESTS.md.

    Args:
        user_id: User ID
        message_id: Optional message ID to match
        timestamp: Optional timestamp to match (format: "YYYY-MM-DD HH:MM:SS")
        new_status: New status ("Pending", "Responded", "Timeout")

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        if not USER_REQUESTS_FILE.exists():
            logger.warning("USER_REQUESTS.md does not exist, cannot update status")
            return False

        content = USER_REQUESTS_FILE.read_text(encoding="utf-8")

        # Find and update the matching entry
        # Look for the entry with matching user_id and optionally message_id or timestamp
        lines = content.split("\n")
        updated = False

        for i, line in enumerate(lines):
            # Look for status line
            if line.strip().startswith("- **Status:**"):
                # Check if this entry matches our criteria
                # Look backwards for user_id and optionally message_id/timestamp
                entry_start = max(0, i - 10)  # Look back up to 10 lines
                entry_lines = lines[entry_start:i + 1]
                entry_text = "\n".join(entry_lines)

                # Check if this entry matches
                matches = True
                if user_id not in entry_text:
                    matches = False
                if message_id and message_id not in entry_text:
                    matches = False
                if timestamp and timestamp not in entry_text:
                    matches = False

                if matches:
                    # Update status
                    lines[i] = f"- **Status:** {new_status}"
                    updated = True
                    break

        if updated:
            USER_REQUESTS_FILE.write_text("\n".join(lines), encoding="utf-8")
            logger.debug(f"Updated message status to {new_status} for user {user_id}")
            return True
        else:
            logger.warning(f"Could not find matching message to update status for user {user_id}")
            return False

    except Exception as e:
        logger.error(f"Failed to update message status in USER_REQUESTS.md: {e}")
        return False


def _initialize_user_requests_file() -> None:
    """Initialize USER_REQUESTS.md with template if it doesn't exist."""
    template = """# User Requests and Agent Communication Log

This file tracks all direct communication between whitelisted users and the looping agent.

## Format

Each entry follows this structure:

```markdown
## [TIMESTAMP] Message Type
- **User:** @username (user_id: 123456789)
- **Platform:** Telegram | Discord
- **Type:** Request | Response | Clarification | Help Request | Progress Update
- **Content:** [message content]
- **Message ID:** [platform message ID]
- **Chat ID:** [platform chat/channel ID]
- **Status:** Pending | Responded | Timeout
```

## Communication Log

<!-- Messages will be synced here automatically -->

"""
    USER_REQUESTS_FILE.write_text(template, encoding="utf-8")
    logger.info(f"Initialized USER_REQUESTS.md at {USER_REQUESTS_FILE}")
