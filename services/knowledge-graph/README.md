# Knowledge Graph Service

MCP service for managing knowledge graphs. Provides entities, relationships, and path querying capabilities for AI agents.

## Features

- **Entity Management**: Create, update, and search entities
- **Relationship Management**: Create relationships between entities
- **Path Querying**: Find paths between entities in the graph
- **MCP Protocol**: Full MCP (Model Context Protocol) support for agent integration

## API Endpoints

### MCP Endpoint
- `POST /mcp` - MCP JSON-RPC endpoint
- `GET /mcp/functions` - List available MCP functions

### REST API
- `POST /entities` - Create or update an entity
- `GET /entities/{entity_id}` - Get an entity by ID
- `GET /entities` - Search entities (query params: `entity_type`, `name_pattern`, `limit`)
- `POST /relationships` - Create a relationship
- `GET /entities/{entity_id}/relationships` - Get relationships for an entity
- `GET /paths` - Find paths between entities (query params: `source_id`, `target_id`, `max_depth`)
- `GET /health` - Health check

## MCP Functions

1. `create_entity` - Create or update an entity
2. `get_entity` - Get an entity by ID
3. `search_entities` - Search entities by type and/or name
4. `create_relationship` - Create a relationship between entities
5. `get_entity_relationships` - Get relationships for an entity
6. `query_path` - Find paths between two entities

## Environment Variables

- `KG_DB_PATH` - Path to SQLite database (default: `/app/data/kg.db`)
- `KG_SERVICE_PORT` - Service port (default: `8006`)

## Usage

The service runs on port 8006 by default and provides both REST API and MCP endpoints for agent integration.
