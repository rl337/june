"""Shared base for chat services (Telegram, Discord, etc.)"""

from essence.chat.interaction import setup_agent_message_endpoint, setup_health_endpoint

__all__ = [
    "setup_agent_message_endpoint",
    "setup_health_endpoint",
]
