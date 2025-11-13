"""
Authentication dependencies for FastAPI endpoints.

Provides dependency functions for:
- JWT token verification
- Role-based access control
- Permission checking
"""
import logging
from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from auth import (
    verify_access_token,
    check_permission,
    check_role,
    get_user_permissions,
    AuthenticationError,
    AuthorizationError
)

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Dependency to get current authenticated user from JWT token.
    
    Returns:
        Dictionary with user_id, roles, and permissions
        
    Raises:
        HTTPException: If token is invalid or missing
    """
    try:
        payload = verify_access_token(credentials.credentials)
        return {
            "user_id": payload.get("sub"),
            "roles": payload.get("roles", []),
            "permissions": payload.get("permissions", [])
        }
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


async def require_role(role: str):
    """
    Dependency factory to require a specific role.
    
    Args:
        role: Required role name
        
    Returns:
        Dependency function
    """
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_id = user.get("user_id")
        user_roles = user.get("roles", [])
        
        if role not in user_roles:
            # Fallback: Check database if role not in token
            if not check_role(user_id, role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{role}' required"
                )
        
        return user
    
    return role_checker


async def require_permission(permission: str):
    """
    Dependency factory to require a specific permission.
    
    Args:
        permission: Required permission name
        
    Returns:
        Dependency function
    """
    async def permission_checker(user: dict = Depends(get_current_user)) -> dict:
        user_id = user.get("user_id")
        user_permissions = user.get("permissions", [])
        
        if permission not in user_permissions:
            # Fallback: Check database if permission not in token
            if not check_permission(user_id, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{permission}' required"
                )
        
        return user
    
    return permission_checker


async def require_any_permission(permissions: List[str]):
    """
    Dependency factory to require any of the specified permissions.
    
    Args:
        permissions: List of permission names (user needs at least one)
        
    Returns:
        Dependency function
    """
    async def any_permission_checker(user: dict = Depends(get_current_user)) -> dict:
        user_id = user.get("user_id")
        user_permissions = user.get("permissions", [])
        
        # Check if user has any of the required permissions
        has_permission = any(
            perm in user_permissions or check_permission(user_id, perm)
            for perm in permissions
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of the following permissions required: {', '.join(permissions)}"
            )
        
        return user
    
    return any_permission_checker


# Common role dependencies
require_admin = require_role("admin")
require_user = require_role("user")
require_service = require_role("service")

# Common permission dependencies
require_users_read = require_permission("users.read")
require_users_write = require_permission("users.write")
require_admin_read = require_permission("admin.read")
require_admin_write = require_permission("admin.write")
