"""
Database schema and management for Knowledge Graph service.
"""
import sqlite3
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class KnowledgeGraphDatabase:
    """SQLite database for Knowledge Graph management."""
    
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
            
            # Entities table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    properties TEXT,  -- JSON
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Relationships table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    properties TEXT,  -- JSON
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE,
                    UNIQUE(source_id, target_id, relationship_type)
                )
            """)
            
            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type)")
            
            conn.commit()
            logger.info(f"Knowledge Graph database schema initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise
        finally:
            conn.close()
    
    def create_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        description: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create or update an entity."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            properties_json = json.dumps(properties or {})
            
            cursor.execute("""
                INSERT OR REPLACE INTO entities (id, type, name, description, properties, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (entity_id, entity_type, name, description, properties_json))
            
            conn.commit()
            return self.get_entity(entity_id)
        except Exception as e:
            logger.error(f"Failed to create entity: {e}")
            raise
        finally:
            conn.close()
    
    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get an entity by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
            row = cursor.fetchone()
            if row:
                entity = dict(row)
                if entity.get("properties"):
                    entity["properties"] = json.loads(entity["properties"])
                return entity
            return None
        finally:
            conn.close()
    
    def search_entities(
        self,
        entity_type: Optional[str] = None,
        name_pattern: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search entities by type and/or name pattern."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM entities WHERE 1=1"
            params = []
            
            if entity_type:
                query += " AND type = ?"
                params.append(entity_type)
            
            if name_pattern:
                query += " AND name LIKE ?"
                params.append(f"%{name_pattern}%")
            
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            entities = []
            for row in rows:
                entity = dict(row)
                if entity.get("properties"):
                    entity["properties"] = json.loads(entity["properties"])
                entities.append(entity)
            
            return entities
        finally:
            conn.close()
    
    def create_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create or update a relationship."""
        conn = self._get_connection()
        try:
            # Verify entities exist
            if not self.get_entity(source_id):
                raise ValueError(f"Source entity {source_id} not found")
            if not self.get_entity(target_id):
                raise ValueError(f"Target entity {target_id} not found")
            
            cursor = conn.cursor()
            properties_json = json.dumps(properties or {})
            
            cursor.execute("""
                INSERT OR REPLACE INTO relationships 
                (source_id, target_id, relationship_type, properties, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (source_id, target_id, relationship_type, properties_json))
            
            conn.commit()
            return self.get_relationship(cursor.lastrowid)
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            raise
        finally:
            conn.close()
    
    def get_relationship(self, relationship_id: int) -> Optional[Dict[str, Any]]:
        """Get a relationship by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM relationships WHERE id = ?", (relationship_id,))
            row = cursor.fetchone()
            if row:
                rel = dict(row)
                if rel.get("properties"):
                    rel["properties"] = json.loads(rel["properties"])
                return rel
            return None
        finally:
            conn.close()
    
    def get_entity_relationships(
        self,
        entity_id: str,
        relationship_type: Optional[str] = None,
        direction: str = "both"  # "outgoing", "incoming", "both"
    ) -> List[Dict[str, Any]]:
        """Get relationships for an entity."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            relationships = []
            
            if direction in ("outgoing", "both"):
                query = "SELECT * FROM relationships WHERE source_id = ?"
                params = [entity_id]
                if relationship_type:
                    query += " AND relationship_type = ?"
                    params.append(relationship_type)
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    rel = dict(row)
                    if rel.get("properties"):
                        rel["properties"] = json.loads(rel["properties"])
                    relationships.append(rel)
            
            if direction in ("incoming", "both"):
                query = "SELECT * FROM relationships WHERE target_id = ?"
                params = [entity_id]
                if relationship_type:
                    query += " AND relationship_type = ?"
                    params.append(relationship_type)
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    rel = dict(row)
                    if rel.get("properties"):
                        rel["properties"] = json.loads(rel["properties"])
                    relationships.append(rel)
            
            return relationships
        finally:
            conn.close()
    
    def query_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 3
    ) -> List[List[Dict[str, Any]]]:
        """Find paths between two entities (simple BFS implementation)."""
        # This is a simplified path finding - for production, consider using a graph library
        paths = []
        visited = set()
        queue = [(source_id, [source_id])]
        
        while queue and len(paths) < 10:  # Limit to 10 paths
            current_id, path = queue.pop(0)
            
            if current_id == target_id and len(path) > 1:
                # Reconstruct full path with relationships
                full_path = []
                for i in range(len(path) - 1):
                    rels = self.get_entity_relationships(path[i], direction="outgoing")
                    for rel in rels:
                        if rel["target_id"] == path[i + 1]:
                            full_path.append({
                                "entity": self.get_entity(path[i]),
                                "relationship": rel,
                                "target_entity": self.get_entity(path[i + 1])
                            })
                            break
                if full_path:
                    paths.append(full_path)
                continue
            
            if len(path) >= max_depth:
                continue
            
            key = (current_id, tuple(path))
            if key in visited:
                continue
            visited.add(key)
            
            # Get outgoing relationships
            rels = self.get_entity_relationships(current_id, direction="outgoing")
            for rel in rels:
                next_id = rel["target_id"]
                if next_id not in path:  # Avoid cycles
                    queue.append((next_id, path + [next_id]))
        
        return paths
