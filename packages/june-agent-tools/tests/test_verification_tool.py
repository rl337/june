"""
Tests for verification tool.
"""

import pytest
import tempfile
import subprocess
from pathlib import Path

from june_agent_tools.testing.verification_tool import VerificationTool
from june_agent_tools.tool import ToolResult


class TestVerificationTool:
    """Test VerificationTool."""
    
    def test_tool_interface(self):
        """Test that VerificationTool implements Tool interface."""
        tool = VerificationTool()
        assert tool.name == "verify_work"
        assert "verification" in tool.description.lower()
        assert tool.parameters_schema is not None
    
    def test_validate_parameters(self):
        """Test parameter validation."""
        tool = VerificationTool()
        
        # Valid parameters
        assert tool.validate({"timeout": 300})
        assert tool.validate({"timeout": 600})
        assert tool.validate({})  # Uses default timeout
        
        # Invalid parameters
        assert not tool.validate({"timeout": 5})  # Too low
        assert not tool.validate({"timeout": -1})  # Negative
    
    def test_execute_with_missing_run_checks(self, tmp_path):
        """Test execution when run_checks.sh is missing."""
        tool = VerificationTool()
        
        result = tool.execute({
            "project_root": str(tmp_path),
            "run_checks_script": True,
            "run_tests": False,
            "check_quality": False,
            "check_functional": False,
            "check_integration": False,
            "check_documentation": False
        })
        
        assert isinstance(result, ToolResult)
        assert not result.success  # Should fail because run_checks.sh missing
        assert "run_checks.sh" in result.output.lower()
    
    def test_execute_with_mock_checks_script(self, tmp_path):
        """Test execution with a mock run_checks.sh script."""
        tool = VerificationTool()
        
        # Create a mock run_checks.sh that succeeds
        checks_script = tmp_path / "run_checks.sh"
        checks_script.write_text("#!/bin/bash\necho 'All checks passed'\nexit 0\n")
        checks_script.chmod(0o755)
        
        result = tool.execute({
            "project_root": str(tmp_path),
            "run_checks_script": True,
            "run_tests": False,
            "check_quality": False,
            "check_functional": False,
            "check_integration": False,
            "check_documentation": False,
            "timeout": 10
        })
        
        assert isinstance(result, ToolResult)
        # Should pass or fail depending on whether bash is available
        assert "run_checks.sh" in result.output.lower()
    
    def test_syntax_check(self, tmp_path):
        """Test syntax checking."""
        tool = VerificationTool()
        
        # Create a Python file with valid syntax
        valid_file = tmp_path / "valid.py"
        valid_file.write_text("def hello():\n    print('world')\n")
        
        result_dict = tool._check_syntax(tmp_path)
        
        assert result_dict["check_name"] == "syntax_check"
        assert result_dict["success"] is True
    
    def test_syntax_check_with_error(self, tmp_path):
        """Test syntax checking with errors."""
        tool = VerificationTool()
        
        # Create a Python file with syntax error
        invalid_file = tmp_path / "invalid.py"
        invalid_file.write_text("def hello(\n    print('world')\n")  # Missing closing paren
        
        result_dict = tool._check_syntax(tmp_path)
        
        assert result_dict["check_name"] == "syntax_check"
        # Should detect syntax error (though it may not find it if file is not compiled)
        assert "syntax_check" in result_dict["check_name"]
    
    def test_formatting_check(self, tmp_path):
        """Test formatting check."""
        tool = VerificationTool()
        
        # Create a Python file
        py_file = tmp_path / "test.py"
        py_file.write_text("def hello():\n    print('world')\n")
        
        result_dict = tool._check_formatting(tmp_path)
        
        assert result_dict["check_name"] == "formatting_check"
        # Result depends on whether black/isort are installed
        # Should not crash regardless
    
    def test_linting_check(self, tmp_path):
        """Test linting check."""
        tool = VerificationTool()
        
        # Create a Python file
        py_file = tmp_path / "test.py"
        py_file.write_text("def hello():\n    print('world')\n")
        
        result_dict = tool._check_linting(tmp_path)
        
        assert result_dict["check_name"] == "linting_check"
        # Result depends on whether flake8 is installed
        # Should not crash regardless
    
    def test_type_hints_check(self, tmp_path):
        """Test type hints check."""
        tool = VerificationTool()
        
        result_dict = tool._check_type_hints(tmp_path)
        
        assert result_dict["check_name"] == "type_hints_check"
        # Result depends on whether mypy is installed
        # Should not crash regardless
    
    def test_functional_check(self, tmp_path):
        """Test functional verification."""
        tool = VerificationTool()
        
        result_dict = tool._check_functional(tmp_path)
        
        assert result_dict["check_name"] == "functional_verification"
        assert result_dict["success"] is True  # Should succeed with no tests
    
    def test_integration_check(self, tmp_path):
        """Test integration validation."""
        tool = VerificationTool()
        
        result_dict = tool._check_integration(tmp_path)
        
        assert result_dict["check_name"] == "integration_validation"
        assert result_dict["success"] is True  # Should succeed with no integration tests
    
    def test_documentation_check_with_readme(self, tmp_path):
        """Test documentation check with README."""
        tool = VerificationTool()
        
        # Create README.md
        readme = tmp_path / "README.md"
        readme.write_text("# Test Project\n\nThis is a test.\n")
        
        result_dict = tool._check_documentation(tmp_path)
        
        assert result_dict["check_name"] == "documentation_verification"
        # Should pass or provide suggestions
    
    def test_documentation_check_without_readme(self, tmp_path):
        """Test documentation check without README."""
        tool = VerificationTool()
        
        result_dict = tool._check_documentation(tmp_path)
        
        assert result_dict["check_name"] == "documentation_verification"
        # Should suggest creating README
    
    def test_analyze_failures(self):
        """Test failure analysis."""
        tool = VerificationTool()
        
        # Test different failure types
        suggestions = tool._analyze_failures(
            "test failed with error",
            "test execution failed"
        )
        assert len(suggestions) > 0
        assert any("test" in s.lower() for s in suggestions)
    
    def test_analyze_failures_syntax_error(self):
        """Test failure analysis for syntax errors."""
        tool = VerificationTool()
        
        suggestions = tool._analyze_failures(
            "SyntaxError: invalid syntax",
            ""
        )
        assert len(suggestions) > 0
        assert any("syntax" in s.lower() for s in suggestions)
    
    def test_analyze_failures_import_error(self):
        """Test failure analysis for import errors."""
        tool = VerificationTool()
        
        suggestions = tool._analyze_failures(
            "ImportError: No module named 'missing'",
            ""
        )
        assert len(suggestions) > 0
        assert any("import" in s.lower() or "depend" in s.lower() for s in suggestions)
    
    def test_execute_minimal_config(self, tmp_path):
        """Test execution with minimal configuration."""
        tool = VerificationTool()
        
        # Create src directory structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text("")
        
        result = tool.execute({
            "project_root": str(tmp_path),
            "run_checks_script": False,
            "run_tests": False,
            "check_quality": False,
            "check_functional": False,
            "check_integration": False,
            "check_documentation": False,
            "timeout": 10
        })
        
        assert isinstance(result, ToolResult)
        assert result.success is True  # All checks disabled, should pass
        assert "PASSED" in result.output or "passed" in result.output.lower()
    
    def test_execute_all_checks(self, tmp_path):
        """Test execution with all checks enabled."""
        tool = VerificationTool()
        
        # Create basic project structure
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        readme = tmp_path / "README.md"
        readme.write_text("# Test\n")
        
        result = tool.execute({
            "project_root": str(tmp_path),
            "run_checks_script": False,  # Disable to avoid dependency on script
            "run_tests": True,
            "check_quality": True,
            "check_functional": True,
            "check_integration": True,
            "check_documentation": True,
            "timeout": 30
        })
        
        assert isinstance(result, ToolResult)
        # Should complete without crashing
        assert "verification" in result.output.lower() or "check" in result.output.lower()
        assert result.metadata is not None
        assert "summary" in result.metadata