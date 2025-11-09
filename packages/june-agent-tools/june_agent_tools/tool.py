"""
Base tool interface and result types.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of a tool execution."""
    
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __bool__(self) -> bool:
        """ToolResult is truthy if success is True."""
        return self.success
    
    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILURE"
        return f"ToolResult({status}, output_length={len(self.output) if self.output else 0}, error={self.error})"


class Tool(ABC):
    """
    Base class for all agent tools.
    
    Tools provide operations that agents can use to:
    - Read/write files
    - Execute git operations
    - Run tests
    - Perform code analysis
    
    All tools must:
    1. Implement validate() to check parameters
    2. Implement execute() to perform the operation
    3. Provide name and description for discovery
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for discovery and documentation."""
        pass
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """
        JSON schema for tool parameters.
        
        Returns:
            Dict describing parameter types, requirements, etc.
        """
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    @abstractmethod
    def validate(self, params: Dict[str, Any]) -> bool:
        """
        Validate tool parameters before execution.
        
        Args:
            params: Tool parameters dictionary
            
        Returns:
            True if parameters are valid, False otherwise
        """
        pass
    
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the tool operation.
        
        Args:
            params: Tool parameters dictionary
            
        Returns:
            ToolResult with success status, output, and optional error
        """
        pass
    
    def can_handle(self, operation_type: str) -> bool:
        """
        Check if this tool can handle a specific operation type.
        
        Args:
            operation_type: Type of operation (e.g., "file_read", "git_commit")
            
        Returns:
            True if tool can handle the operation type
        """
        # Default implementation: check if operation_type is in tool name
        return operation_type.lower() in self.name.lower()
