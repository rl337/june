"""
MCP (Model Context Protocol) API for Document Manager service.
"""
import os
from typing import Optional, List, Dict, Any
from fastapi import HTTPException

from database import DocumentManagerDatabase

# Initialize database
db_path = os.getenv("DOC_DB_PATH", "/app/data/documents.db")
db = DocumentManagerDatabase(db_path)


class MCPDocumentManagerAPI:
    """MCP API for Document Manager service."""
    
    @staticmethod
    def create_document(
        document_id: Optional[str] = None,
        title: str = "",
        content: str = "",
        content_type: str = "text/plain",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create or update a document."""
        try:
            document = db.create_document(
                document_id=document_id,
                title=title,
                content=content,
                content_type=content_type,
                metadata=metadata,
                tags=tags
            )
            return {"success": True, "document": document}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_document(document_id: str) -> Dict[str, Any]:
        """Get a document by ID."""
        document = db.get_document(document_id)
        if document:
            return {"success": True, "document": document}
        return {"success": False, "error": f"Document {document_id} not found"}
    
    @staticmethod
    def get_document_version(document_id: str, version: int) -> Dict[str, Any]:
        """Get a specific version of a document."""
        document = db.get_document_version(document_id, version)
        if document:
            return {"success": True, "document": document}
        return {"success": False, "error": f"Document version {document_id}:{version} not found"}
    
    @staticmethod
    def search_documents(
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Search documents."""
        try:
            documents = db.search_documents(query, tags, content_type, limit)
            return {"success": True, "documents": documents, "count": len(documents)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def list_documents(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List documents with pagination."""
        try:
            documents = db.list_documents(limit, offset)
            return {"success": True, "documents": documents, "count": len(documents)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def delete_document(document_id: str) -> Dict[str, Any]:
        """Delete a document."""
        try:
            success = db.delete_document(document_id)
            if success:
                return {"success": True, "message": f"Document {document_id} deleted"}
            return {"success": False, "error": f"Document {document_id} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# MCP function definitions for documentation
MCP_FUNCTIONS = [
    {
        "name": "create_document",
        "description": "Create or update a document",
        "parameters": {
            "document_id": "Optional[str] - Document ID (auto-generated if not provided)",
            "title": "str - Document title",
            "content": "str - Document content",
            "content_type": "str - Content type (default: 'text/plain')",
            "metadata": "Optional[Dict] - Additional metadata",
            "tags": "Optional[List[str]] - Document tags"
        }
    },
    {
        "name": "get_document",
        "description": "Get a document by ID",
        "parameters": {
            "document_id": "str - Document ID"
        }
    },
    {
        "name": "get_document_version",
        "description": "Get a specific version of a document",
        "parameters": {
            "document_id": "str - Document ID",
            "version": "int - Version number"
        }
    },
    {
        "name": "search_documents",
        "description": "Search documents using full-text search",
        "parameters": {
            "query": "Optional[str] - Full-text search query",
            "tags": "Optional[List[str]] - Filter by tags",
            "content_type": "Optional[str] - Filter by content type",
            "limit": "int - Maximum results (default: 100)"
        }
    },
    {
        "name": "list_documents",
        "description": "List documents with pagination",
        "parameters": {
            "limit": "int - Maximum results (default: 100)",
            "offset": "int - Pagination offset (default: 0)"
        }
    },
    {
        "name": "delete_document",
        "description": "Delete a document",
        "parameters": {
            "document_id": "str - Document ID to delete"
        }
    }
]
