"""
MCP (Model Context Protocol) API for Knowledge Graph service.
"""
import os
from typing import Optional, List, Dict, Any
from fastapi import HTTPException

from database import KnowledgeGraphDatabase

# Initialize database
db_path = os.getenv("KG_DB_PATH", "/app/data/kg.db")
db = KnowledgeGraphDatabase(db_path)


class MCPKnowledgeGraphAPI:
    """MCP API for Knowledge Graph service."""
    
    @staticmethod
    def create_entity(
        entity_id: str,
        entity_type: str,
        name: str,
        description: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create or update an entity in the knowledge graph."""
        try:
            entity = db.create_entity(entity_id, entity_type, name, description, properties)
            return {"success": True, "entity": entity}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_entity(entity_id: str) -> Dict[str, Any]:
        """Get an entity by ID."""
        entity = db.get_entity(entity_id)
        if entity:
            return {"success": True, "entity": entity}
        return {"success": False, "error": f"Entity {entity_id} not found"}
    
    @staticmethod
    def search_entities(
        entity_type: Optional[str] = None,
        name_pattern: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Search entities by type and/or name pattern."""
        try:
            entities = db.search_entities(entity_type, name_pattern, limit)
            return {"success": True, "entities": entities, "count": len(entities)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def create_relationship(
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a relationship between two entities."""
        try:
            relationship = db.create_relationship(source_id, target_id, relationship_type, properties)
            return {"success": True, "relationship": relationship}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_entity_relationships(
        entity_id: str,
        relationship_type: Optional[str] = None,
        direction: str = "both"
    ) -> Dict[str, Any]:
        """Get relationships for an entity."""
        try:
            relationships = db.get_entity_relationships(entity_id, relationship_type, direction)
            return {"success": True, "relationships": relationships, "count": len(relationships)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def query_path(
        source_id: str,
        target_id: str,
        max_depth: int = 3
    ) -> Dict[str, Any]:
        """Find paths between two entities."""
        try:
            paths = db.query_path(source_id, target_id, max_depth)
            return {"success": True, "paths": paths, "count": len(paths)}
        except Exception as e:
            return {"success": False, "error": str(e)}


# MCP function definitions for documentation
MCP_FUNCTIONS = [
    {
        "name": "create_entity",
        "description": "Create or update an entity in the knowledge graph",
        "parameters": {
            "entity_id": "str - Unique identifier for the entity",
            "entity_type": "str - Type of entity (e.g., 'person', 'concept', 'document')",
            "name": "str - Name of the entity",
            "description": "Optional[str] - Description of the entity",
            "properties": "Optional[Dict] - Additional properties as key-value pairs"
        }
    },
    {
        "name": "get_entity",
        "description": "Get an entity by ID",
        "parameters": {
            "entity_id": "str - Entity ID to retrieve"
        }
    },
    {
        "name": "search_entities",
        "description": "Search entities by type and/or name pattern",
        "parameters": {
            "entity_type": "Optional[str] - Filter by entity type",
            "name_pattern": "Optional[str] - Search pattern for entity name",
            "limit": "int - Maximum number of results (default: 100)"
        }
    },
    {
        "name": "create_relationship",
        "description": "Create a relationship between two entities",
        "parameters": {
            "source_id": "str - Source entity ID",
            "target_id": "str - Target entity ID",
            "relationship_type": "str - Type of relationship (e.g., 'related_to', 'depends_on')",
            "properties": "Optional[Dict] - Additional relationship properties"
        }
    },
    {
        "name": "get_entity_relationships",
        "description": "Get relationships for an entity",
        "parameters": {
            "entity_id": "str - Entity ID",
            "relationship_type": "Optional[str] - Filter by relationship type",
            "direction": "str - 'outgoing', 'incoming', or 'both' (default: 'both')"
        }
    },
    {
        "name": "query_path",
        "description": "Find paths between two entities",
        "parameters": {
            "source_id": "str - Source entity ID",
            "target_id": "str - Target entity ID",
            "max_depth": "int - Maximum path depth (default: 3)"
        }
    }
]
