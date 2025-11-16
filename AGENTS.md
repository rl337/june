# Agent Development Guidelines

This document outlines the architectural principles and best practices for developing agents and services within the June project.

## Core Architecture Principles

### Python Code Organization

**All Python code must be in the `essence` package.**

- The `essence` package is the single source of truth for all shared Python functionality
- Services should import from `essence`, not duplicate code
- New functionality should be added to `essence` rather than service-specific modules
- This ensures consistency, reusability, and maintainability across all services

### Entry Point Pattern

**The only entry point into code should be subclasses of `essence.command.Command`.**

- All executable functionality must be exposed through `essence.command.Command` subclasses
- This provides a consistent interface for:
  - Command-line invocation
  - Programmatic execution
  - Service integration
  - Testing and validation

#### Example Command Implementation

```python
from essence.command import Command

class MyAgentCommand(Command):
    """Description of what this agent does."""
    
    def execute(self, args):
        """Execute the agent logic."""
        # Your agent implementation here
        pass
    
    def validate(self, args):
        """Validate input arguments."""
        # Validation logic
        return True
```

### Service Structure

Services should be thin wrappers around `essence.command.Command` implementations:

1. **Service Entry Point**: FastAPI/HTTP endpoints or platform-specific handlers
2. **Command Invocation**: Call the appropriate `essence.command.Command` subclass
3. **Response Handling**: Format and return the command's output

#### Example Service Pattern

```python
from fastapi import FastAPI
from essence.command import get_command

app = FastAPI()

@app.post("/agent")
async def handle_agent_request(request: AgentRequest):
    # Get the command instance
    command = get_command("my_agent_command")
    
    # Execute with validated arguments
    result = command.execute(request.args)
    
    # Return formatted response
    return {"result": result}
```

## Benefits of This Architecture

1. **Consistency**: All agents follow the same interface pattern
2. **Testability**: Commands can be tested independently of service infrastructure
3. **Reusability**: Commands can be invoked from multiple contexts (CLI, HTTP, platform-specific)
4. **Maintainability**: Centralized code in `essence` reduces duplication
5. **Discoverability**: Commands are self-documenting and discoverable

## Migration Guidelines

When refactoring existing code:

1. **Move shared logic to `essence`**: Extract common functionality from services into `essence` modules
2. **Create Command subclasses**: Wrap executable functionality in `Command` subclasses
3. **Update service entry points**: Modify services to invoke commands rather than containing business logic
4. **Maintain backward compatibility**: During migration, services can call both old and new patterns

## Command Registration

Commands should be registered in a central registry (typically in `essence.command.registry`):

```python
from essence.command import Command, register_command

class MyAgentCommand(Command):
    # ... implementation ...

# Register the command
register_command("my_agent", MyAgentCommand)
```

## Testing

Commands should be tested independently:

```python
def test_my_agent_command():
    command = MyAgentCommand()
    result = command.execute({"input": "test"})
    assert result == expected_output
```

Service-level tests should verify command invocation:

```python
def test_service_calls_command():
    response = client.post("/agent", json={"args": {...}})
    assert response.status_code == 200
    # Verify command was called correctly
```

## Best Practices

1. **Keep services thin**: Services should only handle platform-specific concerns (HTTP, Discord, Telegram, etc.)
2. **Business logic in essence**: All business logic belongs in `essence` modules
3. **Command composition**: Complex agents can compose multiple commands
4. **Error handling**: Commands should raise appropriate exceptions; services handle platform-specific error formatting
5. **Logging**: Use structured logging from `essence` utilities

## Related Documentation

- See `essence/command/__init__.py` for Command base class implementation
- See `essence/README.md` for package structure and module organization
- See individual service READMEs for platform-specific integration patterns

