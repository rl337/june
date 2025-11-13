"""
Comprehensive authentication and authorization module for June Gateway.

Provides:
- JWT token generation and validation
- Refresh token management
- Role-based access control (RBAC)
- Permission checking
- Service-to-service authentication
"""
import os
import logging
import secrets
import hashlib
import bcrypt
import psycopg2
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from jose import JWTError, jwt
from db_pool import get_db_pool
from encryption_helpers import (
    encrypt_password_hash,
    decrypt_password_hash,
    encrypt_token_hash,
    decrypt_token_hash,
    encrypt_api_key_hash,
    decrypt_api_key_hash,
    ENCRYPTION_ENABLED
)

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRATION_HOURS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRATION_HOURS", "1"))
JWT_REFRESH_TOKEN_EXPIRATION_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRATION_DAYS", "30"))

# Service-to-service authentication
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")  # Shared secret for service-to-service auth


class AuthenticationError(Exception):
    """Authentication error exception."""
    pass


class AuthorizationError(Exception):
    """Authorization error exception."""
    pass


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception as e:
        logger.error(f"Error verifying password: {e}", exc_info=True)
        return False


def hash_token(token: str) -> str:
    """Hash a token for storage (SHA-256)."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def generate_refresh_token() -> str:
    """Generate a secure random refresh token."""
    return secrets.token_urlsafe(64)


def create_access_token(user_id: str, roles: List[str] = None, permissions: List[str] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User identifier
        roles: List of role names
        permissions: List of permission names
        
    Returns:
        JWT token string
    """
    if not JWT_SECRET:
        raise AuthenticationError("JWT_SECRET not configured")
    
    payload = {
        "sub": user_id,  # Subject (user ID)
        "exp": datetime.utcnow() + timedelta(hours=JWT_ACCESS_TOKEN_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
        "jti": secrets.token_urlsafe(16),  # JWT ID
        "type": "access"
    }
    
    if roles:
        payload["roles"] = roles
    
    if permissions:
        payload["permissions"] = permissions
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT access token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload
        
    Raises:
        AuthenticationError: If token is invalid
    """
    if not JWT_SECRET:
        raise AuthenticationError("JWT_SECRET not configured")
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # Verify token type
        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")
        
        return payload
    except JWTError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")


def authenticate_user(username: str = None, password: str = None, user_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user with username/password or user_id.
    
    Args:
        username: Username for authentication
        password: Password for authentication
        user_id: User ID for authentication (external auth, no password)
        
    Returns:
        Dictionary with user_id, username, roles, and permissions if authentication succeeds, None otherwise
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build query based on provided credentials
            if username and password:
                # Username/password authentication
                cursor.execute(
                    """
                    SELECT u.id, u.user_id, u.username, u.password_hash, u.is_active
                    FROM users u
                    WHERE (u.username = %s OR u.user_id = %s) AND u.password_hash IS NOT NULL
                    """,
                    (username, username)
                )
            elif user_id:
                # User ID authentication (external auth, no password)
                cursor.execute(
                    """
                    SELECT u.id, u.user_id, u.username, u.password_hash, u.is_active
                    FROM users u
                    WHERE u.user_id = %s
                    """,
                    (user_id,)
                )
            else:
                return None
            
            result = cursor.fetchone()
            
            if not result:
                logger.warning(f"User not found: {username or user_id}")
                return None
            
            user_data = dict(result)
            
            # Decrypt password hash if encrypted
            if ENCRYPTION_ENABLED and user_data.get('password_hash'):
                try:
                    user_data['password_hash'] = decrypt_password_hash(user_data['password_hash'])
                except Exception as e:
                    logger.warning(f"Failed to decrypt password hash (may be unencrypted): {e}")
                    # Continue with original value (backward compatibility)
            
            # Verify password if provided
            if password and user_data['password_hash']:
                if not verify_password(password, user_data['password_hash']):
                    logger.warning(f"Invalid password for user: {username or user_id}")
                    return None
            
            # Check if user is active
            if not user_data.get('is_active', True):
                logger.warning(f"Inactive user: {username or user_id}")
                return None
            
            # Get user roles and permissions
            cursor.execute(
                """
                SELECT 
                    r.name as role_name,
                    p.name as permission_name
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.id
                JOIN roles r ON r.id = ur.role_id
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                LEFT JOIN permissions p ON p.id = rp.permission_id
                WHERE u.id = %s
                    AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
                """,
                (user_data['id'],)
            )
            
            roles = set()
            permissions = set()
            
            for row in cursor.fetchall():
                if row['role_name']:
                    roles.add(row['role_name'])
                if row['permission_name']:
                    permissions.add(row['permission_name'])
            
            # Update last login
            cursor.execute(
                "UPDATE users SET last_login = NOW() WHERE id = %s",
                (user_data['id'],)
            )
            conn.commit()
            
            return {
                'user_id': user_data['user_id'],
                'username': user_data.get('username') or user_data['user_id'],
                'roles': list(roles),
                'permissions': list(permissions)
            }
            
    except Exception as e:
        logger.error(f"Error authenticating user: {e}", exc_info=True)
        return None


def create_refresh_token(user_id: str, device_info: str = None, ip_address: str = None) -> tuple[str, str]:
    """
    Create and store a refresh token.
    
    Args:
        user_id: User identifier
        device_info: Device/browser information
        ip_address: IP address
        
    Returns:
        Tuple of (refresh_token, token_hash)
    """
    try:
        db_pool = get_db_pool()
        
        # Get user ID from users table
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT id FROM users WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            
            if not result:
                raise AuthenticationError(f"User not found: {user_id}")
            
            user_db_id = result['id']
        
        # Generate refresh token
        refresh_token = generate_refresh_token()
        token_hash = hash_token(refresh_token)
        
        # Encrypt token hash if encryption is enabled
        if ENCRYPTION_ENABLED:
            token_hash = encrypt_token_hash(token_hash)
        
        # Store refresh token
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, device_info, ip_address, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    user_db_id,
                    token_hash,
                    device_info,
                    ip_address,
                    datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRATION_DAYS)
                )
            )
            conn.commit()
        
        return refresh_token, token_hash
        
    except Exception as e:
        logger.error(f"Error creating refresh token: {e}", exc_info=True)
        raise AuthenticationError(f"Failed to create refresh token: {str(e)}")


def verify_refresh_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a refresh token and return user information.
    
    Args:
        refresh_token: Refresh token string
        
    Returns:
        Dictionary with user_id, username, roles, and permissions if token is valid, None otherwise
    """
    try:
        db_pool = get_db_pool()
        token_hash = hash_token(refresh_token)
        
        # Encrypt token hash for comparison if encryption is enabled
        search_token_hash = encrypt_token_hash(token_hash) if ENCRYPTION_ENABLED else token_hash
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT 
                    rt.user_id,
                    rt.token_hash,
                    rt.expires_at,
                    rt.revoked,
                    u.user_id as external_user_id,
                    u.username,
                    u.is_active
                FROM refresh_tokens rt
                JOIN users u ON u.id = rt.user_id
                WHERE rt.token_hash = %s
                    AND rt.revoked = FALSE
                    AND rt.expires_at > NOW()
                """,
                (search_token_hash,)
            )
            
            result = cursor.fetchone()
            
            if not result:
                # Try unencrypted lookup for backward compatibility
                if ENCRYPTION_ENABLED:
                    cursor.execute(
                        """
                        SELECT 
                            rt.user_id,
                            rt.token_hash,
                            rt.expires_at,
                            rt.revoked,
                            u.user_id as external_user_id,
                            u.username,
                            u.is_active
                        FROM refresh_tokens rt
                        JOIN users u ON u.id = rt.user_id
                        WHERE rt.token_hash = %s
                            AND rt.revoked = FALSE
                            AND rt.expires_at > NOW()
                        """,
                        (token_hash,)
                    )
                    result = cursor.fetchone()
            
            if not result:
                return None
            
            token_data = dict(result)
            
            # Check if user is active
            if not token_data.get('is_active', True):
                return None
            
            # Get user roles and permissions
            cursor.execute(
                """
                SELECT 
                    r.name as role_name,
                    p.name as permission_name
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.id
                JOIN roles r ON r.id = ur.role_id
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                LEFT JOIN permissions p ON p.id = rp.permission_id
                WHERE u.user_id = %s
                    AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
                """,
                (token_data['external_user_id'],)
            )
            
            roles = set()
            permissions = set()
            
            for row in cursor.fetchall():
                if row['role_name']:
                    roles.add(row['role_name'])
                if row['permission_name']:
                    permissions.add(row['permission_name'])
            
            return {
                'user_id': token_data['external_user_id'],
                'username': token_data.get('username') or token_data['external_user_id'],
                'roles': list(roles),
                'permissions': list(permissions)
            }
            
    except Exception as e:
        logger.error(f"Error verifying refresh token: {e}", exc_info=True)
        return None


def revoke_refresh_token(refresh_token: str) -> bool:
    """
    Revoke a refresh token.
    
    Args:
        refresh_token: Refresh token string to revoke
        
    Returns:
        True if token was revoked, False otherwise
    """
    try:
        db_pool = get_db_pool()
        token_hash = hash_token(refresh_token)
        
        # Encrypt token hash for comparison if encryption is enabled
        search_token_hash = encrypt_token_hash(token_hash) if ENCRYPTION_ENABLED else token_hash
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE refresh_tokens
                SET revoked = TRUE, revoked_at = NOW()
                WHERE token_hash = %s AND revoked = FALSE
                """,
                (search_token_hash,)
            )
            conn.commit()
            
            if cursor.rowcount == 0 and ENCRYPTION_ENABLED:
                # Try unencrypted lookup for backward compatibility
                cursor.execute(
                    """
                    UPDATE refresh_tokens
                    SET revoked = TRUE, revoked_at = NOW()
                    WHERE token_hash = %s AND revoked = FALSE
                    """,
                    (token_hash,)
                )
                conn.commit()
            
            return cursor.rowcount > 0
            
    except Exception as e:
        logger.error(f"Error revoking refresh token: {e}", exc_info=True)
        return False


def revoke_all_user_refresh_tokens(user_id: str) -> bool:
    """
    Revoke all refresh tokens for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        True if tokens were revoked, False otherwise
    """
    try:
        db_pool = get_db_pool()
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE refresh_tokens rt
                SET revoked = TRUE, revoked_at = NOW()
                FROM users u
                WHERE rt.user_id = u.id
                    AND u.user_id = %s
                    AND rt.revoked = FALSE
                """,
                (user_id,)
            )
            conn.commit()
            
            return cursor.rowcount > 0
            
    except Exception as e:
        logger.error(f"Error revoking user refresh tokens: {e}", exc_info=True)
        return False


def check_permission(user_id: str, permission: str) -> bool:
    """
    Check if a user has a specific permission.
    
    Args:
        user_id: User identifier
        permission: Permission name (e.g., 'users.read', 'admin.write')
        
    Returns:
        True if user has permission, False otherwise
    """
    try:
        db_pool = get_db_pool()
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.id
                JOIN roles r ON r.id = ur.role_id
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE u.user_id = %s
                    AND p.name = %s
                    AND u.is_active = TRUE
                    AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
                LIMIT 1
                """,
                (user_id, permission)
            )
            
            return cursor.fetchone() is not None
            
    except Exception as e:
        logger.error(f"Error checking permission: {e}", exc_info=True)
        return False


def check_role(user_id: str, role: str) -> bool:
    """
    Check if a user has a specific role.
    
    Args:
        user_id: User identifier
        role: Role name (e.g., 'admin', 'user')
        
    Returns:
        True if user has role, False otherwise
    """
    try:
        db_pool = get_db_pool()
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.id
                JOIN roles r ON r.id = ur.role_id
                WHERE u.user_id = %s
                    AND r.name = %s
                    AND u.is_active = TRUE
                    AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
                LIMIT 1
                """,
                (user_id, role)
            )
            
            return cursor.fetchone() is not None
            
    except Exception as e:
        logger.error(f"Error checking role: {e}", exc_info=True)
        return False


def get_user_permissions(user_id: str) -> Set[str]:
    """
    Get all permissions for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        Set of permission names
    """
    try:
        db_pool = get_db_pool()
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT p.name
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.id
                JOIN roles r ON r.id = ur.role_id
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE u.user_id = %s
                    AND u.is_active = TRUE
                    AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
                """,
                (user_id,)
            )
            
            return {row[0] for row in cursor.fetchall()}
            
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}", exc_info=True)
        return set()


def verify_service_token(api_key: str) -> bool:
    """
    Verify a service-to-service API key.
    
    Args:
        api_key: API key string
        
    Returns:
        True if API key is valid, False otherwise
    """
    if not SERVICE_API_KEY:
        logger.warning("SERVICE_API_KEY not configured")
        return False
    
    # Simple shared secret comparison (in production, use hashed keys in database)
    return api_key == SERVICE_API_KEY


def create_service_token(service_name: str) -> str:
    """
    Create a JWT token for service-to-service authentication.
    
    Args:
        service_name: Service name (e.g., 'inference-api', 'stt', 'tts')
        
    Returns:
        JWT token string
    """
    if not JWT_SECRET:
        raise AuthenticationError("JWT_SECRET not configured")
    
    payload = {
        "sub": f"service:{service_name}",
        "exp": datetime.utcnow() + timedelta(hours=24),  # Service tokens last 24 hours
        "iat": datetime.utcnow(),
        "jti": secrets.token_urlsafe(16),
        "type": "service",
        "service": service_name,
        "roles": ["service"]
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
