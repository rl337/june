"""
Encryption helpers for Gateway service.

Provides easy-to-use functions for encrypting/decrypting sensitive database fields.
"""

import os
import sys
from pathlib import Path

# Add june-security package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages" / "june-security"))

try:
    from june_security.db_encryption import DatabaseEncryption
    
    # Initialize encryption helper
    _db_encryption = DatabaseEncryption()
    
    def encrypt_password_hash(password_hash: str) -> str:
        """
        Encrypt a password hash before storing in database.
        
        Args:
            password_hash: Bcrypt hashed password
            
        Returns:
            Encrypted password hash
        """
        return _db_encryption.encrypt_field(password_hash)
    
    def decrypt_password_hash(encrypted_hash: str) -> str:
        """
        Decrypt a password hash from database.
        
        Args:
            encrypted_hash: Encrypted password hash
            
        Returns:
            Decrypted password hash (bcrypt hash)
        """
        return _db_encryption.decrypt_field(encrypted_hash)
    
    def encrypt_token_hash(token_hash: str) -> str:
        """
        Encrypt a token hash before storing in database.
        
        Args:
            token_hash: SHA-256 hashed token
            
        Returns:
            Encrypted token hash
        """
        return _db_encryption.encrypt_field(token_hash)
    
    def decrypt_token_hash(encrypted_hash: str) -> str:
        """
        Decrypt a token hash from database.
        
        Args:
            encrypted_hash: Encrypted token hash
            
        Returns:
            Decrypted token hash (SHA-256 hash)
        """
        return _db_encryption.decrypt_field(encrypted_hash)
    
    def encrypt_api_key_hash(api_key_hash: str) -> str:
        """
        Encrypt an API key hash before storing in database.
        
        Args:
            api_key_hash: Hashed API key
            
        Returns:
            Encrypted API key hash
        """
        return _db_encryption.encrypt_field(api_key_hash)
    
    def decrypt_api_key_hash(encrypted_hash: str) -> str:
        """
        Decrypt an API key hash from database.
        
        Args:
            encrypted_hash: Encrypted API key hash
            
        Returns:
            Decrypted API key hash
        """
        return _db_encryption.decrypt_field(encrypted_hash)
    
    def encrypt_bot_token(bot_token: str) -> str:
        """
        Encrypt a bot token before storing in database.
        
        Args:
            bot_token: Plaintext bot token
            
        Returns:
            Encrypted bot token
        """
        return _db_encryption.encrypt_field(bot_token)
    
    def decrypt_bot_token(encrypted_token: str) -> str:
        """
        Decrypt a bot token from database.
        
        Args:
            encrypted_token: Encrypted bot token
            
        Returns:
            Decrypted bot token (plaintext)
        """
        return _db_encryption.decrypt_field(encrypted_token)
    
    # Check if encryption is enabled
    ENCRYPTION_ENABLED = os.getenv("ENABLE_DB_ENCRYPTION", "true").lower() == "true"
    
except ImportError as e:
    # Encryption not available, provide no-op functions
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Encryption not available: {e}. Using no-op functions.")
    
    ENCRYPTION_ENABLED = False
    
    def encrypt_password_hash(password_hash: str) -> str:
        return password_hash
    
    def decrypt_password_hash(encrypted_hash: str) -> str:
        return encrypted_hash
    
    def encrypt_token_hash(token_hash: str) -> str:
        return token_hash
    
    def decrypt_token_hash(encrypted_hash: str) -> str:
        return encrypted_hash
    
    def encrypt_api_key_hash(api_key_hash: str) -> str:
        return api_key_hash
    
    def decrypt_api_key_hash(encrypted_hash: str) -> str:
        return encrypted_hash
    
    def encrypt_bot_token(bot_token: str) -> str:
        return bot_token
    
    def decrypt_bot_token(encrypted_token: str) -> str:
        return encrypted_token
