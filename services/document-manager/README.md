# Document Manager Service

MCP service for managing documents. Provides document storage, versioning, search, and retrieval capabilities for AI agents.

## Features

- **Document Management**: Create, update, and delete documents
- **Version Control**: Automatic versioning of document changes
- **Full-Text Search**: Search documents by content
- **Tagging**: Organize documents with tags
- **Metadata**: Store additional metadata with documents
- **MCP Protocol**: Full MCP (Model Context Protocol) support for agent integration

## API Endpoints

### MCP Endpoint
- `POST /mcp` - MCP JSON-RPC endpoint
- `GET /mcp/functions` - List available MCP functions

### REST API
- `POST /documents` - Create or update a document
- `GET /documents/{document_id}` - Get a document by ID
- `GET /documents/{document_id}/versions/{version}` - Get a specific version
- `GET /documents` - Search documents (query params: `query`, `tags`, `content_type`, `limit`)
- `DELETE /documents/{document_id}` - Delete a document
- `GET /health` - Health check

## MCP Functions

1. `create_document` - Create or update a document
2. `get_document` - Get a document by ID
3. `get_document_version` - Get a specific version of a document
4. `search_documents` - Search documents using full-text search
5. `list_documents` - List documents with pagination
6. `delete_document` - Delete a document

## Environment Variables

- `DOC_DB_PATH` - Path to SQLite database (default: `/app/data/documents.db`)
- `DOC_SERVICE_PORT` - Service port (default: `8007`)

## Usage

The service runs on port 8007 by default and provides both REST API and MCP endpoints for agent integration.
