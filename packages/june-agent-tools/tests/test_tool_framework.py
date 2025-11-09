"""
Tests for tool framework (base classes, registry, executor).
"""

import pytest
import tempfile
from pathlib import Path

from june_agent_tools.tool import Tool, ToolResult
from june_agent_tools.registry import ToolRegistry, register_tool, get_tool, list_tools, discover_tools
from june_agent_tools.code.file_tools import ReadFileTool, WriteFileTool


class TestTool:
    """Test base Tool class."""
    
    def test_tool_interface(self):
        """Test that Tool is an abstract base class."""
        # Cannot instantiate Tool directly
        with pytest.raises(TypeError):
            Tool()


class TestToolRegistry:
    """Test ToolRegistry."""
    
    def test_register_and_get_tool(self):
        """Test registering and retrieving tools."""
        registry = ToolRegistry()
        
        tool = ReadFileTool()
        registry.register(tool)
        
        retrieved = registry.get("read_file")
        assert retrieved is not None
        assert retrieved.name == "read_file"
    
    def test_register_duplicate_tool(self):
        """Test that registering duplicate tool names raises error."""
        registry = ToolRegistry()
        
        tool1 = ReadFileTool()
        tool2 = ReadFileTool()
        
        registry.register(tool1)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool2)
    
    def test_list_tools(self):
        """Test listing all tools."""
        registry = ToolRegistry()
        
        tool1 = ReadFileTool()
        tool2 = WriteFileTool()
        
        registry.register(tool1)
        registry.register(tool2)
        
        tools = registry.list()
        assert len(tools) == 2
        assert tool1 in tools
        assert tool2 in tools
    
    def test_discover_tools(self):
        """Test tool discovery returns metadata."""
        registry = ToolRegistry()
        
        tool = ReadFileTool()
        registry.register(tool)
        
        metadata = registry.discover()
        assert "read_file" in metadata
        assert metadata["read_file"]["name"] == "read_file"
        assert "description" in metadata["read_file"]
        assert "parameters_schema" in metadata["read_file"]


class TestGlobalRegistry:
    """Test global registry functions."""
    
    def test_register_tool(self):
        """Test global register_tool function."""
        # Get a fresh registry
        from june_agent_tools.registry import get_registry
        registry = get_registry()
        registry.clear()
        
        tool = ReadFileTool()
        register_tool(tool)
        
        retrieved = get_tool("read_file")
        assert retrieved is not None
        assert retrieved.name == "read_file"
    
    def test_list_tools(self):
        """Test global list_tools function."""
        from june_agent_tools.registry import get_registry
        registry = get_registry()
        registry.clear()
        
        tool1 = ReadFileTool()
        tool2 = WriteFileTool()
        register_tool(tool1)
        register_tool(tool2)
        
        tools = list_tools()
        assert len(tools) >= 2
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names


class TestReadFileTool:
    """Test ReadFileTool."""
    
    def test_read_file_success(self):
        """Test successfully reading a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Hello, World!")
            
            tool = ReadFileTool()
            
            # Validate
            assert tool.validate({"file_path": str(test_file)})
            
            # Execute
            result = tool.execute({"file_path": str(test_file)})
            
            assert result.success
            assert "Hello, World!" in result.output
            assert result.metadata is not None
            assert "file_path" in result.metadata
    
    def test_read_file_not_found(self):
        """Test reading non-existent file."""
        tool = ReadFileTool()
        
        result = tool.execute({"file_path": "/nonexistent/file.txt"})
        
        assert not result.success
        assert "not found" in result.error.lower()
    
    def test_validate_invalid_params(self):
        """Test parameter validation."""
        tool = ReadFileTool()
        
        assert not tool.validate({})  # Missing file_path
        assert not tool.validate({"file_path": ""})  # Empty file_path
        assert tool.validate({"file_path": "valid/path.txt"})


class TestWriteFileTool:
    """Test WriteFileTool."""
    
    def test_write_file_success(self):
        """Test successfully writing a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            
            tool = WriteFileTool()
            
            # Validate
            assert tool.validate({
                "file_path": str(test_file),
                "content": "Test content"
            })
            
            # Execute
            result = tool.execute({
                "file_path": str(test_file),
                "content": "Test content"
            })
            
            assert result.success
            assert test_file.exists()
            assert test_file.read_text() == "Test content"
    
    def test_write_file_create_dirs(self):
        """Test writing file with directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "subdir" / "test.txt"
            
            tool = WriteFileTool()
            
            result = tool.execute({
                "file_path": str(test_file),
                "content": "Test",
                "create_dirs": True
            })
            
            assert result.success
            assert test_file.exists()
            assert test_file.read_text() == "Test"
    
    def test_validate_invalid_params(self):
        """Test parameter validation."""
        tool = WriteFileTool()
        
        assert not tool.validate({})  # Missing params
        assert not tool.validate({"file_path": "path.txt"})  # Missing content
        assert not tool.validate({"content": "content"})  # Missing file_path
        assert tool.validate({
            "file_path": "path.txt",
            "content": "content"
        })
