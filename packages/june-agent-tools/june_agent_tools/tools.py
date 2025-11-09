"""
Auto-register all available tools.
"""

import logging
from june_agent_tools.registry import register_tool

# Import all tools
from june_agent_tools.code.file_tools import ReadFileTool, WriteFileTool
from june_agent_tools.git.git_tools import (
    GitStatusTool,
    GitCommitTool,
    GitPushTool,
    GitBranchTool,
    GitDiffTool
)
from june_agent_tools.testing.test_tools import RunTestsTool, ParseTestResultsTool
from june_agent_tools.testing.verification_tool import VerificationTool
from june_agent_tools.execution.code_execution_tools import (
    ExecutePythonCodeTool,
    ExecuteShellCommandTool
)

logger = logging.getLogger(__name__)


def register_all_tools() -> None:
    """
    Register all available tools with the global registry.
    
    This function should be called during initialization to make all tools
    available for discovery and execution.
    """
    # Code tools
    register_tool(ReadFileTool())
    register_tool(WriteFileTool())
    
    # Git tools
    register_tool(GitStatusTool())
    register_tool(GitCommitTool())
    register_tool(GitPushTool())
    register_tool(GitBranchTool())
    register_tool(GitDiffTool())
    
    # Testing tools
    register_tool(RunTestsTool())
    register_tool(ParseTestResultsTool())
    register_tool(VerificationTool())
    
    # Code execution tools
    register_tool(ExecutePythonCodeTool())
    register_tool(ExecuteShellCommandTool())
    
    logger.info("All tools registered successfully")


# Auto-register on import
try:
    register_all_tools()
except Exception as e:
    logger.error(f"Failed to register tools: {e}", exc_info=True)
