"""Agent implementations for switchboard."""

from switchboard.agents.base import Agent, AgentRequest, AgentResponse, AgentStatus
from switchboard.agents.popen_cursor import PopenCursorAgent

__all__ = [
    "Agent",
    "AgentRequest",
    "AgentResponse",
    "AgentStatus",
    "PopenCursorAgent",
]

