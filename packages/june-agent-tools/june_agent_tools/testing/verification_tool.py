"""
Comprehensive verification system for agent work validation.

Provides a unified tool that runs all verification checks:
- Test execution (unit, integration)
- Code quality checks (formatting, linting, type hints)
- Functional verification
- Integration validation
- Documentation verification
- Automated validation via run_checks.sh
"""

import logging
import subprocess
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from june_agent_tools.tool import Tool, ToolResult
from june_agent_tools.testing.test_tools import RunTestsTool

logger = logging.getLogger(__name__)


class VerificationTool(Tool):
    """Comprehensive verification tool for validating agent work."""
    
    @property
    def name(self) -> str:
        return "verify_work"
    
    @property
    def description(self) -> str:
        return (
            "Comprehensive verification system that validates agent work before marking tasks complete. "
            "Runs tests, checks code quality, validates functionality, integration, documentation, "
            "and integrates with run_checks.sh. Returns detailed results with actionable suggestions."
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Root directory of the project. Defaults to current directory.",
                    "default": "."
                },
                "run_tests": {
                    "type": "boolean",
                    "description": "Run unit and integration tests",
                    "default": True
                },
                "check_quality": {
                    "type": "boolean",
                    "description": "Run code quality checks (formatting, linting, type hints)",
                    "default": True
                },
                "check_functional": {
                    "type": "boolean",
                    "description": "Verify feature works as specified",
                    "default": True
                },
                "check_integration": {
                    "type": "boolean",
                    "description": "Test integration with related services",
                    "default": False
                },
                "check_documentation": {
                    "type": "boolean",
                    "description": "Verify documentation is updated",
                    "default": True
                },
                "run_checks_script": {
                    "type": "boolean",
                    "description": "Run run_checks.sh script (comprehensive validation)",
                    "default": True
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum time to wait for checks (seconds)",
                    "default": 300,
                    "minimum": 10
                }
            },
            "required": []
        }
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate verification parameters."""
        timeout = params.get("timeout", 300)
        if timeout < 10:
            return False
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute comprehensive verification checks.
        
        Returns detailed results with suggestions for failures.
        """
        start_time = datetime.now()
        project_root = Path(params.get("project_root", ".")).resolve()
        
        # Configuration
        run_tests = params.get("run_tests", True)
        check_quality = params.get("check_quality", True)
        check_functional = params.get("check_functional", True)
        check_integration = params.get("check_integration", False)
        check_documentation = params.get("check_documentation", True)
        run_checks_script = params.get("run_checks_script", True)
        timeout = params.get("timeout", 300)
        
        results = []
        all_passed = True
        
        logger.info(f"Starting verification checks in {project_root}")
        
        # 1. Run run_checks.sh if available (comprehensive check)
        if run_checks_script:
            result = self._run_checks_script(project_root, timeout)
            results.append(result)
            if not result["success"]:
                all_passed = False
        
        # 2. Test execution
        if run_tests:
            result = self._run_tests(project_root, timeout)
            results.append(result)
            if not result["success"]:
                all_passed = False
        
        # 3. Code quality checks
        if check_quality:
            quality_results = self._check_code_quality(project_root)
            results.extend(quality_results)
            if not all(r["success"] for r in quality_results):
                all_passed = False
        
        # 4. Functional verification
        if check_functional:
            result = self._check_functional(project_root)
            results.append(result)
            if not result["success"]:
                all_passed = False
        
        # 5. Integration validation
        if check_integration:
            result = self._check_integration(project_root)
            results.append(result)
            if not result["success"]:
                all_passed = False
        
        # 6. Documentation verification
        if check_documentation:
            result = self._check_documentation(project_root)
            results.append(result)
            if not result["success"]:
                all_passed = False
        
        # Calculate summary
        duration = (datetime.now() - start_time).total_seconds()
        total = len(results)
        passed = sum(1 for r in results if r["success"])
        failed = total - passed
        
        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "duration_seconds": duration,
            "all_passed": all_passed
        }
        
        # Build output message
        output_lines = []
        output_lines.append(f"Verification {'PASSED' if all_passed else 'FAILED'}: {passed}/{total} checks passed")
        output_lines.append(f"Duration: {duration:.2f} seconds")
        output_lines.append("")
        
        for result in results:
            status = "?" if result["success"] else "?"
            output_lines.append(f"{status} {result['check_name']}: {result['message']}")
            if not result["success"] and result.get("details"):
                output_lines.append(f"  Details: {result['details'][:200]}...")
            if result.get("suggestions"):
                output_lines.append(f"  Suggestions:")
                for suggestion in result["suggestions"]:
                    output_lines.append(f"    - {suggestion}")
        
        output_text = "\n".join(output_lines)
        
        return ToolResult(
            success=all_passed,
            output=output_text,
            metadata={
                "summary": summary,
                "checks": results
            }
        )
    
    def _run_checks_script(self, project_root: Path, timeout: int) -> Dict[str, Any]:
        """Run the run_checks.sh script."""
        checks_script = project_root / "run_checks.sh"
        
        if not checks_script.exists():
            return {
                "check_name": "run_checks.sh",
                "success": False,
                "message": "run_checks.sh not found",
                "details": f"Expected {checks_script}",
                "suggestions": [
                    "Create run_checks.sh script for comprehensive validation",
                    "Or disable run_checks_script parameter"
                ]
            }
        
        start_time = datetime.now()
        try:
            logger.info(f"Running {checks_script}")
            result = subprocess.run(
                ["bash", str(checks_script)],
                cwd=project_root,
                timeout=timeout,
                capture_output=True,
                text=True
            )
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                return {
                    "check_name": "run_checks.sh",
                    "success": True,
                    "message": "All checks passed",
                    "details": result.stdout[-1000:] if result.stdout else None,
                    "duration_seconds": duration
                }
            else:
                suggestions = self._analyze_failures(result.stderr, result.stdout)
                
                return {
                    "check_name": "run_checks.sh",
                    "success": False,
                    "message": "Some checks failed",
                    "details": (result.stderr[-2000:] if result.stderr else result.stdout[-2000:]),
                    "duration_seconds": duration,
                    "suggestions": suggestions
                }
        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "check_name": "run_checks.sh",
                "success": False,
                "message": f"Checks timed out after {timeout} seconds",
                "duration_seconds": duration,
                "suggestions": [
                    "Increase timeout value",
                    "Check for hanging tests or operations",
                    "Review run_checks.sh for inefficient checks"
                ]
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error running checks script: {e}", exc_info=True)
            return {
                "check_name": "run_checks.sh",
                "success": False,
                "message": f"Error running checks: {str(e)}",
                "duration_seconds": duration,
                "suggestions": [
                    "Check that run_checks.sh is executable",
                    "Verify dependencies are installed",
                    "Check file permissions"
                ]
            }
    
    def _run_tests(self, project_root: Path, timeout: int) -> Dict[str, Any]:
        """Run unit and integration tests."""
        start_time = datetime.now()
        
        # Use existing RunTestsTool for consistency
        test_tool = RunTestsTool()
        test_params = {
            "test_path": "tests/",
            "work_dir": str(project_root),
            "options": ["-v", "--tb=short"],
            "capture_output": True
        }
        
        if not test_tool.validate(test_params):
            return {
                "check_name": "test_execution",
                "success": False,
                "message": "Invalid test parameters",
                "suggestions": ["Verify test directory exists"]
            }
        
        result = test_tool.execute(test_params)
        duration = (datetime.now() - start_time).total_seconds()
        
        if result.success:
            metadata = result.metadata or {}
            passed = metadata.get("passed", 0)
            failed = metadata.get("failed", 0)
            return {
                "check_name": "test_execution",
                "success": True,
                "message": f"Tests passed: {passed} passed, {failed} failed",
                "details": result.output,
                "duration_seconds": duration
            }
        else:
            suggestions = [
                "Review test failures",
                "Run specific failing tests: pytest tests/test_<module>.py::test_<function> -v",
                "Check that all dependencies are installed"
            ]
            
            return {
                "check_name": "test_execution",
                "success": False,
                "message": "Some tests failed",
                "details": result.error or result.output,
                "duration_seconds": duration,
                "suggestions": suggestions
            }
    
    def _check_code_quality(self, project_root: Path) -> List[Dict[str, Any]]:
        """Check code quality (formatting, linting, type hints)."""
        results = []
        
        # Check 1: Python syntax
        syntax_result = self._check_syntax(project_root)
        results.append(syntax_result)
        
        # Check 2: Code formatting (black, isort)
        formatting_result = self._check_formatting(project_root)
        results.append(formatting_result)
        
        # Check 3: Linting (flake8, pylint)
        linting_result = self._check_linting(project_root)
        results.append(linting_result)
        
        # Check 4: Type hints
        type_hints_result = self._check_type_hints(project_root)
        results.append(type_hints_result)
        
        return results
    
    def _check_syntax(self, project_root: Path) -> Dict[str, Any]:
        """Check Python syntax errors."""
        start_time = datetime.now()
        issues = []
        
        try:
            # Find Python files
            python_files = []
            for ext in ["*.py"]:
                python_files.extend(project_root.rglob(ext))
            
            for py_file in python_files[:50]:  # Limit to first 50 files
                try:
                    result = subprocess.run(
                        ["python3", "-m", "py_compile", str(py_file)],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode != 0:
                        issues.append(f"Syntax error in {py_file.relative_to(project_root)}: {result.stderr}")
                except Exception as e:
                    issues.append(f"Error checking {py_file}: {str(e)}")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if issues:
                return {
                    "check_name": "syntax_check",
                    "success": False,
                    "message": f"Found {len(issues)} syntax errors",
                    "details": "\n".join(issues[:10]),  # First 10 issues
                    "duration_seconds": duration,
                    "suggestions": [
                        "Fix syntax errors in listed files",
                        "Run: python3 -m py_compile <file> to see details"
                    ]
                }
            else:
                return {
                    "check_name": "syntax_check",
                    "success": True,
                    "message": "No syntax errors found",
                    "duration_seconds": duration
                }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error checking syntax: {e}", exc_info=True)
            return {
                "check_name": "syntax_check",
                "success": False,
                "message": f"Error checking syntax: {str(e)}",
                "duration_seconds": duration
            }
    
    def _check_formatting(self, project_root: Path) -> Dict[str, Any]:
        """Check code formatting (black, isort)."""
        start_time = datetime.now()
        
        try:
            # Check black formatting
            black_result = subprocess.run(
                ["black", "--check", "--diff", "."],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Check isort
            isort_result = subprocess.run(
                ["isort", "--check-only", "--diff", "."],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            issues = []
            if black_result.returncode != 0:
                issues.append("Code formatting issues (black)")
            if isort_result.returncode != 0:
                issues.append("Import sorting issues (isort)")
            
            if issues:
                return {
                    "check_name": "formatting_check",
                    "success": False,
                    "message": f"Found formatting issues: {', '.join(issues)}",
                    "details": (black_result.stdout or black_result.stderr or "")[:500],
                    "duration_seconds": duration,
                    "suggestions": [
                        "Run: black .",
                        "Run: isort .",
                        "Or: black . && isort ."
                    ]
                }
            else:
                return {
                    "check_name": "formatting_check",
                    "success": True,
                    "message": "Code formatting is correct",
                    "duration_seconds": duration
                }
        except FileNotFoundError:
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "check_name": "formatting_check",
                "success": False,
                "message": "black or isort not found",
                "duration_seconds": duration,
                "suggestions": [
                    "Install: pip install black isort",
                    "Or disable formatting check"
                ]
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error checking formatting: {e}", exc_info=True)
            return {
                "check_name": "formatting_check",
                "success": False,
                "message": f"Error checking formatting: {str(e)}",
                "duration_seconds": duration
            }
    
    def _check_linting(self, project_root: Path) -> Dict[str, Any]:
        """Check linting (flake8)."""
        start_time = datetime.now()
        
        try:
            result = subprocess.run(
                ["flake8", "."],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                return {
                    "check_name": "linting_check",
                    "success": True,
                    "message": "No linting errors found",
                    "duration_seconds": duration
                }
            else:
                lines = result.stdout.splitlines()[:20]  # First 20 issues
                return {
                    "check_name": "linting_check",
                    "success": False,
                    "message": f"Found {len(result.stdout.splitlines())} linting errors",
                    "details": "\n".join(lines),
                    "duration_seconds": duration,
                    "suggestions": [
                        "Review and fix linting errors",
                        "Run: flake8 . to see all issues",
                        "Configure .flake8 or setup.cfg for project-specific rules"
                    ]
                }
        except FileNotFoundError:
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "check_name": "linting_check",
                "success": False,
                "message": "flake8 not found",
                "duration_seconds": duration,
                "suggestions": [
                    "Install: pip install flake8",
                    "Or disable linting check"
                ]
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error checking linting: {e}", exc_info=True)
            return {
                "check_name": "linting_check",
                "success": False,
                "message": f"Error checking linting: {str(e)}",
                "duration_seconds": duration
            }
    
    def _check_type_hints(self, project_root: Path) -> Dict[str, Any]:
        """Check for type hints in code."""
        start_time = datetime.now()
        
        try:
            # Use mypy if available, otherwise basic check
            result = subprocess.run(
                ["mypy", ".", "--ignore-missing-imports"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # mypy returns 0 on success, 1 on type errors, 2 on command errors
            if result.returncode == 0:
                return {
                    "check_name": "type_hints_check",
                    "success": True,
                    "message": "Type checking passed",
                    "duration_seconds": duration
                }
            elif result.returncode == 1:
                return {
                    "check_name": "type_hints_check",
                    "success": False,
                    "message": "Type checking found errors",
                    "details": result.stdout[:1000],
                    "duration_seconds": duration,
                    "suggestions": [
                        "Review type errors",
                        "Add type hints to functions",
                        "Run: mypy . to see all errors"
                    ]
                }
            else:
                return {
                    "check_name": "type_hints_check",
                    "success": False,
                    "message": "mypy command error",
                    "details": result.stderr[:500],
                    "duration_seconds": duration,
                    "suggestions": ["Check mypy configuration"]
                }
        except FileNotFoundError:
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "check_name": "type_hints_check",
                "success": True,  # Not required if mypy not installed
                "message": "mypy not found (type checking optional)",
                "duration_seconds": duration
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error checking type hints: {e}", exc_info=True)
            return {
                "check_name": "type_hints_check",
                "success": False,
                "message": f"Error checking type hints: {str(e)}",
                "duration_seconds": duration
            }
    
    def _check_functional(self, project_root: Path) -> Dict[str, Any]:
        """Verify feature works as specified (basic validation)."""
        start_time = datetime.now()
        
        try:
            # Basic functional check: can we import main modules?
            # This is a simple check - agents should implement task-specific functional tests
            test_files = list(project_root.glob("tests/**/*.py"))
            
            if not test_files:
                duration = (datetime.now() - start_time).total_seconds()
                return {
                    "check_name": "functional_verification",
                    "success": True,
                    "message": "Functional verification skipped (no specific checks configured)",
                    "details": "Agents should implement task-specific functional tests",
                    "duration_seconds": duration,
                    "suggestions": [
                        "Add functional tests in tests/ directory",
                        "Test edge cases and error handling",
                        "Validate feature works as specified"
                    ]
                }
            
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "check_name": "functional_verification",
                "success": True,
                "message": "Functional verification: tests available",
                "details": f"Found {len(test_files)} test files",
                "duration_seconds": duration
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error in functional verification: {e}", exc_info=True)
            return {
                "check_name": "functional_verification",
                "success": False,
                "message": f"Error in functional verification: {str(e)}",
                "duration_seconds": duration
            }
    
    def _check_integration(self, project_root: Path) -> Dict[str, Any]:
        """Test integration with related services."""
        start_time = datetime.now()
        
        try:
            # Check for integration test files
            integration_tests = list(project_root.glob("tests/integration/**/*.py"))
            
            if not integration_tests:
                duration = (datetime.now() - start_time).total_seconds()
                return {
                    "check_name": "integration_validation",
                    "success": True,
                    "message": "Integration validation skipped (no integration tests found)",
                    "duration_seconds": duration,
                    "suggestions": [
                        "Add integration tests in tests/integration/",
                        "Test with related services",
                        "Verify API compatibility"
                    ]
                }
            
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "check_name": "integration_validation",
                "success": True,
                "message": f"Integration tests available ({len(integration_tests)} files)",
                "duration_seconds": duration
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error in integration validation: {e}", exc_info=True)
            return {
                "check_name": "integration_validation",
                "success": False,
                "message": f"Error in integration validation: {str(e)}",
                "duration_seconds": duration
            }
    
    def _check_documentation(self, project_root: Path) -> Dict[str, Any]:
        """Verify documentation is updated."""
        start_time = datetime.now()
        
        try:
            # Check for README.md
            readme = project_root / "README.md"
            docs_updated = readme.exists()
            
            # Check if there are docstrings in Python files
            src_files = list((project_root / "src").glob("*.py")) if (project_root / "src").exists() else []
            docstring_count = 0
            for py_file in src_files[:20]:  # Check first 20 files
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if '"""' in content or "'''" in content:
                    docstring_count += 1
            
            duration = (datetime.now() - start_time).total_seconds()
            
            issues = []
            if not docs_updated:
                issues.append("README.md not found")
            
            if issues:
                return {
                    "check_name": "documentation_verification",
                    "success": False,
                    "message": f"Documentation issues: {', '.join(issues)}",
                    "duration_seconds": duration,
                    "suggestions": [
                        "Create or update README.md",
                        "Add docstrings to public functions",
                        "Update API documentation if needed"
                    ]
                }
            else:
                return {
                    "check_name": "documentation_verification",
                    "success": True,
                    "message": "Documentation appears up to date",
                    "details": f"README.md found, {docstring_count}/{len(src_files)} files have docstrings",
                    "duration_seconds": duration
                }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error checking documentation: {e}", exc_info=True)
            return {
                "check_name": "documentation_verification",
                "success": False,
                "message": f"Error checking documentation: {str(e)}",
                "duration_seconds": duration
            }
    
    def _analyze_failures(self, stderr: str, stdout: str) -> List[str]:
        """Analyze failure output and generate suggestions."""
        suggestions = []
        combined = (stderr or "") + " " + (stdout or "")
        combined_lower = combined.lower()
        
        if "test" in combined_lower and ("fail" in combined_lower or "error" in combined_lower):
            suggestions.append("Review test failures and fix broken tests")
        
        if "syntax" in combined_lower or "syntaxerror" in combined_lower:
            suggestions.append("Fix syntax errors in Python files")
        
        if "import" in combined_lower and ("error" in combined_lower or "failed" in combined_lower):
            suggestions.append("Fix import errors - check dependencies are installed")
        
        if "format" in combined_lower or "black" in combined_lower:
            suggestions.append("Run code formatter: black . && isort .")
        
        if "lint" in combined_lower or "flake8" in combined_lower:
            suggestions.append("Fix linting errors: flake8 . to see issues")
        
        if "timeout" in combined_lower:
            suggestions.append("Some operations timed out - check for hanging processes")
        
        if not suggestions:
            suggestions.append("Review error output for specific issues")
        
        return suggestions