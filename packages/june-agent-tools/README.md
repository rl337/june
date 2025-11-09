# June Agent Tools

Agent tool system for code and git operations.

This package provides a comprehensive tool system that exposes code and git operations as tools that agents can use to implement changes.

## Features

### Tool Framework
- **Tool Interface**: Base `Tool` class for all operations
- **Tool Registry**: Centralized tool discovery and registration
- **Tool Executor**: Executes tools with safety checks and audit logging

### Code Tools
- **ReadFileTool**: Read file contents safely with path validation
- **WriteFileTool**: Write file contents with path validation and directory creation

### Git Tools
- **GitStatusTool**: Get git repository status
- **GitCommitTool**: Commit changes with message validation
- **GitPushTool**: Push commits to remote (force push to main/master blocked)
- **GitBranchTool**: Create and switch branches
- **GitDiffTool**: Get git diff

### Testing Tools
- **RunTestsTool**: Execute tests (pytest) and capture results
- **ParseTestResultsTool**: Parse test result files (JUnit XML, pytest JSON)
- **VerificationTool**: Comprehensive verification system that validates agent work before marking tasks complete

### Code Execution Tools
- **ExecutePythonCodeTool**: Execute Python code dynamically in a safe sandbox environment
- **ExecuteShellCommandTool**: Execute shell commands safely with resource limits and security restrictions
- **SandboxEnvironment**: Sandbox environment with resource limits (CPU, memory, timeout), security boundaries, and path validation

### Safety and Validation
- **Sandbox Environment**: Isolated execution with resource limits (CPU, memory, disk, network)
- **Security Boundaries**: Path validation, command validation, dangerous operation blocking
- Integration with `june-security` package for:
  - Path validation (prevent escaping project directories)
  - Command validation (block dangerous operations)
  - Git operation validation (commit message quality, prevent force push)
  - Audit logging of all operations
- **Resource Limits**: CPU time limits, memory limits, process limits, timeout controls
- **Network Access Control**: Optional network access blocking for code execution

## Installation

```bash
cd packages/june-agent-tools
pip install -e .
```

## Usage

### Basic Usage

```python
from june_agent_tools import ToolExecutor, get_tool, list_tools

# Initialize executor with project paths
executor = ToolExecutor(
    project_paths=["/path/to/project1", "/path/to/project2"],
    enable_security=True,
    enable_audit=True
)

# Execute a tool
result = executor.execute(
    tool_name="read_file",
    params={"file_path": "src/main.py"},
    agent_id="agent-1"
)

if result.success:
    print(f"File content: {result.output}")
else:
    print(f"Error: {result.error}")
```

### Tool Discovery

```python
from june_agent_tools import discover_tools, list_tools

# Discover all tools and get metadata
tools_metadata = discover_tools()
for name, metadata in tools_metadata.items():
    print(f"{name}: {metadata['description']}")

# List all tool instances
tools = list_tools()
for tool in tools:
    print(f"Tool: {tool.name} - {tool.description}")
```

### Tool Registration

Tools are automatically registered on import. To register manually:

```python
from june_agent_tools.tools import register_all_tools

register_all_tools()
```

### Example: File Operations

```python
from june_agent_tools import ToolExecutor

executor = ToolExecutor(project_paths=["/path/to/project"])

# Read a file
read_result = executor.execute(
    "read_file",
    {"file_path": "src/config.py"},
    agent_id="agent-1"
)

# Write a file
write_result = executor.execute(
    "write_file",
    {
        "file_path": "src/new_file.py",
        "content": "def hello():\n    print('Hello, World!')\n",
        "create_dirs": True
    },
    agent_id="agent-1"
)
```

### Example: Git Operations

```python
from june_agent_tools import ToolExecutor

executor = ToolExecutor(project_paths=["/path/to/project"])

# Get git status
status_result = executor.execute(
    "git_status",
    {"repo_path": "/path/to/project"},
    agent_id="agent-1"
)

# Commit changes
commit_result = executor.execute(
    "git_commit",
    {
        "repo_path": "/path/to/project",
        "message": "Add feature X with comprehensive tests",
        "stage_all": True
    },
    agent_id="agent-1"
)

# Push to remote
push_result = executor.execute(
    "git_push",
    {
        "repo_path": "/path/to/project",
        "remote": "origin",
        "branch": "feature-x"
    },
    agent_id="agent-1"
)
```

### Example: Testing

```python
from june_agent_tools import ToolExecutor

executor = ToolExecutor(project_paths=["/path/to/project"])

# Run tests
test_result = executor.execute(
    "run_tests",
    {
        "test_path": "tests/",
        "test_runner": "pytest",
        "options": ["-v", "--tb=short"]
    },
    agent_id="agent-1"
)

if test_result.success:
    print(f"Tests passed: {test_result.metadata.get('passed', 0)}")
else:
    print(f"Tests failed: {test_result.error}")
```

### Example: Comprehensive Verification

```python
from june_agent_tools import ToolExecutor

executor = ToolExecutor(project_paths=["/path/to/project"])

# Run comprehensive verification
verification_result = executor.execute(
    "verify_work",
    {
        "project_root": "/path/to/project",
        "run_tests": True,
        "check_quality": True,
        "check_functional": True,
        "check_integration": False,
        "check_documentation": True,
        "run_checks_script": True,
        "timeout": 300
    },
    agent_id="agent-1"
)

if verification_result.success:
    summary = verification_result.metadata.get("summary", {})
    print(f"Verification passed: {summary.get('passed', 0)}/{summary.get('total', 0)} checks passed")
else:
    checks = verification_result.metadata.get("checks", [])
    for check in checks:
        if not check["success"]:
            print(f"Failed: {check['check_name']} - {check['message']}")
            if check.get("suggestions"):
                print("Suggestions:")
                for suggestion in check["suggestions"]:
                    print(f"  - {suggestion}")
```

The VerificationTool provides:
- **Test Execution**: Runs unit and integration tests
- **Code Quality**: Checks syntax, formatting (black, isort), linting (flake8), type hints (mypy)
- **Functional Verification**: Validates feature works as specified
- **Integration Validation**: Tests integration with related services
- **Documentation Verification**: Checks README and docstrings
- **Automated Validation**: Integrates with run_checks.sh for comprehensive checks
- **Failure Analysis**: Provides actionable suggestions for common issues

## Architecture

### Tool Interface

All tools inherit from the `Tool` base class:

```python
from june_agent_tools.tool import Tool, ToolResult

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"
    
    @property
    def description(self) -> str:
        return "Tool description"
    
    def validate(self, params: Dict[str, Any]) -> bool:
        # Validate parameters
        return True
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        # Execute operation
        return ToolResult(success=True, output="result")
```

### Security Integration

The `ToolExecutor` integrates with `june-security` to provide:

1. **Path Validation**: Ensures all file paths are within allowed project directories
2. **Command Validation**: Blocks dangerous commands (rm -rf, etc.)
3. **Git Validation**: Validates commit messages and blocks force push to main/master
4. **Audit Logging**: Logs all tool executions for audit trail

### Error Handling

All tools return `ToolResult` objects:

```python
@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

## Dependencies

- `june-security>=0.1.0`: Security validation and audit logging

## Development

### Running Tests

```bash
cd packages/june-agent-tools
pytest tests/ -v
```

### Adding New Tools

1. Create tool class inheriting from `Tool`
2. Implement `name`, `description`, `validate()`, and `execute()`
3. Register tool in `june_agent_tools/tools.py`

## Integration with Agent API

Tools can be exposed via agent API endpoints. Example integration:

```python
from june_agent_tools import ToolExecutor, discover_tools
from fastapi import FastAPI

app = FastAPI()
executor = ToolExecutor(project_paths=["/path/to/project"])

@app.get("/tools")
def list_tools():
    return discover_tools()

@app.post("/tools/{tool_name}/execute")
def execute_tool(tool_name: str, params: dict, agent_id: str):
    result = executor.execute(tool_name, params, agent_id)
    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "metadata": result.metadata
    }
```

## License

MIT
