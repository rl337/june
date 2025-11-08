-- Initialize pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create tables for RAG and conversation storage
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- 'system', 'user', 'assistant', 'tool'
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
    embedding vector(1536), -- Adjust dimension based on embedding model
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500),
    content TEXT NOT NULL,
    source_url VARCHAR(1000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_embeddings_conversation_id ON embeddings(conversation_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_message_id ON embeddings(message_id);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_document_id ON document_embeddings(document_id);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_chunk_index ON document_embeddings(document_id, chunk_index);

-- Create vector similarity indexes (using HNSW for better performance)
CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_vector ON document_embeddings USING hnsw (embedding vector_cosine_ops);

-- Agent State Management Tables
-- Agent state table - stores current state of each agent
CREATE TABLE IF NOT EXISTS agent_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) NOT NULL UNIQUE,
    current_task_id VARCHAR(255), -- Reference to task (may be in external TODO service)
    status VARCHAR(50) NOT NULL CHECK (status IN ('init', 'active', 'idle', 'error')),
    capabilities JSONB DEFAULT '[]'::jsonb, -- List of tools/capabilities
    performance_metrics JSONB DEFAULT '{}'::jsonb, -- Completion rate, avg time, etc.
    configuration JSONB DEFAULT '{}'::jsonb, -- Agent-specific settings
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Agent execution history table - tracks agent activity over time
CREATE TABLE IF NOT EXISTS agent_execution_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255), -- Reference to task
    action_type VARCHAR(100) NOT NULL, -- e.g., 'task_started', 'task_completed', 'tool_used', etc.
    outcome VARCHAR(50) CHECK (outcome IN ('success', 'failure', 'partial', 'cancelled')),
    duration_ms INTEGER, -- Duration in milliseconds
    metadata JSONB DEFAULT '{}'::jsonb, -- Additional action metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (agent_id) REFERENCES agent_state(agent_id) ON DELETE CASCADE
);

-- Agent plans and strategies table - stores agent plans and execution strategies
CREATE TABLE IF NOT EXISTS agent_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255), -- Reference to task
    plan_type VARCHAR(100) NOT NULL, -- e.g., 'task_decomposition', 'execution_plan', 'strategy'
    plan_data JSONB NOT NULL DEFAULT '{}'::jsonb, -- Plan structure and details
    success_rate REAL DEFAULT 0.0, -- Success rate if plan was reused
    execution_count INTEGER DEFAULT 0, -- Number of times plan was executed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (agent_id) REFERENCES agent_state(agent_id) ON DELETE CASCADE
);

-- Agent knowledge cache table - caches agent learnings and knowledge
CREATE TABLE IF NOT EXISTS agent_knowledge_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) NOT NULL,
    knowledge_key VARCHAR(500) NOT NULL, -- Key identifying the knowledge
    knowledge_value JSONB NOT NULL DEFAULT '{}'::jsonb, -- Cached knowledge/value
    access_count INTEGER DEFAULT 0, -- Number of times accessed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (agent_id) REFERENCES agent_state(agent_id) ON DELETE CASCADE,
    UNIQUE(agent_id, knowledge_key)
);

-- Indexes for agent state management tables
-- Agent state indexes
CREATE INDEX IF NOT EXISTS idx_agent_state_agent_id ON agent_state(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_state_status ON agent_state(status);
CREATE INDEX IF NOT EXISTS idx_agent_state_current_task_id ON agent_state(current_task_id) WHERE current_task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_state_updated_at ON agent_state(updated_at);

-- Agent execution history indexes
CREATE INDEX IF NOT EXISTS idx_agent_execution_history_agent_id ON agent_execution_history(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_execution_history_task_id ON agent_execution_history(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_execution_history_created_at ON agent_execution_history(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_execution_history_action_type ON agent_execution_history(action_type);
CREATE INDEX IF NOT EXISTS idx_agent_execution_history_outcome ON agent_execution_history(outcome) WHERE outcome IS NOT NULL;

-- Agent plans indexes
CREATE INDEX IF NOT EXISTS idx_agent_plans_agent_id ON agent_plans(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_plans_task_id ON agent_plans(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_plans_plan_type ON agent_plans(plan_type);
CREATE INDEX IF NOT EXISTS idx_agent_plans_success_rate ON agent_plans(success_rate);

-- Agent knowledge cache indexes
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_cache_agent_id ON agent_knowledge_cache(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_cache_key ON agent_knowledge_cache(knowledge_key);
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_cache_last_accessed ON agent_knowledge_cache(last_accessed_at);

-- Resource locks table - stores persistent locks for coordination
CREATE TABLE IF NOT EXISTS resource_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id VARCHAR(500) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    lock_type VARCHAR(50) NOT NULL CHECK (lock_type IN ('exclusive', 'shared')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    released BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (agent_id) REFERENCES agent_state(agent_id) ON DELETE CASCADE,
    UNIQUE(resource_id, agent_id, created_at) -- Prevent exact duplicates
);

-- Indexes for resource locks
CREATE INDEX IF NOT EXISTS idx_resource_locks_resource_id ON resource_locks(resource_id);
CREATE INDEX IF NOT EXISTS idx_resource_locks_agent_id ON resource_locks(agent_id);
CREATE INDEX IF NOT EXISTS idx_resource_locks_expires_at ON resource_locks(expires_at);
CREATE INDEX IF NOT EXISTS idx_resource_locks_active ON resource_locks(resource_id, expires_at, released) 
    WHERE released = FALSE AND expires_at > NOW();

-- Admin Management Tables
-- Blocked users table - stores users blocked from using the bot
CREATE TABLE IF NOT EXISTS blocked_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL UNIQUE,
    blocked_by VARCHAR(255) NOT NULL, -- Admin user_id who blocked
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Admin users table - stores admin user IDs
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Audit logs table - stores audit trail for admin actions
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL, -- e.g., 'user_blocked', 'user_unblocked', 'conversation_cleared', 'system_status_checked'
    actor_user_id VARCHAR(255) NOT NULL, -- Admin user_id who performed the action
    target_user_id VARCHAR(255), -- Target user_id (if applicable)
    target_conversation_id UUID, -- Target conversation_id (if applicable)
    details JSONB DEFAULT '{}'::jsonb, -- Additional action details
    ip_address VARCHAR(45), -- IPv4 or IPv6 address
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for admin management tables
CREATE INDEX IF NOT EXISTS idx_blocked_users_user_id ON blocked_users(user_id);
CREATE INDEX IF NOT EXISTS idx_blocked_users_created_at ON blocked_users(created_at);
CREATE INDEX IF NOT EXISTS idx_admin_users_user_id ON admin_users(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_target_user_id ON audit_logs(target_user_id) WHERE target_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);


