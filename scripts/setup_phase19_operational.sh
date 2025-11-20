#!/bin/bash
# Operational workflow script for Phase 19: Direct Agent-User Communication
#
# This script orchestrates the operational tasks for Phase 19:
# 1. Configure whitelisted users
# 2. Start Telegram/Discord services with whitelist
# 3. Verify whitelist configuration
# 4. Test end-to-end communication
# 5. Verify message syncing and polling
#
# Usage:
#   ./scripts/setup_phase19_operational.sh [--telegram-users USER1,USER2] [--discord-users USER1,USER2] [--skip-start] [--test-only]
#
# Options:
#   --telegram-users    Comma-separated list of Telegram user IDs to whitelist
#   --discord-users     Comma-separated list of Discord user IDs to whitelist
#   --skip-start        Skip service startup (assumes services already running)
#   --test-only         Only run tests (assumes services already running with whitelist configured)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

TELEGRAM_USERS=""
DISCORD_USERS=""
SKIP_START=false
TEST_ONLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --telegram-users)
            TELEGRAM_USERS="$2"
            shift 2
            ;;
        --discord-users)
            DISCORD_USERS="$2"
            shift 2
            ;;
        --skip-start)
            SKIP_START=true
            shift
            ;;
        --test-only)
            TEST_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--telegram-users USER1,USER2] [--discord-users USER1,USER2] [--skip-start] [--test-only]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Phase 19: Direct Agent-User Communication"
echo "Operational Setup Script"
echo "=========================================="
echo ""

# Step 1: Configure whitelisted users
if [ "$TEST_ONLY" = false ]; then
    echo "Step 1: Configure whitelisted users"
    echo "-----------------------------------"
    
    if [ -z "$TELEGRAM_USERS" ] && [ -z "$DISCORD_USERS" ]; then
        echo "⚠️  WARNING: No whitelisted users specified"
        echo ""
        echo "To configure whitelisted users, use:"
        echo "  --telegram-users USER1,USER2,USER3"
        echo "  --discord-users USER1,USER2,USER3"
        echo ""
        echo "Or set environment variables:"
        echo "  export TELEGRAM_WHITELISTED_USERS=\"USER1,USER2,USER3\""
        echo "  export DISCORD_WHITELISTED_USERS=\"USER1,USER2,USER3\""
        echo ""
        read -p "Continue without whitelist configuration? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Exiting. Please configure whitelisted users and try again."
            exit 1
        fi
    else
        if [ -n "$TELEGRAM_USERS" ]; then
            export TELEGRAM_WHITELISTED_USERS="$TELEGRAM_USERS"
            echo "✅ Telegram whitelist configured: $TELEGRAM_USERS"
        fi
        
        if [ -n "$DISCORD_USERS" ]; then
            export DISCORD_WHITELISTED_USERS="$DISCORD_USERS"
            echo "✅ Discord whitelist configured: $DISCORD_USERS"
        fi
        
        echo ""
        echo "To persist these settings, add to your environment or docker-compose.yml:"
        echo "  TELEGRAM_WHITELISTED_USERS=$TELEGRAM_USERS"
        echo "  DISCORD_WHITELISTED_USERS=$DISCORD_USERS"
        echo ""
    fi
fi

# Step 2: Verify whitelist configuration
echo "Step 2: Verify whitelist configuration"
echo "-----------------------------------"

if [ -n "${TELEGRAM_WHITELISTED_USERS:-}" ]; then
    echo "✅ TELEGRAM_WHITELISTED_USERS: $TELEGRAM_WHITELISTED_USERS"
else
    echo "⚠️  TELEGRAM_WHITELISTED_USERS: Not set"
fi

if [ -n "${DISCORD_WHITELISTED_USERS:-}" ]; then
    echo "✅ DISCORD_WHITELISTED_USERS: $DISCORD_WHITELISTED_USERS"
else
    echo "⚠️  DISCORD_WHITELISTED_USERS: Not set"
fi

echo ""

# Step 3: Start services with whitelist
if [ "$SKIP_START" = false ] && [ "$TEST_ONLY" = false ]; then
    echo "Step 3: Start Telegram/Discord services with whitelist"
    echo "-----------------------------------"
    
    echo "Starting services with whitelist configuration..."
    echo ""
    
    # Check if docker-compose.yml exists
    if [ ! -f "docker-compose.yml" ]; then
        echo "❌ ERROR: docker-compose.yml not found"
        exit 1
    fi
    
    # Start Telegram service
    if [ -n "${TELEGRAM_WHITELISTED_USERS:-}" ]; then
        echo "Starting Telegram service with whitelist..."
        TELEGRAM_WHITELISTED_USERS="$TELEGRAM_WHITELISTED_USERS" docker compose up -d telegram
        echo "✅ Telegram service started"
    else
        echo "⚠️  Skipping Telegram service (no whitelist configured)"
    fi
    
    # Start Discord service
    if [ -n "${DISCORD_WHITELISTED_USERS:-}" ]; then
        echo "Starting Discord service with whitelist..."
        DISCORD_WHITELISTED_USERS="$DISCORD_WHITELISTED_USERS" docker compose up -d discord
        echo "✅ Discord service started"
    else
        echo "⚠️  Skipping Discord service (no whitelist configured)"
    fi
    
    echo ""
    echo "Waiting for services to be ready..."
    sleep 5
    
    # Check service health
    echo "Checking service health..."
    if docker compose ps telegram | grep -q "Up"; then
        echo "✅ Telegram service is running"
    else
        echo "⚠️  Telegram service may not be running properly"
    fi
    
    if docker compose ps discord | grep -q "Up"; then
        echo "✅ Discord service is running"
    else
        echo "⚠️  Discord service may not be running properly"
    fi
    
    echo ""
fi

# Step 4: Verify whitelist routing
echo "Step 4: Verify whitelist routing"
echo "-----------------------------------"
echo ""
echo "To verify whitelist routing is working:"
echo "1. Send a message from a whitelisted user"
echo "2. Check service logs to confirm direct routing:"
echo "   docker compose logs telegram | grep -i whitelist"
echo "   docker compose logs discord | grep -i whitelist"
echo "3. Send a message from a non-whitelisted user"
echo "4. Verify non-whitelisted users still use existing agentic flow"
echo ""

# Step 5: Test end-to-end communication
echo "Step 5: Test end-to-end communication"
echo "-----------------------------------"
echo ""
echo "Manual testing steps:"
echo "1. Send test message from whitelisted user via Telegram/Discord"
echo "2. Verify message appears in USER_REQUESTS.md:"
echo "   cat USER_REQUESTS.md | grep -A 5 'Your message here'"
echo ""
echo "3. Verify agent reads and responds:"
echo "   # Agent should read USER_REQUESTS.md and respond"
echo "   # Check agent logs or USER_REQUESTS.md for response"
echo ""
echo "4. Verify agent response appears in Telegram/Discord"
echo "5. Verify agent response synced to USER_REQUESTS.md"
echo ""

# Step 6: Test message grouping and editing
echo "Step 6: Test message grouping and editing"
echo "-----------------------------------"
echo ""
echo "To test message grouping and editing:"
echo "1. Send multiple messages from whitelisted user"
echo "2. Verify messages are grouped in USER_REQUESTS.md"
echo "3. Verify agent can edit previous messages"
echo ""

# Step 7: Test polling loop
echo "Step 7: Test polling loop"
echo "-----------------------------------"
echo ""
echo "To test polling loop:"
echo "1. Ensure polling is enabled in agent script:"
echo "   export ENABLE_USER_POLLING=1"
echo "   export USER_POLLING_INTERVAL_SECONDS=120  # 2 minutes"
echo ""
echo "2. Start agent loop with polling:"
echo "   ./scripts/refactor_agent_loop.sh"
echo ""
echo "3. Send message from whitelisted user"
echo "4. Verify polling detects new user requests"
echo "5. Verify polling processes user responses"
echo ""

# Step 8: Test service conflict prevention
echo "Step 8: Test service conflict prevention"
echo "-----------------------------------"
echo ""
echo "To test service conflict prevention:"
echo "1. Start agent loop (will disable Telegram/Discord services when communicating)"
echo "2. Send message from whitelisted user"
echo "3. Verify Telegram/Discord service is disabled during agent communication"
echo "4. Verify service is re-enabled after agent communication completes"
echo ""

# Step 9: Verify actual exchanges
echo "Step 9: Verify actual exchanges happening"
echo "-----------------------------------"
echo ""
echo "To verify actual exchanges:"
echo "1. Confirm user can send messages to looping agent via Telegram/Discord"
echo "2. Confirm agent can send messages to user via Telegram/Discord"
echo "3. Confirm messages are synced to USER_REQUESTS.md"
echo "4. Confirm polling loop is working"
echo "5. Confirm message grouping/editing is working"
echo "6. Confirm service conflict prevention is working"
echo ""

echo "=========================================="
echo "Phase 19 Operational Setup Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Configure whitelisted users (if not already done)"
echo "2. Start services with whitelist environment variables"
echo "3. Test end-to-end communication"
echo "4. Verify message syncing and polling"
echo ""
echo "For detailed instructions, see:"
echo "  - docs/guides/AGENT_COMMUNICATION.md"
echo "  - REFACTOR_PLAN.md Phase 19 section"
echo ""
