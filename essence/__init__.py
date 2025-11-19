"""
Essence - June's core reusable codebase.

This module contains all the shared, reusable code that powers June's services.
Code here should be:
- Well-tested (pytest-driven tests in june/tests/)
- Platform-agnostic where possible
- Reusable across multiple services
- Properly documented

Structure:
- essence.chat: Chat service functionality (Telegram, Discord, etc.)
- essence.audio: Audio processing (STT, TTS)
- essence.agent: Agent execution and management
- essence.storage: Data storage and persistence
- essence.utils: Utility functions
- essence.config: Configuration management
"""

__version__ = "0.1.0"
