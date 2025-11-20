"""
Command to read pending user requests from USER_REQUESTS.md.

This command is used by the looping agent to check for new requests from whitelisted users.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from essence.command import Command

logger = logging.getLogger(__name__)

# Path to USER_REQUESTS.md (in project root)
USER_REQUESTS_FILE = Path(__file__).parent.parent.parent / "USER_REQUESTS.md"


@dataclass
class UserRequest:
    """Represents a user request from USER_REQUESTS.md"""

    timestamp: str
    user_id: str
    chat_id: str
    platform: str
    message_type: str
    content: str
    message_id: Optional[str] = None
    status: str = "Pending"
    username: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "platform": self.platform,
            "message_type": self.message_type,
            "content": self.content,
            "message_id": self.message_id,
            "status": self.status,
            "username": self.username,
        }


def parse_user_requests_file(file_path: Path) -> List[UserRequest]:
    """
    Parse USER_REQUESTS.md and extract all requests.

    Args:
        file_path: Path to USER_REQUESTS.md

    Returns:
        List of UserRequest objects
    """
    if not file_path.exists():
        logger.warning(f"USER_REQUESTS.md not found at {file_path}")
        return []

    content = file_path.read_text(encoding="utf-8")
    requests = []

    # Pattern to match request entries
    # Format: ## [TIMESTAMP] Message Type
    pattern = r"## \[([^\]]+)\] (.+?)(?=\n## |\Z)"
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        timestamp = match.group(1)
        entry_text = match.group(2)

        # Extract fields from entry
        user_id = None
        chat_id = None
        platform = None
        message_type = (
            match.group(2).split("\n")[0].strip()
        )  # First line is message type
        content_text = None
        message_id = None
        status = "Pending"
        username = None

        # Parse entry fields
        for line in entry_text.split("\n"):
            line = line.strip()
            if line.startswith("- **User:**"):
                # Extract user_id and username
                user_match = re.search(r"\(user_id: (\d+)\)", line)
                if user_match:
                    user_id = user_match.group(1)
                username_match = re.search(r"@(\w+)", line)
                if username_match:
                    username = f"@{username_match.group(1)}"
            elif line.startswith("- **Platform:**"):
                platform = line.split(":", 1)[1].strip()
            elif line.startswith("- **Type:**"):
                message_type = line.split(":", 1)[1].strip()
            elif line.startswith("- **Content:**"):
                content_text = line.split(":", 1)[1].strip()
            elif line.startswith("- **Message ID:**"):
                message_id = line.split(":", 1)[1].strip()
            elif line.startswith("- **Chat ID:**"):
                chat_id = line.split(":", 1)[1].strip()
            elif line.startswith("- **Status:**"):
                status = line.split(":", 1)[1].strip()

        # Only include requests (not responses)
        if message_type == "Request" and user_id and content_text:
            requests.append(
                UserRequest(
                    timestamp=timestamp,
                    user_id=user_id,
                    chat_id=chat_id or "",
                    platform=platform or "unknown",
                    message_type=message_type,
                    content=content_text,
                    message_id=message_id,
                    status=status,
                    username=username,
                )
            )

    return requests


def get_pending_requests(file_path: Optional[Path] = None) -> List[UserRequest]:
    """
    Get all pending requests from USER_REQUESTS.md.

    Args:
        file_path: Optional path to USER_REQUESTS.md (defaults to project root)

    Returns:
        List of pending UserRequest objects
    """
    if file_path is None:
        file_path = USER_REQUESTS_FILE

    all_requests = parse_user_requests_file(file_path)
    pending = [req for req in all_requests if req.status == "Pending"]
    return pending


class ReadUserRequestsCommand(Command):
    """Command to read pending user requests from USER_REQUESTS.md"""

    @classmethod
    def get_name(cls) -> str:
        return "read-user-requests"

    @classmethod
    def get_description(cls) -> str:
        return "Read pending user requests from USER_REQUESTS.md"

    def init(self) -> None:
        """Initialize the command"""
        pass

    def run(self) -> None:
        """Read and display pending user requests"""
        pending = get_pending_requests()

        if not pending:
            print("No pending requests found in USER_REQUESTS.md")
            return

        print(f"Found {len(pending)} pending request(s):\n")

        for i, req in enumerate(pending, 1):
            print(f"Request {i}:")
            print(f"  Timestamp: {req.timestamp}")
            print(f"  User: {req.username or 'Unknown'} (ID: {req.user_id})")
            print(f"  Platform: {req.platform}")
            print(f"  Chat ID: {req.chat_id}")
            print(
                f"  Content: {req.content[:100]}{'...' if len(req.content) > 100 else ''}"
            )
            print(f"  Status: {req.status}")
            if req.message_id:
                print(f"  Message ID: {req.message_id}")
            print()

    def cleanup(self) -> None:
        """Cleanup resources"""
        pass
