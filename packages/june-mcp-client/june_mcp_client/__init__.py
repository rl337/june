"""
June MCP Client - Python client library for TODO MCP Service.

Provides a convenient interface for June agents to interact with the TODO MCP Service
using the Model Context Protocol (MCP) over JSON-RPC 2.0.
"""

from .client import (
    MCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPProtocolError,
    MCPServiceError
)
from .types import Task, TaskContext, AgentPerformance, Project

__all__ = [
    "MCPClient",
    "MCPClientError",
    "MCPConnectionError",
    "MCPProtocolError",
    "MCPServiceError",
    "Task",
    "TaskContext",
    "AgentPerformance",
    "Project",
]
__version__ = "0.1.0"
