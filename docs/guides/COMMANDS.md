# Command Pattern Guide

This guide explains how to create and use commands in the June project.

## Overview

All reusable tools in June are implemented as **commands** that follow a consistent pattern. Commands are run via:

```bash
poetry run python -m essence <command-name> [arguments]
```

## Available Commands

### Service Commands
- `telegram-service` - Run Telegram bot service
- `discord-service` - Run Discord bot service
- `stt` - Run STT service
- `tts` - Run TTS service
- `inference-api` - Run legacy inference API service (deprecated, use TensorRT-LLM via home_infra)

### Utility Commands
- `download-models` - Download models for June Agent
- `monitor-gpu` - Monitor GPU metrics and export to Prometheus
- `review-sandbox` - Review sandbox snapshots from benchmark evaluations
- `run-benchmarks` - Run benchmark evaluations with sandboxed execution (HumanEval, MBPP)
- `verify-qwen3` - Verify Qwen3 quantization settings and model performance (legacy inference-api)
- `benchmark-qwen3` - Benchmark Qwen3-30B-A3B model performance
- `verify-tensorrt-llm` - Verify TensorRT-LLM setup and migration readiness
- `manage-tensorrt-llm` - Manage TensorRT-LLM models (load/unload/list/status)
- `setup-triton-repository` - Setup and validate Triton Inference Server model repository structure
- `compile-model` - Validate prerequisites and provide guidance for TensorRT-LLM model compilation
  - `--check-prerequisites` - Check GPU, repository structure, and build tools
  - `--generate-template` - Generate compilation command templates
  - `--generate-config` - Generate config.pbtxt template file
  - `--generate-tokenizer-commands` - Generate commands to copy tokenizer files
  - `--check-readiness` - Verify model is ready for loading (checks all required files)
- `verify-nim` - Verify NVIDIA NIM (NVIDIA Inference Microservice) setup and connectivity
  - `--nim-host HOST` - NIM service hostname (default: nim-qwen3)
  - `--http-port PORT` - NIM HTTP health port (default: 8003)
  - `--grpc-port PORT` - NIM gRPC port (default: 8001)
  - `--check-protocol` - Check gRPC protocol compatibility (requires june_grpc_api)
  - `--json` - Output results as JSON
- `get-message-history` - Retrieve and analyze message history for debugging Telegram and Discord rendering issues
  - `--user-id ID` - Filter by user ID
  - `--chat-id ID` - Filter by chat/channel ID
  - `--platform PLATFORM` - Filter by platform (telegram, discord)
  - `--analyze` - Analyze messages for rendering issues
  - `--compare TEXT` - Compare expected text with actual sent message
  - `--validate TEXT` - Validate message text for platform (requires --platform)
  - `--stats` - Show statistics instead of messages
  - `--format FORMAT` - Output format (text, json)

## Creating a New Command

### Step 1: Create Command File

Create a new file in `essence/commands/<command_name>.py`:

```python
"""
Command description.

Usage:
    poetry run python -m essence <command-name> [--option VALUE]
"""
import argparse
import logging
from essence.command import Command

logger = logging.getLogger(__name__)


class MyCommand(Command):
    """Command for doing something."""
    
    @classmethod
    def get_name(cls) -> str:
        return "my-command"
    
    @classmethod
    def get_description(cls) -> str:
        return "Description of what the command does"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--option",
            type=str,
            help="Option description"
        )
    
    def init(self) -> None:
        """Initialize command."""
        # Setup, validation, etc.
        pass
    
    def run(self) -> None:
        """Run the command."""
        # Main command logic
        logger.info(f"Running with option: {self.args.option}")
        # ... do work ...
    
    def cleanup(self) -> None:
        """Clean up command."""
        # Cleanup if needed
        pass
```

### Step 2: Register Command

Add import to `essence/commands/__init__.py`:

```python
from . import my_command  # noqa: F401
```

Add to `__all__` list:

```python
__all__ = [..., "my_command"]
```

### Step 3: Test Command

```bash
# Test help
poetry run python -m essence my-command --help

# Test command
poetry run python -m essence my-command --option value
```

## Command Lifecycle

Commands follow a consistent lifecycle:

1. **`init()`** - Initialize resources, validate configuration, setup
2. **`run()`** - Execute main command logic (blocking)
3. **`cleanup()`** - Clean up resources on shutdown

The `execute()` method in the base `Command` class handles this lifecycle automatically.

## Command Pattern Details

### Base Class

All commands inherit from `essence.command.Command`:

```python
from essence.command import Command

class MyCommand(Command):
    # Must implement:
    # - get_name() classmethod
    # - get_description() classmethod
    # - init() method
    # - run() method
    # - cleanup() method
    # Optional:
    # - add_args() classmethod
```

### Required Methods

1. **`get_name()`** - Returns command name (used as subcommand)
   ```python
   @classmethod
   def get_name(cls) -> str:
       return "my-command"
   ```

2. **`get_description()`** - Returns description for help text
   ```python
   @classmethod
   def get_description(cls) -> str:
       return "Description of command"
   ```

3. **`init()`** - Initialize command (setup, validation)
   ```python
   def init(self) -> None:
       # Validate args, setup resources
       pass
   ```

4. **`run()`** - Execute command (main logic)
   ```python
   def run(self) -> None:
       # Main command logic
       pass
   ```

5. **`cleanup()`** - Clean up resources
   ```python
   def cleanup(self) -> None:
       # Cleanup if needed
       pass
   ```

### Optional Methods

**`add_args()`** - Add command-specific arguments
```python
@classmethod
def add_args(cls, parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--option", help="Option description")
```

## Examples

### Simple One-Shot Command

```python
class ReviewSandboxCommand(Command):
    @classmethod
    def get_name(cls) -> str:
        return "review-sandbox"
    
    def init(self) -> None:
        pass  # No initialization needed
    
    def run(self) -> None:
        # Load and display sandbox data
        # Exit when done
        pass
    
    def cleanup(self) -> None:
        pass  # No cleanup needed
```

### Long-Running Service Command

```python
import time
import threading
from essence.command import Command

class MonitorGpuCommand(Command):
    def __init__(self, args):
        super().__init__(args)
        self._monitoring_active = False
        self._shutdown_event = threading.Event()
    
    def init(self) -> None:
        # Setup signal handlers for graceful shutdown
        self.setup_signal_handlers()
        
        # Initialize GPU monitoring
        # ... setup code ...
        
        self._monitoring_active = True
    
    def run(self) -> None:
        # Start monitoring loop
        while self._monitoring_active and not self._shutdown_event.is_set():
            # Collect metrics
            # ... collect metrics ...
            
            # Sleep with periodic checks for shutdown
            self._shutdown_event.wait(timeout=5)  # Check every 5 seconds
    
    def cleanup(self) -> None:
        # Shutdown GPU monitoring
        self._monitoring_active = False
        # ... cleanup code ...
```

### Service Command (Telegram/Discord/STT/TTS)

```python
from essence.command import Command
from essence.services.telegram.main import TelegramBotService

class TelegramServiceCommand(Command):
    @classmethod
    def get_name(cls) -> str:
        return "telegram-service"
    
    @classmethod
    def get_description(cls) -> str:
        return "Run the Telegram bot service"
    
    @classmethod
    def add_args(cls, parser):
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("TELEGRAM_SERVICE_PORT", "8080")),
            help="Health check HTTP port"
        )
    
    def init(self) -> None:
        # Validate required environment variables
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Initialize service
        self.service = TelegramBotService()
    
    def run(self) -> None:
        # Run service (blocking)
        self.service.run()
    
    def cleanup(self) -> None:
        # Service handles its own cleanup
        pass
```

### Command with Complex Arguments

```python
class DownloadModelsCommand(Command):
    @classmethod
    def add_args(cls, parser):
        parser.add_argument(
            "--model",
            type=str,
            help="Specific model to download (e.g., Qwen/Qwen3-30B-A3B-Thinking-2507)"
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Download all required models"
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List available models"
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Check download status of models"
        )
    
    def init(self) -> None:
        # Validate arguments
        if not any([self.args.model, self.args.all, self.args.list, self.args.status]):
            raise ValueError("Must specify --model, --all, --list, or --status")
    
    def run(self) -> None:
        if self.args.list:
            # List models
            pass
        elif self.args.status:
            # Check status
            pass
        elif self.args.all:
            # Download all
            pass
        elif self.args.model:
            # Download specific model
            pass
```

## Command Discovery

Commands are automatically discovered via reflection in `essence/__main__.py`:
- Commands must be in `essence/commands/` package
- Commands must inherit from `essence.command.Command`
- Commands must be imported in `essence/commands/__init__.py` (for module loading)
- The discovery mechanism scans all modules in `essence.commands` and finds classes that:
  - Inherit from `Command`
  - Are not the base `Command` class itself
  - Have a `get_name()` class method

**How it works:**
1. `essence/__main__.py` uses `pkgutil.iter_modules()` to scan `essence.commands`
2. Each module is imported
3. Classes are inspected to find `Command` subclasses
4. `get_name()` is called to get the command name
5. Commands are registered with argparse subparsers

**Note:** You must import your command module in `essence/commands/__init__.py` for it to be discovered. This ensures the module is loaded when the package is imported.

## Best Practices

1. **Use descriptive names** - `review-sandbox` not `review`
   - Use kebab-case for command names (e.g., `monitor-gpu`, `download-models`)
   - Service commands use `-service` suffix (e.g., `telegram-service`)

2. **Handle errors gracefully** - Log errors, return appropriate exit codes
   - The base `Command.execute()` method catches exceptions and returns exit codes
   - Use `logger.error()` for errors, `logger.warning()` for warnings
   - Raise exceptions for fatal errors (they'll be caught and logged)

3. **Support --help** - Always implement `add_args()` for argument help
   - Use descriptive help text for all arguments
   - Provide default values where appropriate
   - Support environment variables for configuration (see examples)

4. **Log appropriately** - Use `logger.info()`, `logger.error()`, etc.
   - Log important state changes
   - Log errors with full context
   - Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)

5. **Clean up resources** - Implement `cleanup()` for long-running commands
   - Close file handles, database connections, network connections
   - Stop background threads/tasks
   - Release locks, semaphores, etc.

6. **Handle signals** - Call `self.setup_signal_handlers()` in `init()` for long-running commands
   - This enables graceful shutdown on SIGTERM/SIGINT
   - Check `self._shutdown_event` in your run loop
   - Exit cleanly when shutdown is requested

7. **Environment variable support** - Support both CLI args and environment variables
   ```python
   parser.add_argument(
       "--port",
       type=int,
       default=int(os.getenv("SERVICE_PORT", "8080")),
       help="Service port (default: 8080)"
   )
   ```

8. **Validate early** - Do validation in `init()`, not `run()`
   - Check required environment variables
   - Validate configuration
   - Fail fast if something is wrong

9. **Document usage** - Add docstring with usage examples
   ```python
   """
   Command description.
   
   Usage:
       poetry run python -m essence my-command --option VALUE
   """
   ```

## Error Handling

The base `Command.execute()` method provides error handling:
- Catches `KeyboardInterrupt` (returns exit code 130)
- Catches all exceptions (returns exit code 1)
- Always calls `cleanup()` in a `finally` block
- Logs errors with full traceback

**Best practices:**
- Raise exceptions for fatal errors (don't catch and return codes manually)
- Use `logger.error()` for error context
- Validate in `init()` to fail fast
- Handle expected errors gracefully (e.g., file not found, network errors)

## Testing Commands

Commands can be tested like any Python class:

```python
import pytest
from essence.commands.my_command import MyCommand
import argparse

def test_my_command():
    # Create args
    args = argparse.Namespace(option="value")
    
    # Create command
    cmd = MyCommand(args)
    
    # Test initialization
    cmd.init()
    
    # Test execution (may need mocking for external dependencies)
    # cmd.run()
    
    # Test cleanup
    cmd.cleanup()
```

For integration tests, use `subprocess` to run commands:

```python
import subprocess

def test_command_via_subprocess():
    result = subprocess.run(
        ["poetry", "run", "python", "-m", "essence", "my-command", "--option", "value"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
```

## Migration from Scripts

When converting a script to a command:

1. **Move script logic** to `essence/commands/<command_name>.py`
   - Wrap main logic in `Command` class
   - Convert argument parsing to `add_args()`
   - Move initialization to `init()`
   - Move main logic to `run()`
   - Move cleanup to `cleanup()`

2. **Update imports** to use proper packages
   - Use `from essence.command import Command`
   - Update any relative imports

3. **Register command** in `essence/commands/__init__.py`
   ```python
   from . import my_command  # noqa: F401
   __all__ = [..., "my_command"]
   ```

4. **Update documentation**
   - Update README.md if command is mentioned
   - Update this guide if adding new patterns

5. **Test the command**
   ```bash
   poetry run python -m essence my-command --help
   poetry run python -m essence my-command --option value
   ```

6. **Remove old script** from `scripts/` (after verification)
   - Keep a shell wrapper if needed for complex container operations
   - Update any references to the old script

## See Also

- `essence/command/__init__.py` - Command base class
- `essence/commands/` - Example command implementations
- `REFACTOR_PLAN.md` - Project refactoring plan
