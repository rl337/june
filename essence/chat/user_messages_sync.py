"""
User Messages Synchronization

Handles syncing all messages between owner/whitelisted users and the looping agent to USER_MESSAGES.md.
Uses file locking (open/write/close) to minimize concurrent read/write issues.
"""
import logging
import os
import fcntl
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Path to USER_MESSAGES.md (in /var/data/ directory)
# Support environment variable for host testing (matches volume mount in docker-compose.yml)
# In containers: /var/data (volume mount)
# On host: ${JUNE_DATA_DIR}/var-data (volume mount path)
DATA_DIR_OVERRIDE = os.getenv("USER_MESSAGES_DATA_DIR")
if DATA_DIR_OVERRIDE:
    DATA_DIR = Path(DATA_DIR_OVERRIDE)
else:
    # Auto-detect: if /var/data/USER_MESSAGES.md exists, we're in a container
    # Otherwise, use host path
    default_container_path = Path("/var/data")
    june_data_dir = os.getenv("JUNE_DATA_DIR", "/home/rlee/june_data")
    default_host_path = Path(f"{june_data_dir}/var-data")
    
    # Check if we're in a container by checking if /var/data/USER_MESSAGES.md exists
    # or if /var/data exists and is a mount point (typical in containers)
    container_file = default_container_path / "USER_MESSAGES.md"
    if container_file.exists():
        # File exists in container path, we're in a container
        DATA_DIR = default_container_path
    elif default_container_path.exists() and default_container_path.is_dir():
        # Directory exists but file doesn't - could be container or host
        # Check if it's a mount point (more likely in containers)
        # For now, prefer host path if JUNE_DATA_DIR is set
        if june_data_dir != "/home/rlee/june_data" or default_host_path.exists():
            # JUNE_DATA_DIR is customized or host path exists, use host path
            DATA_DIR = default_host_path
            logger.debug(f"Using host path (JUNE_DATA_DIR set or host path exists): {DATA_DIR}")
        else:
            # Default to container path
            DATA_DIR = default_container_path
    else:
        # Running on host, use host path
        DATA_DIR = default_host_path
        logger.debug(f"Running on host, using host path: {DATA_DIR}")

# Try to create directory, but handle permission errors gracefully
# (TTS service doesn't need this directory, so it's OK if creation fails)
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError) as e:
    # Log warning but don't fail - some services (like TTS) don't need this directory
    logger.warning(f"Could not create {DATA_DIR} directory: {e}. This is OK for services that don't use USER_MESSAGES.md")
USER_MESSAGES_FILE = DATA_DIR / "USER_MESSAGES.md"


def get_owner_users(platform: str) -> List[str]:
    """
    Get list of owner user IDs (personal accounts for direct communication).

    Args:
        platform: Platform name ("telegram" or "discord")

    Returns:
        List of user IDs as strings
    """
    env_var = f"{platform.upper()}_OWNER_USERS"
    owner_str = os.getenv(env_var, "")
    if not owner_str:
        return []

    # Parse comma-separated user IDs
    user_ids = [uid.strip() for uid in owner_str.split(",") if uid.strip()]
    return user_ids


def get_whitelisted_users(platform: str) -> List[str]:
    """
    Get list of whitelisted user IDs (includes owners).

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


def is_user_owner(user_id: str, platform: str) -> bool:
    """
    Check if a user is an owner (personal account for direct communication).

    Args:
        user_id: User ID to check
        platform: Platform name ("telegram" or "discord")

    Returns:
        True if user is an owner, False otherwise
    """
    owners = get_owner_users(platform)
    return str(user_id) in owners


def is_user_whitelisted(user_id: str, platform: str) -> bool:
    """
    Check if a user is whitelisted (includes owners).

    Args:
        user_id: User ID to check
        platform: Platform name ("telegram" or "discord")

    Returns:
        True if user is whitelisted, False otherwise
    """
    whitelisted = get_whitelisted_users(platform)
    return str(user_id) in whitelisted


def append_message_to_user_messages(
    user_id: str,
    chat_id: str,
    platform: str,
    message_type: str,
    content: str,
    message_id: Optional[str] = None,
    status: str = "NEW",
    username: Optional[str] = None,
) -> bool:
    """
    Append a message to USER_MESSAGES.md with file locking.

    Uses open/write/close pattern with fcntl locking to minimize concurrent access issues.

    Args:
        user_id: User ID
        chat_id: Chat/channel ID
        platform: Platform ("telegram" or "discord")
        message_type: Type of message ("Request", "Response", etc.)
        content: Message content
        message_id: Optional platform message ID
        status: Message status ("NEW", "PROCESSING", "RESPONDED", etc.)
        username: Optional username (e.g., "@username")

    Returns:
        True if appended successfully, False otherwise
    """
    try:
        # Ensure file exists
        if not USER_MESSAGES_FILE.exists():
            _initialize_user_messages_file()

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

        # Open file with exclusive lock, append, and close
        # This minimizes concurrent read/write issues
        with open(USER_MESSAGES_FILE, "a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock
            try:
                f.write(entry)
                f.flush()  # Ensure data is written
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock

        logger.debug(
            f"Appended {message_type} message to USER_MESSAGES.md for user {user_id} (status: {status})"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to append message to USER_MESSAGES.md: {e}", exc_info=True)
        return False


def read_user_messages() -> str:
    """
    Read USER_MESSAGES.md with file locking.

    Returns:
        File content as string, or empty string if file doesn't exist or error occurs
    """
    try:
        if not USER_MESSAGES_FILE.exists():
            return ""

        # Open file with shared lock, read, and close
        with open(USER_MESSAGES_FILE, "r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock (allows multiple readers)
            try:
                content = f.read()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock

        return content

    except Exception as e:
        logger.error(f"Failed to read USER_MESSAGES.md: {e}", exc_info=True)
        return ""


def update_message_status(
    user_id: str,
    message_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    new_status: str = "PROCESSING",
) -> bool:
    """
    Update the status of a message in USER_MESSAGES.md with file locking.

    Args:
        user_id: User ID
        message_id: Optional message ID to match
        timestamp: Optional timestamp to match (format: "YYYY-MM-DD HH:MM:SS")
        new_status: New status ("NEW", "PROCESSING", "RESPONDED", etc.)

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        if not USER_MESSAGES_FILE.exists():
            logger.warning("USER_MESSAGES.md does not exist, cannot update status")
            return False

        # Read current content with lock
        content = read_user_messages()
        if not content:
            return False

        # Find and update the matching entry
        lines = content.split("\n")
        updated = False

        for i, line in enumerate(lines):
            # Look for status line
            if line.strip().startswith("- **Status:**"):
                # Check if this entry matches our criteria
                # Look backwards for user_id and optionally message_id/timestamp
                entry_start = max(0, i - 10)  # Look back up to 10 lines
                entry_lines = lines[entry_start : i + 1]
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
            # Write back with exclusive lock
            with open(USER_MESSAGES_FILE, "w", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock
                try:
                    f.write("\n".join(lines))
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock

            logger.debug(f"Updated message status to {new_status} for user {user_id}")
            return True
        else:
            logger.warning(
                f"Could not find matching message to update status for user {user_id}"
            )
            return False

    except Exception as e:
        logger.error(f"Failed to update message status in USER_MESSAGES.md: {e}", exc_info=True)
        return False


def _initialize_user_messages_file() -> None:
    """Initialize USER_MESSAGES.md with template if it doesn't exist."""
    template = """# User Messages and Agent Communication Log

This file tracks all direct communication between owner/whitelisted users and the looping agent.

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
- **Status:** NEW | PROCESSING | RESPONDED | ERROR
```

## Status Values

- **NEW**: Message just received, not yet processed by agent
- **PROCESSING**: Agent is currently processing this message
- **RESPONDED**: Agent has responded to this message
- **ERROR**: Error occurred while processing

## Communication Log

"""
    try:
        with open(USER_MESSAGES_FILE, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock
            try:
                f.write(template)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock
        logger.info(f"Initialized USER_MESSAGES.md at {USER_MESSAGES_FILE}")
    except Exception as e:
        logger.error(f"Failed to initialize USER_MESSAGES.md: {e}", exc_info=True)
        raise
