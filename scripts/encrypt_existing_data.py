#!/usr/bin/env python3
"""
Migration script to encrypt existing sensitive data in the database.

This script:
1. Reads all sensitive fields from the database
2. Encrypts unencrypted values
3. Updates the database with encrypted values
4. Preserves already encrypted values (idempotent)

Usage:
    python scripts/encrypt_existing_data.py [--dry-run] [--table TABLE_NAME]
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "june-security"))

try:
    from june_security.db_encryption import DatabaseEncryption
    from june_security import get_encryption_manager
except ImportError as e:
    print(f"Error importing encryption modules: {e}")
    print("Make sure june-security package is installed: pip install -e packages/june-security")
    sys.exit(1)

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection."""
    postgres_url = os.getenv(
        "POSTGRES_URL",
        "postgresql://june:changeme@localhost:5432/june"
    )
    return psycopg2.connect(postgres_url)


def encrypt_table_data(conn, table_name: str, field_name: str, dry_run: bool = False):
    """
    Encrypt data in a specific table field.
    
    Args:
        conn: Database connection
        table_name: Table name
        field_name: Field name to encrypt
        dry_run: If True, don't actually update the database
    """
    db_encryption = DatabaseEncryption()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get all rows with non-null values
    cursor.execute(
        f"""
        SELECT id, {field_name}
        FROM {table_name}
        WHERE {field_name} IS NOT NULL
        """
    )
    
    rows = cursor.fetchall()
    logger.info(f"Found {len(rows)} rows in {table_name}.{field_name}")
    
    encrypted_count = 0
    already_encrypted_count = 0
    error_count = 0
    
    for row in rows:
        row_id = row['id']
        value = row[field_name]
        
        # Skip if already encrypted
        if db_encryption.is_encrypted(value):
            already_encrypted_count += 1
            continue
        
        try:
            # Encrypt the value
            encrypted_value = db_encryption.encrypt_field(value)
            
            if not dry_run:
                # Update the database
                update_cursor = conn.cursor()
                update_cursor.execute(
                    f"UPDATE {table_name} SET {field_name} = %s WHERE id = %s",
                    (encrypted_value, row_id)
                )
                update_cursor.close()
            
            encrypted_count += 1
            logger.debug(f"Encrypted {table_name}.{field_name} for row {row_id}")
            
        except Exception as e:
            error_count += 1
            logger.error(f"Error encrypting {table_name}.{field_name} for row {row_id}: {e}")
    
    if not dry_run:
        conn.commit()
    
    logger.info(
        f"{table_name}.{field_name}: "
        f"Encrypted {encrypted_count}, "
        f"Already encrypted {already_encrypted_count}, "
        f"Errors {error_count}"
    )
    
    return encrypted_count, already_encrypted_count, error_count


def main():
    parser = argparse.ArgumentParser(description="Encrypt existing database data")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually update the database")
    parser.add_argument("--table", help="Only encrypt data in this table")
    args = parser.parse_args()
    
    # Check encryption key
    if not os.getenv("ENCRYPTION_KEY"):
        logger.error("ENCRYPTION_KEY environment variable must be set")
        sys.exit(1)
    
    # Verify encryption works
    try:
        encryption_manager = get_encryption_manager()
        test_encrypted = encryption_manager.encrypt("test")
        test_decrypted = encryption_manager.decrypt(test_encrypted)
        assert test_decrypted == "test"
        logger.info("Encryption key verified")
    except Exception as e:
        logger.error(f"Encryption key verification failed: {e}")
        sys.exit(1)
    
    # Tables and fields to encrypt
    tables_to_encrypt = {
        "users": ["password_hash"],
        "admin_users": ["password_hash"],
        "refresh_tokens": ["token_hash"],
        "service_accounts": ["api_key_hash"],
        "bot_config": ["bot_token"],
    }
    
    if args.table:
        if args.table not in tables_to_encrypt:
            logger.error(f"Table {args.table} not found in encryption list")
            sys.exit(1)
        tables_to_encrypt = {args.table: tables_to_encrypt[args.table]}
    
    conn = None
    try:
        conn = get_db_connection()
        logger.info("Connected to database")
        
        total_encrypted = 0
        total_already_encrypted = 0
        total_errors = 0
        
        for table_name, fields in tables_to_encrypt.items():
            for field_name in fields:
                encrypted, already_encrypted, errors = encrypt_table_data(
                    conn, table_name, field_name, dry_run=args.dry_run
                )
                total_encrypted += encrypted
                total_already_encrypted += already_encrypted
                total_errors += errors
        
        logger.info(
            f"\nSummary:\n"
            f"  Encrypted: {total_encrypted}\n"
            f"  Already encrypted: {total_already_encrypted}\n"
            f"  Errors: {total_errors}"
        )
        
        if args.dry_run:
            logger.info("\nDRY RUN - No changes were made to the database")
            logger.info("Run without --dry-run to actually encrypt the data")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
