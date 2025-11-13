-- Database Query Optimizations
-- This file contains indexes and optimizations for PostgreSQL queries
-- Run this after postgres-init.sql

-- ============================================================================
-- EXTENSIONS
-- ============================================================================

-- Enable pg_trgm for fast text pattern matching (replaces slow ILIKE)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- CONVERSATION QUERIES OPTIMIZATION
-- ============================================================================

-- Index for conversation listing ordered by updated_at (most common query)
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at 
    ON conversations(updated_at DESC);

-- Composite index for user-specific queries with date filtering
CREATE INDEX IF NOT EXISTS idx_conversations_user_id_created_at 
    ON conversations(user_id, created_at DESC);

-- Index for date range queries on conversations
CREATE INDEX IF NOT EXISTS idx_conversations_created_at_range 
    ON conversations(created_at) 
    WHERE created_at >= NOW() - INTERVAL '90 days';

-- ============================================================================
-- MESSAGE QUERIES OPTIMIZATION
-- ============================================================================

-- Composite index for message retrieval by conversation (most common query)
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_created_at 
    ON messages(conversation_id, created_at ASC);

-- Index for role-based queries (used in response time calculations)
CREATE INDEX IF NOT EXISTS idx_messages_role_created_at 
    ON messages(role, created_at) 
    WHERE role IN ('user', 'assistant');

-- Full-text search index for message content (replaces slow ILIKE)
CREATE INDEX IF NOT EXISTS idx_messages_content_gin 
    ON messages USING gin(to_tsvector('english', content));

-- Index for message search by conversation and role
CREATE INDEX IF NOT EXISTS idx_messages_conversation_role_created_at 
    ON messages(conversation_id, role, created_at);

-- ============================================================================
-- USER ID TEXT SEARCH OPTIMIZATION
-- ============================================================================

-- GIN index for fast user_id pattern matching (requires pg_trgm)
CREATE INDEX IF NOT EXISTS idx_conversations_user_id_gin 
    ON conversations USING gin(user_id gin_trgm_ops);

-- ============================================================================
-- RAG QUERIES OPTIMIZATION
-- ============================================================================

-- Ensure documents table has primary key index (should exist, but verify)
CREATE INDEX IF NOT EXISTS idx_documents_id_btree 
    ON documents(id);

-- Index for document retrieval by multiple IDs (optimizes ANY() queries)
-- Note: PostgreSQL should use the primary key index, but this ensures it
CREATE INDEX IF NOT EXISTS idx_documents_id_hash 
    ON documents USING hash(id);

-- Index for document metadata queries
CREATE INDEX IF NOT EXISTS idx_documents_metadata_gin 
    ON documents USING gin(metadata);

-- Index for document source URL lookups
CREATE INDEX IF NOT EXISTS idx_documents_source_url 
    ON documents(source_url) 
    WHERE source_url IS NOT NULL;

-- ============================================================================
-- ANALYTICS QUERIES OPTIMIZATION
-- ============================================================================

-- Index for cost tracking queries (user + date filtering)
CREATE INDEX IF NOT EXISTS idx_cost_tracking_user_id_created_at 
    ON cost_tracking(user_id, created_at DESC);

-- Index for cost tracking by service
CREATE INDEX IF NOT EXISTS idx_cost_tracking_service_created_at 
    ON cost_tracking(service, created_at DESC);

-- Index for analytics date aggregations
CREATE INDEX IF NOT EXISTS idx_conversations_date_trunc_created_at 
    ON conversations((DATE_TRUNC('day', created_at)));

-- Index for analytics date aggregations on updated_at
CREATE INDEX IF NOT EXISTS idx_conversations_date_trunc_updated_at 
    ON conversations((DATE_TRUNC('day', updated_at)));

-- ============================================================================
-- VECTOR SEARCH OPTIMIZATION (pgvector)
-- ============================================================================

-- Ensure HNSW indexes exist for vector similarity search
-- (These should already exist from postgres-init.sql, but verify)

-- Verify embeddings vector index
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE indexname = 'idx_embeddings_vector'
    ) THEN
        CREATE INDEX idx_embeddings_vector 
            ON embeddings USING hnsw (embedding vector_cosine_ops);
    END IF;
END $$;

-- Verify document_embeddings vector index
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE indexname = 'idx_document_embeddings_vector'
    ) THEN
        CREATE INDEX idx_document_embeddings_vector 
            ON document_embeddings USING hnsw (embedding vector_cosine_ops);
    END IF;
END $$;

-- ============================================================================
-- QUERY STATISTICS
-- ============================================================================

-- Update table statistics for better query planning
ANALYZE conversations;
ANALYZE messages;
ANALYZE documents;
ANALYZE document_embeddings;
ANALYZE cost_tracking;

-- ============================================================================
-- NOTES
-- ============================================================================

-- Query Rewrite Recommendations:
--
-- 1. Replace ILIKE with full-text search:
--    OLD: WHERE content ILIKE '%search%'
--    NEW: WHERE to_tsvector('english', content) @@ plainto_tsquery('english', 'search')
--
-- 2. Replace user_id ILIKE with trigram matching:
--    OLD: WHERE user_id ILIKE '%pattern%'
--    NEW: WHERE user_id % 'pattern'  (using pg_trgm similarity)
--
-- 3. Optimize RAG document retrieval:
--    OLD: WHERE d.id = ANY(:document_ids)
--    NEW: Use IN clause for small lists, or keep ANY() for large lists (index helps)
--
-- 4. Use covering indexes where possible:
--    Consider including frequently selected columns in indexes to avoid table lookups
