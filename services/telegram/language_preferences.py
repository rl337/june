"""
Language preference storage for Telegram bot users.

Stores language preferences per user/chat. Uses in-memory storage
(can be upgraded to persistent storage later if needed).
"""
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# In-memory storage: (user_id, chat_id) -> language_code
_language_preferences: Dict[tuple, str] = {}

# Supported languages (ISO 639-1 codes)
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "hi": "Hindi",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "pl": "Polish",
    "tr": "Turkish",
    "el": "Greek",
}

DEFAULT_LANGUAGE = "en"


def get_language_preference(user_id: str, chat_id: str) -> str:
    """
    Get language preference for a user/chat.
    
    Args:
        user_id: Telegram user ID
        chat_id: Telegram chat ID
        
    Returns:
        Language code (ISO 639-1), defaults to "en"
    """
    key = (user_id, chat_id)
    language = _language_preferences.get(key, DEFAULT_LANGUAGE)
    logger.debug(f"Language preference for {user_id}/{chat_id}: {language}")
    return language


def set_language_preference(user_id: str, chat_id: str, language_code: str) -> bool:
    """
    Set language preference for a user/chat.
    
    Args:
        user_id: Telegram user ID
        chat_id: Telegram chat ID
        language_code: Language code (ISO 639-1)
        
    Returns:
        True if language was set, False if language code is invalid
    """
    # Normalize language code (lowercase)
    language_code = language_code.lower()
    
    # Validate language code
    if language_code not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language code: {language_code}")
        return False
    
    key = (user_id, chat_id)
    _language_preferences[key] = language_code
    logger.info(f"Set language preference for {user_id}/{chat_id}: {language_code}")
    return True


def get_supported_languages() -> Dict[str, str]:
    """
    Get dictionary of supported language codes and names.
    
    Returns:
        Dictionary mapping language codes to language names
    """
    return SUPPORTED_LANGUAGES.copy()


def is_language_supported(language_code: str) -> bool:
    """
    Check if a language code is supported.
    
    Args:
        language_code: Language code to check
        
    Returns:
        True if supported, False otherwise
    """
    return language_code.lower() in SUPPORTED_LANGUAGES
