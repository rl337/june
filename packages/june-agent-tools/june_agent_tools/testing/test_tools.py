"""
Testing operation tools for executing tests and parsing results.
"""

import logging
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional, List

from june_agent_tools.tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class RunTestsTool(Tool):
    """Tool for executing tests (pytest, etc.) and capturing results."""
    
    @property
    def name(self) -> str:
        return "run_tests"
    
    @property
    def description(self) -> str:
        return "Execute tests (pytest) and return results"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "test_path": {
                    "type": "string",
                    "description": "Path to test file, directory, or test pattern",
                    "default": "tests/"
                },
                "test_runner": {
                    "type": "string",
                    "enum": ["pytest"],
                    "description": "Test runner to use",
                    "default": "pytest"
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional test runner options",
                    "default": []
                },
                "work_dir": {
                    "type": "string",
                    "description": "Working directory for test execution",
                    "default": "."
                },
                "capture_output": {
                    "type": "boolean",
                    "description": "Capture test output",
                    "default": True
                }
            },
            "required": []
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate test parameters."""
        test_runner = params.get("test_runner", "pytest")
        if test_runner not in ["pytest"]:
            return False
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute tests."""
        test_path = params.get("test_path", "tests/")
        test_runner = params.get("test_runner", "pytest")
        options = params.get("options", [])
        work_dir = Path(params.get("work_dir", ".")).resolve()
        capture_output = params.get("capture_output", True)
        
        try:
            if test_runner == "pytest":
                cmd = ["pytest", test_path] + options
                
                # Add JSON report for parsing
                if "--json-report" not in options and "-v" not in options:
                    cmd.extend(["-v", "--tb=short"])
                
                result = subprocess.run(
                    cmd,
                    cwd=work_dir,
                    capture_output=capture_output,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                # Parse pytest output
                exit_code = result.returncode
                stdout = result.stdout if result.stdout else ""
                stderr = result.stderr if result.stderr else ""
                
                # Try to extract summary from pytest output
                passed = 0
                failed = 0
                skipped = 0
                error = 0
                
                # Parse pytest output for test counts
                lines = stdout.splitlines()
                for line in lines:
                    if " passed" in line.lower():
                        try:
                            passed = int(line.split()[0])
                        except (ValueError, IndexError):
                            pass
                    if " failed" in line.lower():
                        try:
                            failed = int(line.split()[0])
                        except (ValueError, IndexError):
                            pass
                    if " skipped" in line.lower():
                        try:
                            skipped = int(line.split()[0])
                        except (ValueError, IndexError):
                            pass
                    if " error" in line.lower() and "ERRORS" in line:
                        try:
                            error = int(line.split()[0])
                        except (ValueError, IndexError):
                            pass
                
                success = exit_code == 0
                
                output_text = f"Test execution {'passed' if success else 'failed'}\n"
                output_text += f"Passed: {passed}, Failed: {failed}, Skipped: {skipped}, Errors: {error}\n"
                if stdout:
                    output_text += f"\nOutput:\n{stdout}"
                if stderr:
                    output_text += f"\nErrors:\n{stderr}"
                
                return ToolResult(
                    success=success,
                    output=output_text,
                    metadata={
                        "exit_code": exit_code,
                        "passed": passed,
                        "failed": failed,
                        "skipped": skipped,
                        "errors": error,
                        "test_runner": test_runner,
                        "test_path": test_path,
                        "stdout": stdout,
                        "stderr": stderr
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported test runner: {test_runner}"
                )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Test execution timed out (> 5 minutes)"
            )
        except Exception as e:
            logger.error(f"Error running tests: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error running tests: {str(e)}"
            )


class ParseTestResultsTool(Tool):
    """Tool for parsing test result files and extracting statistics."""
    
    @property
    def name(self) -> str:
        return "parse_test_results"
    
    @property
    def description(self) -> str:
        return "Parse test result files (JUnit XML, pytest JSON, etc.) and extract statistics"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "result_file": {
                    "type": "string",
                    "description": "Path to test result file"
                },
                "format": {
                    "type": "string",
                    "enum": ["junit-xml", "pytest-json", "auto"],
                    "description": "Result file format",
                    "default": "auto"
                }
            },
            "required": ["result_file"]
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate result file parameter."""
        if "result_file" not in params:
            return False
        result_file = params["result_file"]
        if not isinstance(result_file, str) or not result_file.strip():
            return False
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Parse test result file."""
        result_file = Path(params["result_file"])
        format_type = params.get("format", "auto")
        
        try:
            if not result_file.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Test result file not found: {result_file}"
                )
            
            # Auto-detect format
            if format_type == "auto":
                if result_file.suffix == ".xml":
                    format_type = "junit-xml"
                elif result_file.suffix == ".json":
                    format_type = "pytest-json"
                else:
                    # Try to detect from content
                    content = result_file.read_text(encoding="utf-8")[:100]
                    if content.strip().startswith("<"):
                        format_type = "junit-xml"
                    elif content.strip().startswith("{"):
                        format_type = "pytest-json"
                    else:
                        return ToolResult(
                            success=False,
                            output="",
                            error=f"Unable to auto-detect format for {result_file}"
                        )
            
            # Parse based on format
            if format_type == "junit-xml":
                tree = ET.parse(result_file)
                root = tree.getroot()
                
                # Extract test statistics
                total_tests = int(root.get("tests", 0))
                failures = int(root.get("failures", 0))
                errors = int(root.get("errors", 0))
                skipped = int(root.get("skipped", 0))
                
                passed = total_tests - failures - errors - skipped
                
                # Extract test cases
                test_cases = []
                for testcase in root.findall(".//testcase"):
                    test_cases.append({
                        "name": testcase.get("name"),
                        "classname": testcase.get("classname"),
                        "status": "passed" if not (testcase.find("failure") or testcase.find("error")) else "failed"
                    })
                
                summary = {
                    "total": total_tests,
                    "passed": passed,
                    "failed": failures,
                    "errors": errors,
                    "skipped": skipped,
                    "test_cases": test_cases[:10]  # Limit to first 10 for summary
                }
                
                output_text = f"Parsed JUnit XML test results:\n"
                output_text += f"Total: {total_tests}, Passed: {passed}, Failed: {failures}, Errors: {errors}, Skipped: {skipped}\n"
                
                return ToolResult(
                    success=True,
                    output=output_text,
                    metadata=summary
                )
            
            elif format_type == "pytest-json":
                content = result_file.read_text(encoding="utf-8")
                data = json.loads(content)
                
                # Extract statistics from pytest JSON
                summary = {
                    "total": data.get("summary", {}).get("total", 0),
                    "passed": data.get("summary", {}).get("passed", 0),
                    "failed": data.get("summary", {}).get("failed", 0),
                    "skipped": data.get("summary", {}).get("skipped", 0),
                }
                
                output_text = f"Parsed pytest JSON test results:\n"
                output_text += f"Total: {summary['total']}, Passed: {summary['passed']}, Failed: {summary['failed']}, Skipped: {summary['skipped']}\n"
                
                return ToolResult(
                    success=True,
                    output=output_text,
                    metadata=summary
                )
            
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported format: {format_type}"
                )
        except ET.ParseError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to parse XML: {str(e)}"
            )
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to parse JSON: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error parsing test results: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Error parsing test results: {str(e)}"
            )
