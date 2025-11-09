"""
File operation tools for reading and writing files.
"""

import logging
from pathlib import Path
from typing import Dict, Any

from june_agent_tools.tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class ReadFileTool(Tool):
    """Tool for reading file contents with path validation."""
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return "Read file contents safely with path validation"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file to read"
                }
            },
            "required": ["file_path"]
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate file path parameter."""
        if "file_path" not in params:
            return False
        file_path = params["file_path"]
        if not isinstance(file_path, str) or not file_path.strip():
            return False
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Read file contents."""
        file_path = Path(params["file_path"])
        
        try:
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {file_path}"
                )
            
            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is not a file: {file_path}"
                )
            
            content = file_path.read_text(encoding="utf-8")
            
            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "file_path": str(file_path),
                    "file_size": len(content),
                    "lines": len(content.splitlines())
                }
            )
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error reading file: {str(e)}"
            )


class WriteFileTool(Tool):
    """Tool for writing file contents with path validation."""
    
    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "Write file contents safely with path validation"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file to write"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to file"
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "Create parent directories if they don't exist",
                    "default": True
                }
            },
            "required": ["file_path", "content"]
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate file path and content parameters."""
        if "file_path" not in params or "content" not in params:
            return False
        file_path = params["file_path"]
        content = params["content"]
        if not isinstance(file_path, str) or not file_path.strip():
            return False
        if not isinstance(content, str):
            return False
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Write file contents."""
        file_path = Path(params["file_path"])
        content = params["content"]
        create_dirs = params.get("create_dirs", True)
        
        try:
            # Create parent directories if needed
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            file_path.write_text(content, encoding="utf-8")
            
            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(content)} characters to {file_path}",
                metadata={
                    "file_path": str(file_path),
                    "bytes_written": len(content.encode("utf-8")),
                    "lines_written": len(content.splitlines())
                }
            )
        except Exception as e:
            logger.error(f"Error writing file {file_path}: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error writing file: {str(e)}"
            )
