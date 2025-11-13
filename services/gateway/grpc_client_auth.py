"""
gRPC Client Authentication Helper for Gateway Service.

Provides helpers for Gateway to authenticate when calling gRPC services.
"""
import os
import logging
from typing import Optional
import grpc

from auth import create_service_token

logger = logging.getLogger(__name__)

SERVICE_NAME = "gateway"


def create_service_metadata() -> tuple:
    """
    Create gRPC metadata with service authentication token.
    
    Returns:
        Tuple of metadata key-value pairs for gRPC calls
    """
    try:
        token = create_service_token(SERVICE_NAME)
        return (
            ("authorization", f"Bearer {token}"),
        )
    except Exception as e:
        logger.error(f"Failed to create service token: {e}", exc_info=True)
        # Fallback: use API key if available
        api_key = os.getenv("SERVICE_API_KEY", "")
        if api_key:
            return (
                ("x-api-key", api_key),
            )
        return tuple()


def add_auth_to_metadata(metadata: Optional[tuple] = None) -> tuple:
    """
    Add authentication metadata to existing gRPC metadata.
    
    Args:
        metadata: Existing metadata tuple
        
    Returns:
        Combined metadata tuple with authentication
    """
    auth_metadata = create_service_metadata()
    
    if metadata:
        return metadata + auth_metadata
    
    return auth_metadata
