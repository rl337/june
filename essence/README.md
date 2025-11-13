# Essence - June's Core Codebase

Essence is June's core reusable codebase that powers all services. This module contains all shared, well-tested, platform-agnostic code.

## Structure

- `essence.chat` - Chat service functionality (Telegram, Discord, etc.)
- `essence.audio` - Audio processing (STT, TTS, audio utilities)
- `essence.gateway` - Gateway and API functionality
- `essence.agent` - Agent execution and management
- `essence.storage` - Data storage and persistence
- `essence.utils` - Utility functions
- `essence.config` - Configuration management

## Installation

```bash
cd essence
pip install -e .
```

For development with test dependencies:
```bash
pip install -e ".[dev]"
```

## Testing

All tests are in `june/tests/` and use pytest:

```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit
pytest -m integration
pytest -m chat
pytest -m audio
```

## Dependencies

All dependencies are managed in `pyproject.toml`. This replaces the scattered `requirements.txt` files across services.

## Migration Notes

As we migrate code from services to essence:
1. Code should be platform-agnostic where possible
2. All code must have tests in `june/tests/`
3. Dependencies should be added to `pyproject.toml`
4. Services should import from `essence` module

