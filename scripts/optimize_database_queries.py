#!/usr/bin/env python3
"""
Database Query Optimization Script

Analyzes PostgreSQL queries across Gateway, Inference API, and TODO service.
Identifies slow queries, missing indexes, and optimization opportunities.
Applies optimizations and documents improvements.
"""
import os
import sys
import psycopg2
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get PostgreSQL database connection."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "conversations")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    
    conn_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
    if db_password:
        conn_string += f" password={db_password}"
    
    return psycopg2.connect(conn_string)


def explain_analyze_query(conn, query: str, params: tuple = None) -> Dict[str, Any]:
    """Run EXPLAIN ANALYZE on a query and return execution plan."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
        cursor.execute(explain_query, params)
        result = cursor.fetchone()
        if result and result[0]:
            plan = result[0][0]
            return {
                "plan": plan,
                "execution_time_ms": plan.get("Execution Time", 0) * 1000,  # Convert to ms
                "planning_time_ms": plan.get("Planning Time", 0) * 1000,
                "total_time_ms": (plan.get("Execution Time", 0) + plan.get("Planning Time", 0)) * 1000,
            }
        return {}
    except Exception as e:
        logger.error(f"Error running EXPLAIN ANALYZE: {e}")
        return {}
    finally:
        cursor.close()


def check_index_exists(conn, table_name: str, index_name: str) -> bool:
    """Check if an index exists."""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = %s AND indexname = %s
            )
        """, (table_name, index_name))
        return cursor.fetchone()[0]
    finally:
        cursor.close()


def create_index(conn, index_sql: str, index_name: str, table_name: str) -> bool:
    """Create an index if it doesn't exist."""
    if check_index_exists(conn, table_name, index_name):
        logger.info(f"Index {index_name} already exists, skipping")
        return False
    
    cursor = conn.cursor()
    try:
        cursor.execute(index_sql)
        conn.commit()
        logger.info(f"Created index: {index_name}")
        return True
    except Exception as e:
        logger.error(f"Error creating index {index_name}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()


def analyze_conversation_queries(conn) -> List[Dict[str, Any]]:
    """Analyze conversation-related queries."""
    results = []
    
    # Query 1: Get conversations with message counts (from conversation_management.py)
    query1 = """
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
    """
    
    logger.info("Analyzing conversation listing query...")
    plan1 = explain_analyze_query(conn, query1)
    results.append({
        "query_name": "conversation_listing_with_messages",
        "query": query1,
        "execution_plan": plan1
    })
    
    # Query 2: Search conversations with ILIKE (potentially slow)
    query2 = """
        SELECT DISTINCT c.id
        FROM conversations c
        WHERE c.user_id ILIKE '%test%'
           OR EXISTS (
               SELECT 1 FROM messages m 
               WHERE m.conversation_id = c.id 
               AND m.content ILIKE '%test%'
           )
        LIMIT 20
    """
    
    logger.info("Analyzing conversation search query...")
    plan2 = explain_analyze_query(conn, query2)
    results.append({
        "query_name": "conversation_search_ilike",
        "query": query2,
        "execution_plan": plan2
    })
    
    # Query 3: Get conversation with all messages
    query3 = """
        SELECT 
            c.id,
            c.user_id,
            c.session_id,
            c.created_at,
            c.updated_at,
            c.metadata,
            COUNT(DISTINCT m.id) as message_count
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.id
        WHERE c.id = '00000000-0000-0000-0000-000000000000'::uuid
        GROUP BY c.id, c.user_id, c.session_id, c.created_at, c.updated_at, c.metadata
    """
    
    logger.info("Analyzing single conversation query...")
    plan3 = explain_analyze_query(conn, query3)
    results.append({
        "query_name": "single_conversation_with_messages",
        "query": query3,
        "execution_plan": plan3
    })
    
    # Query 4: Get messages for a conversation
    query4 = """
        SELECT 
            id,
            role,
            content,
            created_at,
            metadata
        FROM messages
        WHERE conversation_id = '00000000-0000-0000-0000-000000000000'::uuid
        ORDER BY created_at ASC
    """
    
    logger.info("Analyzing messages query...")
    plan4 = explain_analyze_query(conn, query4)
    results.append({
        "query_name": "messages_by_conversation",
        "query": query4,
        "execution_plan": plan4
    })
    
    return results


def analyze_rag_queries(conn) -> List[Dict[str, Any]]:
    """Analyze RAG-related queries."""
    results = []
    
    # Query 1: RAG document retrieval (from inference-api/main.py)
    # Note: This uses ANY() which can be optimized
    query1 = """
        SELECT d.id, d.title, d.content, d.source_url, d.metadata
        FROM documents d
        WHERE d.id = ANY(ARRAY['00000000-0000-0000-0000-000000000000'::uuid]::uuid[])
    """
    
    logger.info("Analyzing RAG document retrieval query...")
    plan1 = explain_analyze_query(conn, query1)
    results.append({
        "query_name": "rag_document_retrieval",
        "query": query1,
        "execution_plan": plan1
    })
    
    # Query 2: Vector similarity search (pgvector)
    query2 = """
        SELECT 
            de.document_id,
            de.chunk_text,
            de.chunk_index,
            1 - (de.embedding <=> '[0.1,0.2,0.3]'::vector) as similarity
        FROM document_embeddings de
        ORDER BY de.embedding <=> '[0.1,0.2,0.3]'::vector
        LIMIT 10
    """
    
    logger.info("Analyzing vector similarity search query...")
    plan2 = explain_analyze_query(conn, query2)
    results.append({
        "query_name": "vector_similarity_search",
        "query": query2,
        "execution_plan": plan2
    })
    
    return results


def analyze_analytics_queries(conn) -> List[Dict[str, Any]]:
    """Analyze analytics queries."""
    results = []
    
    # Query 1: User analytics with date filtering
    query1 = """
        SELECT COUNT(DISTINCT user_id) as total_users
        FROM conversations c
        WHERE c.created_at >= NOW() - INTERVAL '30 days'
          AND c.created_at <= NOW()
    """
    
    logger.info("Analyzing user analytics query...")
    plan1 = explain_analyze_query(conn, query1)
    results.append({
        "query_name": "user_analytics_date_filter",
        "query": query1,
        "execution_plan": plan1
    })
    
    # Query 2: Conversation statistics with aggregation
    query2 = """
        SELECT 
            EXTRACT(HOUR FROM c.created_at) as hour,
            COUNT(*) as conversation_count
        FROM conversations c
        WHERE c.created_at >= NOW() - INTERVAL '7 days'
        GROUP BY EXTRACT(HOUR FROM c.created_at)
        ORDER BY hour
    """
    
    logger.info("Analyzing conversation statistics query...")
    plan2 = explain_analyze_query(conn, query2)
    results.append({
        "query_name": "conversation_statistics_hourly",
        "query": query2,
        "execution_plan": plan2
    })
    
    # Query 3: Message response time calculation
    query3 = """
        SELECT 
            AVG(EXTRACT(EPOCH FROM (m.created_at - prev_msg.created_at))) as avg_response_time
        FROM messages m
        JOIN messages prev_msg ON prev_msg.conversation_id = m.conversation_id
            AND prev_msg.created_at < m.created_at
            AND prev_msg.role = 'user'
        WHERE m.role = 'assistant'
          AND m.created_at >= NOW() - INTERVAL '7 days'
    """
    
    logger.info("Analyzing message response time query...")
    plan3 = explain_analyze_query(conn, query3)
    results.append({
        "query_name": "message_response_time_calculation",
        "query": query3,
        "execution_plan": plan3
    })
    
    return results


def get_missing_indexes_recommendations() -> List[Dict[str, Any]]:
    """Get recommendations for missing indexes based on query patterns."""
    recommendations = [
        {
            "name": "idx_conversations_updated_at",
            "table": "conversations",
            "sql": "CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC)",
            "reason": "Optimizes conversation listing queries ordered by updated_at"
        },
        {
            "name": "idx_conversations_user_id_created_at",
            "table": "conversations",
            "sql": "CREATE INDEX idx_conversations_user_id_created_at ON conversations(user_id, created_at DESC)",
            "reason": "Optimizes user-specific conversation queries with date filtering"
        },
        {
            "name": "idx_messages_conversation_id_created_at",
            "table": "messages",
            "sql": "CREATE INDEX idx_messages_conversation_id_created_at ON messages(conversation_id, created_at ASC)",
            "reason": "Optimizes message retrieval for conversations ordered by created_at"
        },
        {
            "name": "idx_messages_role_created_at",
            "table": "messages",
            "sql": "CREATE INDEX idx_messages_role_created_at ON messages(role, created_at) WHERE role IN ('user', 'assistant')",
            "reason": "Optimizes response time calculations and role-based queries"
        },
        {
            "name": "idx_messages_content_gin",
            "table": "messages",
            "sql": "CREATE INDEX idx_messages_content_gin ON messages USING gin(to_tsvector('english', content))",
            "reason": "Enables fast full-text search on message content (replaces slow ILIKE queries)"
        },
        {
            "name": "idx_conversations_user_id_gin",
            "table": "conversations",
            "sql": "CREATE INDEX idx_conversations_user_id_gin ON conversations USING gin(user_id gin_trgm_ops)",
            "reason": "Enables fast pattern matching on user_id (requires pg_trgm extension)"
        },
        {
            "name": "idx_documents_id_btree",
            "table": "documents",
            "sql": "CREATE INDEX IF NOT EXISTS idx_documents_id_btree ON documents(id)",
            "reason": "Optimizes RAG document retrieval by ID (if not already indexed)"
        },
        {
            "name": "idx_cost_tracking_user_id_created_at",
            "table": "cost_tracking",
            "sql": "CREATE INDEX IF NOT EXISTS idx_cost_tracking_user_id_created_at ON cost_tracking(user_id, created_at DESC)",
            "reason": "Optimizes cost tracking queries filtered by user and date"
        },
    ]
    
    return recommendations


def apply_optimizations(conn) -> Dict[str, Any]:
    """Apply database optimizations."""
    results = {
        "indexes_created": [],
        "indexes_skipped": [],
        "extensions_created": []
    }
    
    # Check and create pg_trgm extension for trigram matching
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")
        has_trgm = cursor.fetchone()[0]
        
        if not has_trgm:
            logger.info("Creating pg_trgm extension for text search...")
            cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            conn.commit()
            results["extensions_created"].append("pg_trgm")
        else:
            logger.info("pg_trgm extension already exists")
    except Exception as e:
        logger.warning(f"Could not create pg_trgm extension (may require superuser): {e}")
        conn.rollback()
    finally:
        cursor.close()
    
    # Apply index recommendations
    recommendations = get_missing_indexes_recommendations()
    
    for rec in recommendations:
        if create_index(conn, rec["sql"], rec["name"], rec["table"]):
            results["indexes_created"].append(rec["name"])
        else:
            results["indexes_skipped"].append(rec["name"])
    
    return results


def generate_optimization_report(
    before_results: List[Dict[str, Any]],
    after_results: List[Dict[str, Any]],
    optimizations: Dict[str, Any]
) -> str:
    """Generate a markdown report of optimization results."""
    report = f"""# Database Query Optimization Report

Generated: {datetime.now().isoformat()}

## Summary

This report documents the analysis and optimization of PostgreSQL queries across Gateway, Inference API services.

## Optimizations Applied

### Extensions Created
"""
    for ext in optimizations["extensions_created"]:
        report += f"- {ext}\n"
    
    report += "\n### Indexes Created\n"
    for idx in optimizations["indexes_created"]:
        report += f"- {idx}\n"
    
    report += "\n### Indexes Skipped (Already Exists)\n"
    for idx in optimizations["indexes_skipped"]:
        report += f"- {idx}\n"
    
    report += "\n## Query Performance Analysis\n\n"
    
    # Compare before/after for each query
    for before in before_results:
        query_name = before["query_name"]
        before_time = before["execution_plan"].get("execution_time_ms", 0)
        
        # Find corresponding after result
        after = next((a for a in after_results if a["query_name"] == query_name), None)
        if after:
            after_time = after["execution_plan"].get("execution_time_ms", 0)
            improvement = ((before_time - after_time) / before_time * 100) if before_time > 0 else 0
            
            report += f"### {query_name}\n\n"
            report += f"- **Before**: {before_time:.2f} ms\n"
            report += f"- **After**: {after_time:.2f} ms\n"
            report += f"- **Improvement**: {improvement:.1f}%\n\n"
    
    report += "\n## Recommendations\n\n"
    report += "1. **Full-Text Search**: Use `to_tsvector` and `ts_rank` instead of ILIKE for better performance\n"
    report += "2. **Query Caching**: Consider caching frequently accessed conversation data\n"
    report += "3. **Connection Pooling**: Ensure connection pooling is configured (see task 470)\n"
    report += "4. **Partitioning**: Consider partitioning large tables (conversations, messages) by date for better performance\n"
    report += "5. **Materialized Views**: Consider materialized views for complex analytics queries\n"
    
    return report


def main():
    """Main optimization workflow."""
    logger.info("Starting database query optimization...")
    
    conn = get_db_connection()
    try:
        # Analyze queries before optimization
        logger.info("Analyzing queries before optimization...")
        before_conversation = analyze_conversation_queries(conn)
        before_rag = analyze_rag_queries(conn)
        before_analytics = analyze_analytics_queries(conn)
        before_results = before_conversation + before_rag + before_analytics
        
        # Apply optimizations
        logger.info("Applying optimizations...")
        optimizations = apply_optimizations(conn)
        
        # Re-analyze queries after optimization
        logger.info("Analyzing queries after optimization...")
        after_conversation = analyze_conversation_queries(conn)
        after_rag = analyze_rag_queries(conn)
        after_analytics = analyze_analytics_queries(conn)
        after_results = after_conversation + after_rag + after_analytics
        
        # Generate report
        report = generate_optimization_report(before_results, after_results, optimizations)
        
        # Save report
        report_path = "/home/rlee/dev/june/docs/database_optimization_report.md"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)
        
        logger.info(f"Optimization report saved to {report_path}")
        
        # Print summary
        print("\n" + "="*60)
        print("OPTIMIZATION SUMMARY")
        print("="*60)
        print(f"Indexes created: {len(optimizations['indexes_created'])}")
        print(f"Indexes skipped: {len(optimizations['indexes_skipped'])}")
        print(f"Extensions created: {len(optimizations['extensions_created'])}")
        print(f"Report saved to: {report_path}")
        print("="*60)
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
