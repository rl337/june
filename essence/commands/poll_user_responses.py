"""
Command to poll for user responses to agent messages.

This command checks USER_REQUESTS.md for pending requests that are waiting
for user responses, and can be used by the looping agent for periodic polling.
"""
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from essence.chat.user_requests_sync import update_message_status
from essence.command import Command
from essence.commands.read_user_requests import UserRequest, parse_user_requests_file

logger = logging.getLogger(__name__)

# Path to USER_REQUESTS.md (in project root)
USER_REQUESTS_FILE = Path(__file__).parent.parent.parent / "USER_REQUESTS.md"

# Default timeout for waiting for user responses (in hours)
DEFAULT_RESPONSE_TIMEOUT_HOURS = 24


def check_for_user_responses(
    timeout_hours: float = DEFAULT_RESPONSE_TIMEOUT_HOURS,
) -> tuple[List[UserRequest], List[UserRequest]]:
    """
    Check for user responses to pending agent messages.

    This function looks for agent messages (clarification, help_request, etc.)
    that are waiting for user responses. It checks if there are newer user
    requests after the agent message, indicating the user has responded.

    Args:
        timeout_hours: Hours to wait before marking a request as timed out

    Returns:
        Tuple of (new_responses, timed_out_requests):
        - new_responses: List of agent messages that have received user responses
        - timed_out_requests: List of agent messages that have timed out
    """
    if not USER_REQUESTS_FILE.exists():
        return [], []

    # Parse all entries from USER_REQUESTS.md
    # We need to parse ALL entries (not just requests) to find agent messages
    import re

    from essence.chat.user_requests_sync import USER_REQUESTS_FILE as SYNC_FILE

    content = SYNC_FILE.read_text(encoding="utf-8")
    all_entries = []

    # Pattern to match all entries (requests and responses)
    pattern = r"## \[([^\]]+)\] (.+?)(?=\n## |\Z)"
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        timestamp = match.group(1)
        entry_text = match.group(2)
        message_type = entry_text.split("\n")[0].strip()

        # Extract fields
        user_id = None
        chat_id = None
        platform = None
        content_text = None
        message_id = None
        status = "Pending"

        for line in entry_text.split("\n"):
            line = line.strip()
            if line.startswith("- **User:**"):
                user_match = re.search(r"\(user_id: (\d+)\)", line)
                if user_match:
                    user_id = user_match.group(1)
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

        if user_id and content_text:
            all_entries.append(
                {
                    "timestamp": timestamp,
                    "user_id": str(user_id),
                    "chat_id": str(chat_id) if chat_id else "",
                    "platform": platform or "unknown",
                    "message_type": message_type,
                    "content": content_text,
                    "message_id": message_id,
                    "status": status,
                }
            )

    # Group entries by user_id and chat_id
    user_entries: dict[tuple[str, str], List[dict]] = {}
    for entry in all_entries:
        key = (str(entry["user_id"]), str(entry["chat_id"]))
        if key not in user_entries:
            user_entries[key] = []
        user_entries[key].append(entry)

    new_responses = []
    timed_out_requests = []
    timeout_threshold = datetime.now() - timedelta(hours=timeout_hours)

    # Agent message types that wait for user responses
    agent_waiting_types = ["Clarification", "Help Request", "Feedback Request"]

    # Check each user's entries for responses
    for (user_id, chat_id), entries in user_entries.items():
        # Sort by timestamp
        entries.sort(key=lambda e: e["timestamp"])

        # Find agent messages waiting for responses
        for i, entry in enumerate(entries):
            if (
                entry["status"] == "Pending"
                and entry["message_type"] in agent_waiting_types
            ):
                # This is an agent message waiting for user response
                # Check if there's a new user request after this agent message
                has_response = False
                for later_entry in entries[i + 1 :]:
                    if (
                        later_entry["user_id"] == user_id
                        and later_entry["chat_id"] == chat_id
                        and later_entry["message_type"] == "Request"
                        and later_entry["status"] == "Pending"
                    ):
                        # Found a new user request (user responded to agent)
                        has_response = True
                        # Convert to UserRequest for return
                        user_req = UserRequest(
                            timestamp=entry["timestamp"],
                            user_id=entry["user_id"],
                            chat_id=entry["chat_id"],
                            platform=entry["platform"],
                            message_type=entry["message_type"],
                            content=entry["content"],
                            message_id=entry["message_id"],
                            status=entry["status"],
                        )
                        new_responses.append(user_req)
                        # Update status
                        try:
                            update_message_status(
                                user_id=entry["user_id"],
                                message_id=entry["message_id"],
                                timestamp=entry["timestamp"],
                                new_status="Responded",
                            )
                        except Exception as e:
                            logger.warning(f"Failed to update message status: {e}")
                        break

                # Check for timeout if no response found
                if not has_response:
                    try:
                        request_time = datetime.strptime(
                            entry["timestamp"], "%Y-%m-%d %H:%M:%S"
                        )
                        if request_time < timeout_threshold:
                            # Convert to UserRequest for return
                            user_req = UserRequest(
                                timestamp=entry["timestamp"],
                                user_id=entry["user_id"],
                                chat_id=entry["chat_id"],
                                platform=entry["platform"],
                                message_type=entry["message_type"],
                                content=entry["content"],
                                message_id=entry["message_id"],
                                status=entry["status"],
                            )
                            timed_out_requests.append(user_req)
                            # Update status
                            try:
                                update_message_status(
                                    user_id=entry["user_id"],
                                    message_id=entry["message_id"],
                                    timestamp=entry["timestamp"],
                                    new_status="Timeout",
                                )
                            except Exception as e:
                                logger.warning(f"Failed to update timeout status: {e}")
                    except ValueError:
                        logger.warning(
                            f"Invalid timestamp format: {entry['timestamp']}"
                        )

    return new_responses, timed_out_requests


class PollUserResponsesCommand(Command):
    """Command to poll for user responses to agent messages"""

    @classmethod
    def get_name(cls) -> str:
        return "poll-user-responses"

    @classmethod
    def get_description(cls) -> str:
        return "Poll for user responses to pending agent messages in USER_REQUESTS.md"

    def init(self) -> None:
        """Initialize the command"""
        pass

    def run(self) -> None:
        """Poll for user responses"""
        # Get timeout from args if provided, otherwise use default
        timeout_hours = getattr(
            self.args, "timeout_hours", DEFAULT_RESPONSE_TIMEOUT_HOURS
        )

        new_responses, timed_out = check_for_user_responses(timeout_hours=timeout_hours)

        if not new_responses and not timed_out:
            print("No new responses or timeouts found.")
            return

        if new_responses:
            print(f"Found {len(new_responses)} new response(s):\n")
            for response in new_responses:
                print(f"  User {response.user_id} ({response.platform}):")
                print(
                    f"    Request: {response.content[:100]}{'...' if len(response.content) > 100 else ''}"
                )
                print(f"    Status: Updated to 'Responded'")
                print()

        if timed_out:
            print(f"Found {len(timed_out)} timed out request(s):\n")
            for timeout in timed_out:
                print(f"  User {timeout.user_id} ({timeout.platform}):")
                print(
                    f"    Request: {timeout.content[:100]}{'...' if len(timeout.content) > 100 else ''}"
                )
                print(
                    f"    Status: Updated to 'Timeout' (no response after {timeout_hours} hours)"
                )
                print()

    def cleanup(self) -> None:
        """Cleanup resources"""
        pass

    @classmethod
    def add_args(cls, parser) -> None:
        """Add command-specific arguments"""
        parser.add_argument(
            "--timeout-hours",
            type=float,
            default=DEFAULT_RESPONSE_TIMEOUT_HOURS,
            help=f"Hours to wait before marking a request as timed out (default: {DEFAULT_RESPONSE_TIMEOUT_HOURS})",
        )
