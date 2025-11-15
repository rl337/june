# June Security Module

Comprehensive security and safety measures for June agent execution.

## Features

### 1. Operation Validation
- **Block dangerous commands**: Prevents execution of commands like `rm -rf /`, `dd`, `mkfs`, etc.
- **File path validation**: Prevents directory traversal and access to unauthorized locations
- **Git operation validation**: Blocks force push to main/master branches and validates commit messages
- **Input sanitization**: Sanitizes user inputs to prevent injection attacks

### 2. Audit Logging
- **Comprehensive logging**: Logs all agent operations with full context
- **Security violation tracking**: Specifically tracks security violations
- **Audit trail**: Provides complete audit trail for compliance
- **Log export**: Allows retrieval and analysis of audit logs

### 3. Security Monitoring
- **Threat detection**: Detects suspicious patterns and security threats
- **Pattern recognition**: Identifies rapid failed operations, repeated blocked operations, path traversal attempts, etc.
- **Automated response**: Can automatically respond to high/critical threats
- **Threat statistics**: Provides statistics on detected threats per agent

### 4. Sandbox Management
- **Isolated execution**: Provides isolated execution environments
- **Resource limits**: Enforces CPU and memory limits per sandbox
- **File system isolation**: Isolates file system access within sandbox
- **Network restrictions**: (Future) Restrict network access (requires network namespaces)

## Installation

```bash
cd packages/june-security
pip install -e .
```

## Usage

### Basic Usage

```python
from june_security import SecurityManager
from pathlib import Path

# Initialize security manager
security_manager = SecurityManager(
    allowed_project_paths=[str(Path("/home/user/project"))],
    enable_sandboxing=True,
    enable_monitoring=True,
    enable_audit_logging=True
)

# Validate an operation before execution
validation_result, threat = security_manager.validate_command(
    agent_id="my-agent",
    command="ls -la"
)

if validation_result:
    # Operation is safe, proceed with execution
    execute_command("ls -la")
    security_manager.log_command_execution(
        agent_id="my-agent",
        command="ls -la",
        success=True
    )
else:
    # Operation blocked
    print(f"Operation blocked: {validation_result.reason}")
```

### Advanced Usage

```python
# Validate file path
validation_result, threat = security_manager.validate_file_path(
    agent_id="my-agent",
    file_path="/home/user/project/src/main.py",
    operation_type=OperationType.FILE_READ
)

# Validate git operation
validation_result, threat = security_manager.validate_git_operation(
    agent_id="my-agent",
    git_command="git push origin main --force"  # This will be blocked
)

# Use sandbox for isolated execution
sandbox_manager = security_manager.get_sandbox_manager()
with sandbox_manager.create_sandbox(agent_id="my-agent", project_path="/path/to/project") as sandbox:
    # Execute operations within sandbox
    # All file operations are isolated to sandbox directory
    pass

# Get security statistics
stats = security_manager.get_security_statistics(agent_id="my-agent")
print(f"Detected threats: {stats.get('threats', 0)}")

# Get detected threats
threats = security_manager.get_detected_threats(agent_id="my-agent")
for threat in threats:
    print(f"Threat: {threat.threat_type} (Level: {threat.threat_level.value})")
```

### Component-Level Usage

You can also use individual components directly:

```python
from june_security import SecurityValidator, AuditLogger, SecurityMonitor

# Use validator directly
validator = SecurityValidator(allowed_project_paths=["/path/to/project"])
result = validator.validate_command("rm -rf /")
assert not result  # This command is blocked

# Use audit logger directly
audit_logger = AuditLogger(log_file="audit.log")
audit_logger.log_operation(
    agent_id="my-agent",
    operation_type="command",
    operation="ls -la",
    allowed=True
)

# Use security monitor directly
monitor = SecurityMonitor()
is_safe, threat = monitor.analyze_operation(
    agent_id="my-agent",
    operation="rm -rf /",
    allowed=False,
    operation_type="command"
)
```

## Integration with June Agent

To integrate security into the June agent execution pipeline:

```python
# In agent loop scripts or similar
from june_security import SecurityManager
from pathlib import Path

# Initialize at startup
security_manager = SecurityManager(
    allowed_project_paths=[str(Path(project_path))],
    audit_log_file="audit.log"
)

# Before executing any operation
validation_result, threat = security_manager.validate_command(
    agent_id=agent_id,
    command=command_to_execute
)

if validation_result:
    # Execute command
    result = execute_command(command_to_execute)
    security_manager.log_command_execution(
        agent_id=agent_id,
        command=command_to_execute,
        success=result.success,
        output=result.output
    )
else:
    # Block execution
    raise SecurityError(f"Operation blocked: {validation_result.reason}")
```

## Configuration

Security manager can be configured with various options:

- `allowed_project_paths`: List of allowed project root paths (required)
- `audit_log_file`: Path to audit log file (optional)
- `enable_sandboxing`: Whether to enable sandboxing (default: True)
- `enable_monitoring`: Whether to enable security monitoring (default: True)
- `enable_audit_logging`: Whether to enable audit logging (default: True)

## Security Features

### Blocked Operations

The following operations are automatically blocked:

- Dangerous commands: `rm -rf /`, `dd`, `mkfs`, etc.
- Force push to main/master branches
- Access to critical system paths (`/etc/passwd`, `/etc/shadow`, etc.)
- Directory traversal attempts (`../`, etc.)
- Command injection patterns

### Detected Threats

The security monitor detects:

- Rapid failed operations (possible brute force)
- Repeated blocked operations (persistence attempts)
- Path traversal attempts
- Command injection attempts
- Mass file deletion attempts

## Testing

```bash
cd packages/june-security
pytest tests/
```

## License

See main project LICENSE file.
