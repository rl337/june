"""
Tool registry for discovering and managing tools.
"""

import logging
from typing import Dict, List, Optional, Type, Any
from june_agent_tools.tool import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all available tools.
    
    Features:
    - Register and discover tools
    - Query tools by capability
    - Validate tool parameters
    """
    
    def __init__(self):
        """Initialize empty tool registry."""
        self._tools: Dict[str, Tool] = {}
        logger.debug("ToolRegistry initialized")
    
    def register(self, tool: Tool) -> None:
        """
        Register a tool instance.
        
        Args:
            tool: Tool instance to register
            
        Raises:
            ValueError: If tool with same name already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} - {tool.description}")
    
    def get(self, tool_name: str) -> Optional[Tool]:
        """
        Get a tool by name.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(tool_name)
    
    def list(self) -> List[Tool]:
        """
        List all registered tools.
        
        Returns:
            List of all registered tool instances
        """
        return list(self._tools.values())
    
    def list_by_capability(self, capability: str) -> List[Tool]:
        """
        List tools that can handle a specific capability.
        
        Args:
            capability: Capability name (e.g., "file_read", "git_commit")
            
        Returns:
            List of tools that can handle the capability
        """
        return [
            tool for tool in self._tools.values()
            if tool.can_handle(capability)
        ]
    
    def discover(self) -> Dict[str, Dict[str, Any]]:
        """
        Discover all tools and return metadata.
        
        Returns:
            Dictionary mapping tool names to metadata (description, schema, etc.)
        """
        return {
            name: {
                "name": name,
                "description": tool.description,
                "parameters_schema": tool.parameters_schema
            }
            for name, tool in self._tools.items()
        }
    
    def clear(self) -> None:
        """Clear all registered tools (useful for testing)."""
        self._tools.clear()
        logger.debug("Tool registry cleared")


# Global tool registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.
    
    Returns:
        Global ToolRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_tool(tool: Tool) -> None:
    """
    Register a tool with the global registry.
    
    Args:
        tool: Tool instance to register
    """
    get_registry().register(tool)


def get_tool(tool_name: str) -> Optional[Tool]:
    """
    Get a tool by name from the global registry.
    
    Args:
        tool_name: Name of the tool
        
    Returns:
        Tool instance or None if not found
    """
    return get_registry().get(tool_name)


def list_tools() -> List[Tool]:
    """
    List all registered tools.
    
    Returns:
        List of all registered tool instances
    """
    return get_registry().list()


def discover_tools() -> Dict[str, Dict[str, Any]]:
    """
    Discover all tools and return metadata.
    
    Returns:
        Dictionary mapping tool names to metadata
    """
    return get_registry().discover()
