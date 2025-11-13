"""
Document Manager Service - REST API and MCP endpoint for document management.
"""
import os
import logging
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from database import DocumentManagerDatabase
from mcp_api import MCPDocumentManagerAPI, MCP_FUNCTIONS

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
db_path = os.getenv("DOC_DB_PATH", "/app/data/documents.db")
db = DocumentManagerDatabase(db_path)

# Create FastAPI app
app = FastAPI(
    title="Document Manager Service",
    description="Document management service for AI agents",
    version="0.1.0"
)


# Pydantic models
class DocumentCreate(BaseModel):
    document_id: Optional[str] = Field(None, description="Document ID (auto-generated if not provided)")
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Document content")
    content_type: str = Field("text/plain", description="Content type")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    tags: Optional[List[str]] = Field(None, description="Document tags")


class MCPRequest(BaseModel):
    """MCP JSON-RPC request model."""
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any] = {}
    id: Optional[str] = None


class MCPResponse(BaseModel):
    """MCP JSON-RPC response model."""
    jsonrpc: str = "2.0"
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[str] = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "document-manager-service"}


@app.get("/mcp/functions")
async def list_mcp_functions():
    """List available MCP functions."""
    return {"functions": MCP_FUNCTIONS}


@app.post("/mcp", response_model=MCPResponse)
async def mcp_endpoint(request: MCPRequest):
    """MCP JSON-RPC endpoint."""
    method = request.method
    params = request.params or {}
    
    try:
        if method == "create_document":
            result = MCPDocumentManagerAPI.create_document(
                document_id=params.get("document_id"),
                title=params.get("title", ""),
                content=params.get("content", ""),
                content_type=params.get("content_type", "text/plain"),
                metadata=params.get("metadata"),
                tags=params.get("tags")
            )
        elif method == "get_document":
            result = MCPDocumentManagerAPI.get_document(
                document_id=params.get("document_id")
            )
        elif method == "get_document_version":
            result = MCPDocumentManagerAPI.get_document_version(
                document_id=params.get("document_id"),
                version=params.get("version")
            )
        elif method == "search_documents":
            result = MCPDocumentManagerAPI.search_documents(
                query=params.get("query"),
                tags=params.get("tags"),
                content_type=params.get("content_type"),
                limit=params.get("limit", 100)
            )
        elif method == "list_documents":
            result = MCPDocumentManagerAPI.list_documents(
                limit=params.get("limit", 100),
                offset=params.get("offset", 0)
            )
        elif method == "delete_document":
            result = MCPDocumentManagerAPI.delete_document(
                document_id=params.get("document_id")
            )
        else:
            return MCPResponse(
                jsonrpc="2.0",
                error={"code": -32601, "message": f"Method not found: {method}"},
                id=request.id
            )
        
        return MCPResponse(jsonrpc="2.0", result=result, id=request.id)
    except Exception as e:
        logger.error(f"MCP error: {e}")
        return MCPResponse(
            jsonrpc="2.0",
            error={"code": -32603, "message": str(e)},
            id=request.id
        )


# REST API endpoints
@app.post("/documents")
async def create_document(document: DocumentCreate):
    """Create or update a document."""
    try:
        result = db.create_document(
            document_id=document.document_id,
            title=document.title,
            content=document.content,
            content_type=document.content_type,
            metadata=document.metadata,
            tags=document.tags
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/documents/{document_id}")
async def get_document(document_id: str):
    """Get a document by ID."""
    document = db.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return document


@app.get("/documents/{document_id}/versions/{version}")
async def get_document_version(document_id: str, version: int):
    """Get a specific version of a document."""
    document = db.get_document_version(document_id, version)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document version {document_id}:{version} not found")
    return document


@app.get("/documents")
async def search_documents(
    query: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),  # Comma-separated
    content_type: Optional[str] = Query(None),
    limit: int = Query(100, le=1000)
):
    """Search documents."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    documents = db.search_documents(query, tag_list, content_type, limit)
    return {"documents": documents, "count": len(documents)}


@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a document."""
    success = db.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return {"message": f"Document {document_id} deleted"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DOC_SERVICE_PORT", "8007"))
    uvicorn.run(app, host="0.0.0.0", port=port)
