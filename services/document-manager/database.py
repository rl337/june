"""
Database schema and management for Document Manager service.
"""
import sqlite3
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import json
import hashlib

logger = logging.getLogger(__name__)


class DocumentManagerDatabase:
    """SQLite database for Document management."""
    
    def __init__(self, db_path: str):
        """Initialize database connection and create schema if needed."""
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_schema()
    
    def _ensure_db_directory(self):
        """Ensure database directory exists."""
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def _init_schema(self):
        """Initialize database schema."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Documents table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_type TEXT DEFAULT 'text/plain',
                    metadata TEXT,  -- JSON
                    tags TEXT,  -- JSON array
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1
                )
            """)
            
            # Document versions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_type TEXT,
                    metadata TEXT,  -- JSON
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                    UNIQUE(document_id, version)
                )
            """)
            
            # Document search index (full-text search)
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(
                    document_id,
                    title,
                    content,
                    content='documents',
                    content_rowid='rowid'
                )
            """)
            
            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_versions_doc ON document_versions(document_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_versions_version ON document_versions(document_id, version)")
            
            conn.commit()
            logger.info(f"Document Manager database schema initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise
        finally:
            conn.close()
    
    def _generate_document_id(self, title: str, content: str) -> str:
        """Generate a deterministic document ID from title and content."""
        content_hash = hashlib.sha256(f"{title}:{content}".encode()).hexdigest()[:16]
        return f"doc_{content_hash}"
    
    def create_document(
        self,
        document_id: Optional[str] = None,
        title: str = "",
        content: str = "",
        content_type: str = "text/plain",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create or update a document."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Generate ID if not provided
            if not document_id:
                document_id = self._generate_document_id(title, content)
            
            # Check if document exists
            existing = self.get_document(document_id)
            if existing:
                # Update existing document and create new version
                version = existing.get("version", 1) + 1
                cursor.execute("""
                    UPDATE documents 
                    SET title = ?, content = ?, content_type = ?, metadata = ?, tags = ?, 
                        updated_at = CURRENT_TIMESTAMP, version = ?
                    WHERE id = ?
                """, (
                    title, content, content_type,
                    json.dumps(metadata or {}),
                    json.dumps(tags or []),
                    version,
                    document_id
                ))
                
                # Save previous version
                cursor.execute("""
                    INSERT INTO document_versions 
                    (document_id, version, title, content, content_type, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    document_id, existing.get("version", 1),
                    existing.get("title"), existing.get("content"),
                    existing.get("content_type"), existing.get("metadata")
                ))
            else:
                # Create new document
                version = 1
                cursor.execute("""
                    INSERT INTO documents 
                    (id, title, content, content_type, metadata, tags, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    document_id, title, content, content_type,
                    json.dumps(metadata or {}),
                    json.dumps(tags or []),
                    version
                ))
            
            # Update full-text search index
            cursor.execute("""
                INSERT OR REPLACE INTO document_search (rowid, document_id, title, content)
                VALUES ((SELECT rowid FROM documents WHERE id = ?), ?, ?, ?)
            """, (document_id, document_id, title, content))
            
            conn.commit()
            return self.get_document(document_id)
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            raise
        finally:
            conn.close()
    
    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
            row = cursor.fetchone()
            if row:
                doc = dict(row)
                if doc.get("metadata"):
                    doc["metadata"] = json.loads(doc["metadata"])
                if doc.get("tags"):
                    doc["tags"] = json.loads(doc["tags"])
                return doc
            return None
        finally:
            conn.close()
    
    def get_document_version(self, document_id: str, version: int) -> Optional[Dict[str, Any]]:
        """Get a specific version of a document."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM document_versions 
                WHERE document_id = ? AND version = ?
            """, (document_id, version))
            row = cursor.fetchone()
            if row:
                doc = dict(row)
                if doc.get("metadata"):
                    doc["metadata"] = json.loads(doc["metadata"])
                return doc
            return None
        finally:
            conn.close()
    
    def search_documents(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search documents using full-text search and filters."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if query:
                # Full-text search
                cursor.execute("""
                    SELECT d.* FROM documents d
                    JOIN document_search ds ON d.id = ds.document_id
                    WHERE document_search MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, limit))
            else:
                # No query, just filter by tags/content_type
                sql = "SELECT * FROM documents WHERE 1=1"
                params = []
                
                if tags:
                    # SQLite JSON array search
                    for tag in tags:
                        sql += " AND json_array_length(json_extract(tags, '$')) > 0"
                        # This is simplified - for production, use proper JSON queries
                
                if content_type:
                    sql += " AND content_type = ?"
                    params.append(content_type)
                
                sql += " ORDER BY updated_at DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(sql, params)
            
            rows = cursor.fetchall()
            documents = []
            for row in rows:
                doc = dict(row)
                if doc.get("metadata"):
                    doc["metadata"] = json.loads(doc["metadata"])
                if doc.get("tags"):
                    doc["tags"] = json.loads(doc["tags"])
                documents.append(doc)
            
            return documents
        finally:
            conn.close()
    
    def list_documents(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List documents with pagination."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM documents 
                ORDER BY updated_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            rows = cursor.fetchall()
            documents = []
            for row in rows:
                doc = dict(row)
                if doc.get("metadata"):
                    doc["metadata"] = json.loads(doc["metadata"])
                if doc.get("tags"):
                    doc["tags"] = json.loads(doc["tags"])
                documents.append(doc)
            
            return documents
        finally:
            conn.close()
    
    def delete_document(self, document_id: str) -> bool:
        """Delete a document and all its versions."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
