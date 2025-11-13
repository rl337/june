"""
MinIO encryption helpers for encrypting files at rest.

Provides utilities for encrypting/decrypting files stored in MinIO.
"""

import io
from typing import Optional, BinaryIO
from minio import Minio
from minio.error import S3Error
from .encryption import get_encryption_manager, EncryptionManager


class MinIOEncryption:
    """
    Helper class for encrypting/decrypting files in MinIO.
    """
    
    def __init__(
        self,
        minio_client: Minio,
        encryption_manager: Optional[EncryptionManager] = None
    ):
        """
        Initialize MinIO encryption helper.
        
        Args:
            minio_client: MinIO client instance
            encryption_manager: Optional EncryptionManager instance.
                              If None, creates one using ENCRYPTION_KEY env var.
        """
        self.minio_client = minio_client
        self._encryption_manager = encryption_manager or get_encryption_manager()
    
    def put_encrypted_object(
        self,
        bucket_name: str,
        object_name: str,
        data: bytes,
        length: Optional[int] = None,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None
    ) -> None:
        """
        Upload and encrypt an object to MinIO.
        
        Args:
            bucket_name: Bucket name
            object_name: Object name (key)
            data: Data to encrypt and upload
            length: Optional data length
            content_type: Content type
            metadata: Optional metadata dict
        """
        # Encrypt the data
        encrypted_data = self._encryption_manager.encrypt_bytes(data)
        
        # Add encryption metadata
        if metadata is None:
            metadata = {}
        metadata['encrypted'] = 'true'
        metadata['original_length'] = str(len(data))
        
        # Upload encrypted data
        data_stream = io.BytesIO(encrypted_data)
        self.minio_client.put_object(
            bucket_name,
            object_name,
            data_stream,
            length=len(encrypted_data) if length is None else length,
            content_type=content_type,
            metadata=metadata
        )
    
    def get_encrypted_object(
        self,
        bucket_name: str,
        object_name: str
    ) -> bytes:
        """
        Download and decrypt an object from MinIO.
        
        Args:
            bucket_name: Bucket name
            object_name: Object name (key)
            
        Returns:
            Decrypted data as bytes
        """
        # Download object
        response = self.minio_client.get_object(bucket_name, object_name)
        encrypted_data = response.read()
        response.close()
        response.release_conn()
        
        # Check if object is encrypted
        stat = self.minio_client.stat_object(bucket_name, object_name)
        is_encrypted = stat.metadata.get('encrypted', 'false').lower() == 'true'
        
        if is_encrypted:
            # Decrypt the data
            return self._encryption_manager.decrypt_bytes(encrypted_data)
        else:
            # Not encrypted, return as-is (for backward compatibility)
            return encrypted_data
    
    def copy_encrypted_object(
        self,
        source_bucket: str,
        source_object: str,
        dest_bucket: str,
        dest_object: str
    ) -> None:
        """
        Copy an encrypted object within MinIO (preserves encryption).
        
        Args:
            source_bucket: Source bucket name
            source_object: Source object name
            dest_bucket: Destination bucket name
            dest_object: Destination object name
        """
        # Use MinIO copy_object which preserves metadata
        from minio.commonconfig import CopySource
        
        copy_source = CopySource(source_bucket, source_object)
        self.minio_client.copy_object(
            dest_bucket,
            dest_object,
            copy_source
        )
    
    def is_encrypted(self, bucket_name: str, object_name: str) -> bool:
        """
        Check if an object is encrypted.
        
        Args:
            bucket_name: Bucket name
            object_name: Object name
            
        Returns:
            True if object is encrypted, False otherwise
        """
        try:
            stat = self.minio_client.stat_object(bucket_name, object_name)
            return stat.metadata.get('encrypted', 'false').lower() == 'true'
        except S3Error:
            return False
