"""
Command to check service status for agent communication.

This command helps verify that Telegram/Discord services are stopped before
using agent-to-user communication to prevent race conditions.
"""
import logging
from typing import Dict, List

from essence.chat.agent_communication import (
    check_discord_service_running,
    check_telegram_service_running,
)
from essence.command import Command

logger = logging.getLogger(__name__)


class CheckServiceStatusCommand(Command):
    """Command to check service status for agent communication"""

    @classmethod
    def get_name(cls) -> str:
        return "check-service-status"

    @classmethod
    def get_description(cls) -> str:
        return "Check if Telegram/Discord services are running (must be stopped for agent communication)"

    def init(self) -> None:
        """Initialize the command"""
        pass

    def run(self) -> None:
        """Check and display service status"""
        telegram_running = check_telegram_service_running()
        discord_running = check_discord_service_running()

        print("Service Status Check for Agent Communication")
        print("=" * 50)
        print()

        # Check Telegram
        print("Telegram Service:")
        if telegram_running:
            print("  ❌ RUNNING - Must be stopped before agent communication")
            print("  → Run: docker compose stop telegram")
        else:
            print("  ✅ STOPPED - Safe for agent communication")
        print()

        # Check Discord
        print("Discord Service:")
        if discord_running:
            print("  ❌ RUNNING - Must be stopped before agent communication")
            print("  → Run: docker compose stop discord")
        else:
            print("  ✅ STOPPED - Safe for agent communication")
        print()

        # Summary
        if telegram_running or discord_running:
            print("⚠️  WARNING: One or more services are running.")
            print(
                "   Agent communication requires services to be stopped to prevent race conditions."
            )
            print()
            print("   Workflow:")
            print("   1. Stop services: docker compose stop telegram discord")
            print("   2. Use agent communication (send messages, read requests)")
            print(
                "   3. Restart services when done: docker compose start telegram discord"
            )
            return 1
        else:
            print("✅ All services are stopped. Safe to use agent communication.")
            return 0

    def cleanup(self) -> None:
        """Cleanup resources"""
        pass


def get_service_status() -> Dict[str, bool]:
    """
    Get status of all services relevant to agent communication.

    Returns:
        Dictionary with service status:
        - telegram: True if running, False if stopped
        - discord: True if running, False if stopped
    """
    return {
        "telegram": check_telegram_service_running(),
        "discord": check_discord_service_running(),
    }


def verify_services_stopped(platform: str = "auto") -> tuple[bool, List[str]]:
    """
    Verify that services are stopped for agent communication.

    Args:
        platform: Platform to check ("telegram", "discord", or "auto" for both)

    Returns:
        Tuple of (all_stopped, running_services):
        - all_stopped: True if all relevant services are stopped
        - running_services: List of service names that are running
    """
    running_services = []
    status = get_service_status()

    if platform == "auto" or platform == "telegram":
        if status["telegram"]:
            running_services.append("telegram")
    if platform == "auto" or platform == "discord":
        if status["discord"]:
            running_services.append("discord")

    all_stopped = len(running_services) == 0
    return all_stopped, running_services
