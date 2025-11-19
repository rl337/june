"""
Database encryption helpers for sensitive fields.

Provides decorators and utilities for automatically encrypting/decrypting
sensitive database fields.
"""

from typing import Optional, Callable, Any
from functools import wraps
from .encryption import get_encryption_manager, EncryptionManager


class DatabaseEncryption:
    """
    Helper class for encrypting/decrypting sensitive database fields.
    """

    def __init__(self, encryption_manager: Optional[EncryptionManager] = None):
        """
        Initialize database encryption helper.

        Args:
            encryption_manager: Optional EncryptionManager instance.
                              If None, creates one using ENCRYPTION_KEY env var.
        """
        self._encryption_manager = encryption_manager or get_encryption_manager()

    def encrypt_field(self, value: Optional[str]) -> Optional[str]:
        """
        Encrypt a database field value.

        Args:
            value: Plaintext value to encrypt. If None, returns None.

        Returns:
            Encrypted value (base64-encoded string), or None if input was None
        """
        if value is None:
            return None

        if value.startswith("encrypted:"):
            # Already encrypted, return as-is
            return value

        encrypted = self._encryption_manager.encrypt(value)
        return f"encrypted:{encrypted}"

    def decrypt_field(self, value: Optional[str]) -> Optional[str]:
        """
        Decrypt a database field value.

        Args:
            value: Encrypted value (with 'encrypted:' prefix) or plaintext.
                  If None, returns None.

        Returns:
            Decrypted plaintext value, or None if input was None
        """
        if value is None:
            return None

        if not value.startswith("encrypted:"):
            # Not encrypted, return as-is (for backward compatibility)
            return value

        encrypted = value[len("encrypted:") :]
        return self._encryption_manager.decrypt(encrypted)

    def is_encrypted(self, value: Optional[str]) -> bool:
        """
        Check if a value is encrypted.

        Args:
            value: Value to check

        Returns:
            True if value is encrypted, False otherwise
        """
        return value is not None and value.startswith("encrypted:")

    def encrypt_dict_fields(self, data: dict, fields: list[str]) -> dict:
        """
        Encrypt specified fields in a dictionary.

        Args:
            data: Dictionary containing data
            fields: List of field names to encrypt

        Returns:
            Dictionary with specified fields encrypted
        """
        result = data.copy()
        for field in fields:
            if field in result:
                result[field] = self.encrypt_field(result[field])
        return result

    def decrypt_dict_fields(self, data: dict, fields: list[str]) -> dict:
        """
        Decrypt specified fields in a dictionary.

        Args:
            data: Dictionary containing data
            fields: List of field names to decrypt

        Returns:
            Dictionary with specified fields decrypted
        """
        result = data.copy()
        for field in fields:
            if field in result:
                result[field] = self.decrypt_field(result[field])
        return result


# Sensitive fields that should be encrypted
SENSITIVE_FIELDS = {
    "users": ["password_hash"],
    "admin_users": ["password_hash"],
    "refresh_tokens": ["token_hash"],
    "service_accounts": ["api_key_hash"],
    "bot_config": ["bot_token"],
}


def encrypt_sensitive_fields(func: Callable) -> Callable:
    """
    Decorator to automatically encrypt sensitive fields before database insert/update.

    Usage:
        @encrypt_sensitive_fields
        def create_user(data: dict):
            # data['password_hash'] will be encrypted before this function runs
            ...
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        db_encryption = DatabaseEncryption()

        # Find dict arguments that might contain sensitive data
        for arg in args:
            if isinstance(arg, dict):
                # Try to determine table name from function name or context
                # For now, encrypt common fields
                for table, fields in SENSITIVE_FIELDS.items():
                    for field in fields:
                        if field in arg:
                            arg[field] = db_encryption.encrypt_field(arg[field])

        # Check kwargs
        for key, value in kwargs.items():
            if isinstance(value, dict):
                for table, fields in SENSITIVE_FIELDS.items():
                    for field in fields:
                        if field in value:
                            value[field] = db_encryption.encrypt_field(value[field])

        return func(*args, **kwargs)

    return wrapper


def decrypt_sensitive_fields(func: Callable) -> Callable:
    """
    Decorator to automatically decrypt sensitive fields after database select.

    Usage:
        @decrypt_sensitive_fields
        def get_user(user_id: str):
            # Returned dict will have password_hash decrypted
            ...
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        db_encryption = DatabaseEncryption()

        # Decrypt result if it's a dict or list of dicts
        if isinstance(result, dict):
            for table, fields in SENSITIVE_FIELDS.items():
                for field in fields:
                    if field in result:
                        result[field] = db_encryption.decrypt_field(result[field])
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    for table, fields in SENSITIVE_FIELDS.items():
                        for field in fields:
                            if field in item:
                                item[field] = db_encryption.decrypt_field(item[field])

        return result

    return wrapper
