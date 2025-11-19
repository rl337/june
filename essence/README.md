# Essence - June's Core Codebase

Essence is June's core reusable codebase that powers all services. This module contains all shared, well-tested, platform-agnostic code.

## Structure

- `essence.chat` - Chat service functionality (Telegram, Discord, message handling, platform translators, etc.)
- `essence.agents` - Agent components (coding agent, evaluator, planner, executor, reflector, reasoning, etc.)
- `essence.commands` - Command pattern implementations (service commands, utility commands, etc.)
- `essence.services` - Service-specific code (telegram, discord, integration test, shared utilities)
- `essence.audio` - Audio processing (STT, TTS, audio utilities)
- `essence.storage` - Data storage and persistence
- `essence.utils` - Utility functions
- `essence.config` - Configuration management
- `essence.command` - Command pattern base classes and utilities

## Installation

**Note: All Python code in June is managed via Poetry. Use Poetry for installation and execution.**

```bash
# From project root, install dependencies
cd /home/rlee/dev/june
poetry install
```

For development with test dependencies:
```bash
poetry install --with dev
```

## Testing

All tests are in `june/tests/` and use pytest via Poetry:

```bash
# Run all tests
poetry run pytest

# Run specific test categories
poetry run pytest -m unit
poetry run pytest -m integration
poetry run pytest -m chat
poetry run pytest -m audio
```

## Dependencies

All dependencies are managed in `pyproject.toml`. This replaces the scattered `requirements.txt` files across services.

## Migration Notes

As we migrate code from services to essence:
1. Code should be platform-agnostic where possible
2. All code must have tests in `june/tests/`
3. Dependencies should be added to `pyproject.toml`
4. Services should import from `essence` module

