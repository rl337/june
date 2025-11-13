"""
Knowledge Graph Service - REST API and MCP endpoint for knowledge graph management.
"""
import os
import logging
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from database import KnowledgeGraphDatabase
from mcp_api import MCPKnowledgeGraphAPI, MCP_FUNCTIONS

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
db_path = os.getenv("KG_DB_PATH", "/app/data/kg.db")
db = KnowledgeGraphDatabase(db_path)

# Create FastAPI app
app = FastAPI(
    title="Knowledge Graph Service",
    description="Knowledge graph management service for AI agents",
    version="0.1.0"
)


# Pydantic models
class EntityCreate(BaseModel):
    entity_id: str = Field(..., description="Unique entity identifier")
    entity_type: str = Field(..., description="Entity type")
    name: str = Field(..., description="Entity name")
    description: Optional[str] = Field(None, description="Entity description")
    properties: Optional[Dict[str, Any]] = Field(None, description="Additional properties")


class RelationshipCreate(BaseModel):
    source_id: str = Field(..., description="Source entity ID")
    target_id: str = Field(..., description="Target entity ID")
    relationship_type: str = Field(..., description="Relationship type")
    properties: Optional[Dict[str, Any]] = Field(None, description="Relationship properties")


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
    return {"status": "healthy", "service": "knowledge-graph-service"}


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
        if method == "create_entity":
            result = MCPKnowledgeGraphAPI.create_entity(
                entity_id=params.get("entity_id"),
                entity_type=params.get("entity_type"),
                name=params.get("name"),
                description=params.get("description"),
                properties=params.get("properties")
            )
        elif method == "get_entity":
            result = MCPKnowledgeGraphAPI.get_entity(
                entity_id=params.get("entity_id")
            )
        elif method == "search_entities":
            result = MCPKnowledgeGraphAPI.search_entities(
                entity_type=params.get("entity_type"),
                name_pattern=params.get("name_pattern"),
                limit=params.get("limit", 100)
            )
        elif method == "create_relationship":
            result = MCPKnowledgeGraphAPI.create_relationship(
                source_id=params.get("source_id"),
                target_id=params.get("target_id"),
                relationship_type=params.get("relationship_type"),
                properties=params.get("properties")
            )
        elif method == "get_entity_relationships":
            result = MCPKnowledgeGraphAPI.get_entity_relationships(
                entity_id=params.get("entity_id"),
                relationship_type=params.get("relationship_type"),
                direction=params.get("direction", "both")
            )
        elif method == "query_path":
            result = MCPKnowledgeGraphAPI.query_path(
                source_id=params.get("source_id"),
                target_id=params.get("target_id"),
                max_depth=params.get("max_depth", 3)
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
@app.post("/entities")
async def create_entity(entity: EntityCreate):
    """Create or update an entity."""
    try:
        result = db.create_entity(
            entity_id=entity.entity_id,
            entity_type=entity.entity_type,
            name=entity.name,
            description=entity.description,
            properties=entity.properties
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/entities/{entity_id}")
async def get_entity(entity_id: str):
    """Get an entity by ID."""
    entity = db.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return entity


@app.get("/entities")
async def search_entities(
    entity_type: Optional[str] = Query(None),
    name_pattern: Optional[str] = Query(None),
    limit: int = Query(100, le=1000)
):
    """Search entities."""
    entities = db.search_entities(entity_type, name_pattern, limit)
    return {"entities": entities, "count": len(entities)}


@app.post("/relationships")
async def create_relationship(relationship: RelationshipCreate):
    """Create a relationship."""
    try:
        result = db.create_relationship(
            source_id=relationship.source_id,
            target_id=relationship.target_id,
            relationship_type=relationship.relationship_type,
            properties=relationship.properties
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/entities/{entity_id}/relationships")
async def get_entity_relationships(
    entity_id: str,
    relationship_type: Optional[str] = Query(None),
    direction: str = Query("both")
):
    """Get relationships for an entity."""
    relationships = db.get_entity_relationships(entity_id, relationship_type, direction)
    return {"relationships": relationships, "count": len(relationships)}


@app.get("/paths")
async def query_path(
    source_id: str = Query(...),
    target_id: str = Query(...),
    max_depth: int = Query(3, le=10)
):
    """Find paths between two entities."""
    paths = db.query_path(source_id, target_id, max_depth)
    return {"paths": paths, "count": len(paths)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("KG_SERVICE_PORT", "8006"))
    uvicorn.run(app, host="0.0.0.0", port=port)
