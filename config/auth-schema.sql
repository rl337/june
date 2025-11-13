-- Authentication and Authorization Schema
-- This migration adds comprehensive user management, roles, permissions, and refresh tokens

-- Users table - stores user accounts with authentication credentials
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL UNIQUE, -- External user identifier (e.g., Telegram user ID)
    username VARCHAR(255) UNIQUE, -- Optional username for login
    email VARCHAR(255) UNIQUE, -- Optional email address
    password_hash VARCHAR(255), -- Hashed password (bcrypt/argon2) - NULL for external auth users
    is_active BOOLEAN DEFAULT TRUE, -- Whether account is active
    is_verified BOOLEAN DEFAULT FALSE, -- Whether email/account is verified
    last_login TIMESTAMP WITH TIME ZONE, -- Last login timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Roles table - stores role definitions
CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE, -- Role name (e.g., 'admin', 'user', 'service')
    description TEXT, -- Role description
    is_system_role BOOLEAN DEFAULT FALSE, -- Whether this is a system role (cannot be deleted)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Permissions table - stores permission definitions
CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE, -- Permission name (e.g., 'users.read', 'admin.write')
    resource VARCHAR(100) NOT NULL, -- Resource name (e.g., 'users', 'conversations', 'admin')
    action VARCHAR(50) NOT NULL, -- Action (e.g., 'read', 'write', 'delete', 'execute')
    description TEXT, -- Permission description
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User roles table - many-to-many relationship between users and roles
CREATE TABLE IF NOT EXISTS user_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    granted_by VARCHAR(255), -- User ID who granted this role
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE, -- Optional expiration date
    UNIQUE(user_id, role_id)
);

-- Role permissions table - many-to-many relationship between roles and permissions
CREATE TABLE IF NOT EXISTS role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    UNIQUE(role_id, permission_id)
);

-- Refresh tokens table - stores refresh tokens for JWT token refresh
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE, -- Hashed refresh token
    device_info VARCHAR(500), -- Device/browser information
    ip_address VARCHAR(45), -- IPv4 or IPv6 address
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, -- Token expiration
    revoked BOOLEAN DEFAULT FALSE, -- Whether token is revoked
    revoked_at TIMESTAMP WITH TIME ZONE, -- When token was revoked
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Service accounts table - stores service-to-service authentication credentials
CREATE TABLE IF NOT EXISTS service_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name VARCHAR(100) NOT NULL UNIQUE, -- Service name (e.g., 'inference-api', 'stt', 'tts')
    api_key_hash VARCHAR(255) NOT NULL, -- Hashed API key
    description TEXT, -- Service description
    is_active BOOLEAN DEFAULT TRUE, -- Whether service account is active
    last_used TIMESTAMP WITH TIME ZONE, -- Last time API key was used
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for users table
CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active) WHERE is_active = TRUE;

-- Indexes for roles table
CREATE INDEX IF NOT EXISTS idx_roles_name ON roles(name);

-- Indexes for permissions table
CREATE INDEX IF NOT EXISTS idx_permissions_name ON permissions(name);
CREATE INDEX IF NOT EXISTS idx_permissions_resource ON permissions(resource);
CREATE INDEX IF NOT EXISTS idx_permissions_resource_action ON permissions(resource, action);

-- Indexes for user_roles table
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_expires_at ON user_roles(expires_at) WHERE expires_at IS NOT NULL;

-- Indexes for role_permissions table
CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission_id ON role_permissions(permission_id);

-- Indexes for refresh_tokens table
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_active ON refresh_tokens(user_id, expires_at, revoked) 
    WHERE revoked = FALSE AND expires_at > NOW();

-- Indexes for service_accounts table
CREATE INDEX IF NOT EXISTS idx_service_accounts_service_name ON service_accounts(service_name);
CREATE INDEX IF NOT EXISTS idx_service_accounts_is_active ON service_accounts(is_active) WHERE is_active = TRUE;

-- Insert default system roles
INSERT INTO roles (name, description, is_system_role) VALUES
    ('admin', 'Administrator with full system access', TRUE),
    ('user', 'Regular user with standard access', TRUE),
    ('service', 'Service account for inter-service communication', TRUE)
ON CONFLICT (name) DO NOTHING;

-- Insert default permissions
INSERT INTO permissions (name, resource, action, description) VALUES
    -- User management permissions
    ('users.read', 'users', 'read', 'Read user information'),
    ('users.write', 'users', 'write', 'Create and update users'),
    ('users.delete', 'users', 'delete', 'Delete users'),
    -- Admin permissions
    ('admin.read', 'admin', 'read', 'Read admin dashboard data'),
    ('admin.write', 'admin', 'write', 'Modify admin settings'),
    -- Conversation permissions
    ('conversations.read', 'conversations', 'read', 'Read conversations'),
    ('conversations.write', 'conversations', 'write', 'Create and update conversations'),
    ('conversations.delete', 'conversations', 'delete', 'Delete conversations'),
    -- Bot permissions
    ('bot.read', 'bot', 'read', 'Read bot configuration'),
    ('bot.write', 'bot', 'write', 'Modify bot configuration'),
    -- System permissions
    ('system.read', 'system', 'read', 'Read system configuration'),
    ('system.write', 'system', 'write', 'Modify system configuration'),
    -- Service permissions
    ('service.inference', 'service', 'execute', 'Execute inference API calls'),
    ('service.stt', 'service', 'execute', 'Execute STT service calls'),
    ('service.tts', 'service', 'execute', 'Execute TTS service calls')
ON CONFLICT (name) DO NOTHING;

-- Grant default permissions to roles
-- Admin role gets all permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'admin'
ON CONFLICT DO NOTHING;

-- User role gets basic permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'user'
    AND p.name IN ('conversations.read', 'conversations.write', 'bot.read')
ON CONFLICT DO NOTHING;

-- Service role gets service execution permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'service'
    AND p.name IN ('service.inference', 'service.stt', 'service.tts')
ON CONFLICT DO NOTHING;

-- Migrate existing admin_users to new users table
-- This preserves existing admin accounts
INSERT INTO users (user_id, username, password_hash, is_active, is_verified)
SELECT 
    au.user_id,
    au.username,
    au.password_hash,
    TRUE,
    TRUE
FROM admin_users au
WHERE NOT EXISTS (
    SELECT 1 FROM users u WHERE u.user_id = au.user_id
)
ON CONFLICT (user_id) DO NOTHING;

-- Assign admin role to migrated admin users
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.user_id IN (SELECT user_id FROM admin_users)
    AND r.name = 'admin'
    AND NOT EXISTS (
        SELECT 1 FROM user_roles ur 
        WHERE ur.user_id = u.id AND ur.role_id = r.id
    )
ON CONFLICT DO NOTHING;
