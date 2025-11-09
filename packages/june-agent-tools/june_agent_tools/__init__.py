"""
June Agent Tools - Tool system for code and git operations.

This package provides a comprehensive tool system that exposes code and git
operations as tools that agents can use to implement changes.
"""

from june_agent_tools.tool import Tool, ToolResult
from june_agent_tools.registry import ToolRegistry, register_tool, get_tool, list_tools, discover_tools
from june_agent_tools.executor import ToolExecutor

# Auto-register all tools on import
import june_agent_tools.tools  # noqa: F401

# Export execution tools
from june_agent_tools.execution import (
    SandboxEnvironment,
    ExecutePythonCodeTool,
    ExecuteShellCommandTool
)

__version__ = "0.1.0"

__all__ = [
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "register_tool",
    "get_tool",
    "list_tools",
    "discover_tools",
    "ToolExecutor",
    "SandboxEnvironment",
    "ExecutePythonCodeTool",
    "ExecuteShellCommandTool",
]
