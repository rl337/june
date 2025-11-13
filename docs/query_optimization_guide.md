# Database Query Optimization Guide

This document describes the optimizations applied to PostgreSQL queries and provides guidance for writing efficient queries.

## Overview

Database query optimization was performed across Gateway and Inference API services to improve performance for the 10x capacity target. The optimizations focus on:

1. **Conversation and message queries** - Most frequent queries in Gateway service
2. **RAG document retrieval** - Vector similarity searches in Inference API
3. **Analytics queries** - Complex aggregations and date filtering
4. **Full-text search** - Replacing slow ILIKE queries with indexed full-text search

## Optimizations Applied

### 1. Indexes Created

#### Conversation Indexes
- `idx_conversations_updated_at` - Optimizes conversation listing ordered by updated_at
- `idx_conversations_user_id_created_at` - Optimizes user-specific queries with date filtering
- `idx_conversations_created_at_range` - Partial index for recent conversations (last 90 days)
- `idx_conversations_user_id_gin` - GIN index for fast user_id pattern matching

#### Message Indexes
- `idx_messages_conversation_id_created_at` - Optimizes message retrieval by conversation
- `idx_messages_role_created_at` - Optimizes role-based queries (response time calculations)
- `idx_messages_content_gin` - Full-text search index for message content
- `idx_messages_conversation_role_created_at` - Composite index for conversation + role queries

#### RAG Indexes
- `idx_documents_id_btree` - Ensures fast document retrieval by ID
- `idx_documents_id_hash` - Hash index for ANY() queries with document IDs
- `idx_documents_metadata_gin` - GIN index for JSONB metadata queries
- `idx_documents_source_url` - Index for source URL lookups

#### Analytics Indexes
- `idx_cost_tracking_user_id_created_at` - Optimizes cost queries by user and date
- `idx_cost_tracking_service_created_at` - Optimizes cost queries by service
- `idx_conversations_date_trunc_created_at` - Optimizes date aggregations
- `idx_conversations_date_trunc_updated_at` - Optimizes date aggregations on updated_at

### 2. Extensions Enabled

- **pg_trgm** - Enables trigram-based text pattern matching for fast ILIKE-like queries

## Query Rewrite Recommendations

### Replace ILIKE with Full-Text Search

**Before (Slow):**
```sql
SELECT * FROM messages 
WHERE content ILIKE '%search term%'
```

**After (Fast):**
```sql
SELECT * FROM messages 
WHERE to_tsvector('english', content) @@ plainto_tsquery('english', 'search term')
ORDER BY ts_rank(to_tsvector('english', content), plainto_tsquery('english', 'search term')) DESC
```

**Benefits:**
- Uses GIN index (`idx_messages_content_gin`) for fast search
- Supports ranking by relevance
- Handles multiple words and stemming

### Replace User ID ILIKE with Trigram Matching

**Before (Slow):**
```sql
SELECT * FROM conversations 
WHERE user_id ILIKE '%pattern%'
```

**After (Fast):**
```sql
SELECT * FROM conversations 
WHERE user_id % 'pattern'  -- Trigram similarity operator
ORDER BY similarity(user_id, 'pattern') DESC
```

**Benefits:**
- Uses GIN index (`idx_conversations_user_id_gin`) for fast pattern matching
- Supports fuzzy matching with similarity scoring

### Optimize RAG Document Retrieval

**Current (Acceptable):**
```sql
SELECT d.id, d.title, d.content, d.source_url, d.metadata
FROM documents d
WHERE d.id = ANY(:document_ids)
```

**Optimization Notes:**
- The `ANY()` operator works well with the primary key index
- For small lists (< 10 items), `IN` clause may be slightly faster
- For large lists, `ANY()` is more efficient
- Hash index (`idx_documents_id_hash`) provides additional optimization

**Alternative for Small Lists:**
```sql
SELECT d.id, d.title, d.content, d.source_url, d.metadata
FROM documents d
WHERE d.id IN (:id1, :id2, :id3, ...)
```

### Optimize Conversation Listing with Message Counts

**Current Query:**
```sql
SELECT 
    c.id,
    c.user_id,
    c.session_id,
    c.created_at,
    c.updated_at,
    c.metadata,
    COUNT(DISTINCT m.id) as message_count,
    MIN(m.created_at) as first_message_at,
    MAX(m.created_at) as last_message_at
FROM conversations c
LEFT JOIN messages m ON m.conversation_id = c.id
WHERE c.updated_at >= NOW() - INTERVAL '30 days'
GROUP BY c.id, c.user_id, c.session_id, c.created_at, c.updated_at, c.metadata
ORDER BY c.updated_at DESC
LIMIT 20
```

**Optimization:**
- Uses `idx_conversations_updated_at` for WHERE and ORDER BY
- Uses `idx_messages_conversation_id_created_at` for JOIN
- Consider materialized view for frequently accessed conversation summaries

### Optimize Response Time Calculations

**Current Query:**
```sql
SELECT 
    AVG(EXTRACT(EPOCH FROM (m.created_at - prev_msg.created_at))) as avg_response_time
FROM messages m
JOIN messages prev_msg ON prev_msg.conversation_id = m.conversation_id
    AND prev_msg.created_at < m.created_at
    AND prev_msg.role = 'user'
WHERE m.role = 'assistant'
  AND m.created_at >= NOW() - INTERVAL '7 days'
```

**Optimization:**
- Uses `idx_messages_role_created_at` for filtering by role
- Uses `idx_messages_conversation_id_created_at` for JOIN
- Consider window functions for better performance:
```sql
SELECT 
    AVG(response_time) as avg_response_time
FROM (
    SELECT 
        conversation_id,
        EXTRACT(EPOCH FROM (
            created_at - LAG(created_at) OVER (
                PARTITION BY conversation_id 
                ORDER BY created_at
            )
        )) as response_time
    FROM messages
    WHERE role = 'assistant'
      AND created_at >= NOW() - INTERVAL '7 days'
) subq
WHERE response_time IS NOT NULL
```

## Performance Monitoring

### Check Index Usage

```sql
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```

### Check Slow Queries

Enable `log_min_duration_statement` in PostgreSQL config:
```sql
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries > 1 second
```

### Analyze Query Plans

Use EXPLAIN ANALYZE to verify index usage:
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) 
SELECT * FROM conversations WHERE updated_at >= NOW() - INTERVAL '30 days';
```

## Expected Performance Improvements

Based on the optimizations:

1. **Conversation listing queries**: 50-70% improvement with `idx_conversations_updated_at`
2. **Message retrieval**: 60-80% improvement with composite index on `(conversation_id, created_at)`
3. **Full-text search**: 90%+ improvement replacing ILIKE with GIN index
4. **User pattern matching**: 80%+ improvement with trigram index
5. **Analytics queries**: 40-60% improvement with date truncation indexes

## Maintenance

### Update Statistics

Run periodically to keep query planner informed:
```sql
ANALYZE conversations;
ANALYZE messages;
ANALYZE documents;
```

### Monitor Index Bloat

Check for index bloat and rebuild if necessary:
```sql
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Rebuild Indexes

If indexes become bloated:
```sql
REINDEX INDEX CONCURRENTLY idx_conversations_updated_at;
```

## Future Optimizations

1. **Partitioning**: Consider partitioning `conversations` and `messages` tables by date for better performance on large datasets
2. **Materialized Views**: Create materialized views for complex analytics queries
3. **Query Result Caching**: Implement Redis caching for frequently accessed conversation data (see task 469)
4. **Connection Pooling**: Ensure proper connection pooling configuration (see task 470)

## References

- PostgreSQL Index Types: https://www.postgresql.org/docs/current/indexes-types.html
- pg_trgm Extension: https://www.postgresql.org/docs/current/pgtrgm.html
- Full-Text Search: https://www.postgresql.org/docs/current/textsearch.html
- pgvector Documentation: https://github.com/pgvector/pgvector
