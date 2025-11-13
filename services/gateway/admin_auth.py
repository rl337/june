"""Admin authentication module for Gateway service."""
import os
import logging
import psycopg2
import bcrypt
from typing import Optional, Dict, Any
from psycopg2.extras import RealDictCursor
from db_pool import get_db_pool
from encryption_helpers import (
    encrypt_password_hash,
    decrypt_password_hash,
    ENCRYPTION_ENABLED
)

logger = logging.getLogger(__name__)


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


def authenticate_admin(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate an admin user with username and password.
    
    Args:
        username: Admin username
        password: Admin password
        
    Returns:
        Dictionary with user_id and username if authentication succeeds, None otherwise
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            # Try to find admin by username or user_id
            cursor.execute(
                """
                SELECT id, user_id, username, password_hash
                FROM admin_users
                WHERE (username = %s OR user_id = %s) AND password_hash IS NOT NULL
                """,
                (username, username)
            )
            result = cursor.fetchone()
            
            if not result:
                logger.warning(f"Admin user not found: {username}")
                return None
            
            admin_data = dict(result)
            
            # Decrypt password hash if encrypted
            if ENCRYPTION_ENABLED and admin_data.get('password_hash'):
                try:
                    admin_data['password_hash'] = decrypt_password_hash(admin_data['password_hash'])
                except Exception as e:
                    logger.warning(f"Failed to decrypt password hash (may be unencrypted): {e}")
                    # Continue with original value (backward compatibility)
            
            # Verify password
            if not verify_password(password, admin_data['password_hash']):
                logger.warning(f"Invalid password for admin: {username}")
                return None
            
            return {
                'user_id': admin_data['user_id'],
                'username': admin_data.get('username') or admin_data['user_id']
            }
    except Exception as e:
        logger.error(f"Error authenticating admin {username}: {e}", exc_info=True)
        return None


def is_admin(user_id: str) -> bool:
    """
    Check if a user is an admin.
    
    Args:
        user_id: User ID to check
        
    Returns:
        True if user is admin, False otherwise
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM admin_users WHERE user_id = %s",
                (str(user_id),)
            )
            result = cursor.fetchone()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}", exc_info=True)
        return False


def create_admin_user(user_id: str, username: Optional[str] = None, password: Optional[str] = None) -> bool:
    """
    Create a new admin user.
    
    Args:
        user_id: User ID (required)
        username: Admin username (optional)
        password: Admin password (optional, will be hashed)
        
    Returns:
        True if admin was created, False otherwise
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            password_hash = hash_password(password) if password else None
            
            # Encrypt password hash if encryption is enabled
            if ENCRYPTION_ENABLED and password_hash:
                password_hash = encrypt_password_hash(password_hash)
            
            cursor.execute(
                """
                INSERT INTO admin_users (user_id, username, password_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username,
                    password_hash = COALESCE(EXCLUDED.password_hash, admin_users.password_hash),
                    updated_at = NOW()
                RETURNING id
                """,
                (str(user_id), username, password_hash)
            )
            result = cursor.fetchone()
            conn.commit()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error creating admin user {user_id}: {e}", exc_info=True)
        return False


def update_admin_password(user_id: str, new_password: str) -> bool:
    """
    Update an admin user's password.
    
    Args:
        user_id: Admin user ID
        new_password: New password (will be hashed)
        
    Returns:
        True if password was updated, False otherwise
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            password_hash = hash_password(new_password)
            
            # Encrypt password hash if encryption is enabled
            if ENCRYPTION_ENABLED:
                password_hash = encrypt_password_hash(password_hash)
            
            cursor.execute(
                """
                UPDATE admin_users
                SET password_hash = %s, updated_at = NOW()
                WHERE user_id = %s
                RETURNING id
                """,
                (password_hash, str(user_id))
            )
            result = cursor.fetchone()
            conn.commit()
            return result is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error updating password for admin {user_id}: {e}", exc_info=True)
        return False
