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
import argparse

class MyAgentCommand(Command):
    """Command for running a custom agent service."""
    
    @classmethod
    def get_name(cls) -> str:
        return "my-agent"
    
    @classmethod
    def get_description(cls) -> str:
        return "Run the custom agent service"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--input", type=str, help="Input for the agent")
    
    def init(self) -> None:
        """Initialize the agent (load config, setup resources, etc.)."""
        # Load configuration
        # Initialize resources
        pass
    
    def run(self) -> None:
        """Run the agent main loop (blocking)."""
        # Main agent logic here
        # This should block until shutdown
        pass
    
    def cleanup(self) -> None:
        """Clean up resources on shutdown."""
        # Close connections
        # Stop background tasks
        pass
```

### Service Structure

Services should be thin wrappers around `essence.command.Command` implementations:

1. **Service Entry Point**: FastAPI/HTTP endpoints or platform-specific handlers
2. **Command Invocation**: Call the appropriate `essence.command.Command` subclass
3. **Response Handling**: Format and return the command's output

#### Example Service Pattern

```python
from fastapi import FastAPI
from essence.commands.my_agent import MyAgentCommand
import argparse

app = FastAPI()

@app.post("/agent")
async def handle_agent_request(request: AgentRequest):
    # Create command with parsed arguments
    args = argparse.Namespace(input=request.input)
    command = MyAgentCommand(args)
    
    # Initialize and run (or use execute() for full lifecycle)
    command.init()
    try:
        # Run in background or call specific methods
        result = await run_agent_async(command)
        return {"result": result}
    finally:
        command.cleanup()
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

## Command Discovery

Commands are automatically discovered via Python reflection:

- Commands must be subclasses of `essence.command.Command`
- Commands must be located in the `essence.commands` package
- The `essence.__main__.get_commands()` function automatically discovers all commands
- No manual registration is required

Commands are discovered by:
1. Scanning all modules in `essence.commands`
2. Finding classes that are subclasses of `Command`
3. Extracting command names via `get_name()` classmethod

## Testing

Commands should be tested independently:

```python
import argparse
from essence.commands.my_agent import MyAgentCommand

def test_my_agent_command():
    # Create mock args
    args = argparse.Namespace(input="test")
    
    # Create command instance
    command = MyAgentCommand(args)
    
    # Test initialization
    command.init()
    
    # Test execution (or test run() separately)
    # Note: execute() calls init(), run(), cleanup() in sequence
    exit_code = command.execute()
    
    assert exit_code == 0
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

