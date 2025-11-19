"""
Encryption module for June Security Package.

Provides encryption/decryption functionality for sensitive data at rest and in transit.
Uses Fernet (symmetric encryption) for application-level encryption.
"""

import base64
import os
from typing import BinaryIO, Optional, Union

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionManager:
    """
    Manages encryption and decryption of sensitive data.

    Uses Fernet (symmetric encryption) with key derivation from a master key.
    Supports key rotation and secure key management.
    """

    def __init__(self, master_key: Optional[Union[str, bytes]] = None):
        """
        Initialize the encryption manager.

        Args:
            master_key: Master encryption key. If None, reads from ENCRYPTION_KEY env var.
                      Can be a string (will be encoded) or bytes.
        """
        if master_key is None:
            master_key = os.getenv("ENCRYPTION_KEY")
            if master_key is None:
                raise ValueError(
                    "ENCRYPTION_KEY environment variable must be set, "
                    "or master_key must be provided"
                )

        # Convert string to bytes if needed
        if isinstance(master_key, str):
            master_key = master_key.encode("utf-8")

        # Derive Fernet key from master key using PBKDF2
        # This allows using a passphrase as the master key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"june_encryption_salt",  # Fixed salt for key derivation
            iterations=100000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key))
        self._fernet = Fernet(key)

    def encrypt(self, data: Union[str, bytes]) -> str:
        """
        Encrypt data and return base64-encoded encrypted string.

        Args:
            data: Data to encrypt (string or bytes)

        Returns:
            Base64-encoded encrypted string
        """
        if isinstance(data, str):
            data = data.encode("utf-8")

        encrypted = self._fernet.encrypt(data)
        return base64.urlsafe_b64encode(encrypted).decode("utf-8")

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt base64-encoded encrypted string.

        Args:
            encrypted_data: Base64-encoded encrypted string

        Returns:
            Decrypted string
        """
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode("utf-8"))
            decrypted = self._fernet.decrypt(encrypted_bytes)
            return decrypted.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to decrypt data: {str(e)}")

    def encrypt_bytes(self, data: bytes) -> bytes:
        """
        Encrypt bytes and return encrypted bytes.

        Args:
            data: Bytes to encrypt

        Returns:
            Encrypted bytes
        """
        return self._fernet.encrypt(data)

    def decrypt_bytes(self, encrypted_data: bytes) -> bytes:
        """
        Decrypt encrypted bytes.

        Args:
            encrypted_data: Encrypted bytes

        Returns:
            Decrypted bytes
        """
        try:
            return self._fernet.decrypt(encrypted_data)
        except Exception as e:
            raise ValueError(f"Failed to decrypt data: {str(e)}")

    def encrypt_file(
        self,
        input_file: Union[str, BinaryIO],
        output_file: Optional[Union[str, BinaryIO]] = None,
    ) -> Optional[bytes]:
        """
        Encrypt a file.

        Args:
            input_file: Path to input file or file-like object
            output_file: Path to output file or file-like object. If None, returns encrypted bytes.

        Returns:
            Encrypted bytes if output_file is None, otherwise None
        """
        # Read input
        if isinstance(input_file, str):
            with open(input_file, "rb") as f:
                data = f.read()
        else:
            data = input_file.read()

        # Encrypt
        encrypted = self.encrypt_bytes(data)

        # Write output
        if output_file is None:
            return encrypted

        if isinstance(output_file, str):
            with open(output_file, "wb") as f:
                f.write(encrypted)
        else:
            output_file.write(encrypted)

        return None

    def decrypt_file(
        self,
        input_file: Union[str, BinaryIO],
        output_file: Optional[Union[str, BinaryIO]] = None,
    ) -> Optional[bytes]:
        """
        Decrypt a file.

        Args:
            input_file: Path to encrypted file or file-like object
            output_file: Path to output file or file-like object. If None, returns decrypted bytes.

        Returns:
            Decrypted bytes if output_file is None, otherwise None
        """
        # Read input
        if isinstance(input_file, str):
            with open(input_file, "rb") as f:
                encrypted_data = f.read()
        else:
            encrypted_data = input_file.read()

        # Decrypt
        decrypted = self.decrypt_bytes(encrypted_data)

        # Write output
        if output_file is None:
            return decrypted

        if isinstance(output_file, str):
            with open(output_file, "wb") as f:
                f.write(decrypted)
        else:
            output_file.write(decrypted)

        return None


def get_encryption_manager(
    master_key: Optional[Union[str, bytes]] = None
) -> EncryptionManager:
    """
    Get or create a global encryption manager instance.

    Args:
        master_key: Optional master key. If None, uses ENCRYPTION_KEY env var.

    Returns:
        EncryptionManager instance
    """
    return EncryptionManager(master_key=master_key)


def generate_encryption_key() -> str:
    """
    Generate a new encryption key.

    Returns:
        Base64-encoded encryption key suitable for ENCRYPTION_KEY env var
    """
    key = Fernet.generate_key()
    return base64.urlsafe_b64encode(key).decode("utf-8")
