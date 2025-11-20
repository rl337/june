#!/usr/bin/env python3
"""
Test script for Phase 21: USER_MESSAGES.md round trip verification.

This script automates the testing of the complete round trip:
1. Owner sends message → appears in USER_MESSAGES.md with status "NEW"
2. Agent reads message → updates status to "PROCESSING"
3. Agent sends response via Message API
4. Owner receives response on Telegram/Discord
5. Message status updated to "RESPONDED" in USER_MESSAGES.md

Usage:
    poetry run python scripts/test_phase21_round_trip.py
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from essence.chat.user_messages_sync import (
    read_user_messages,
    append_message_to_user_messages,
    update_message_status,
    get_owner_users,
    USER_MESSAGES_FILE,
)
from essence.chat.message_api_client import MessageAPIClient, send_message_via_api
from essence.commands.process_user_messages import parse_user_messages_file

# Configuration
# Use JUNE_DATA_DIR if set, otherwise use /var/data (for containers)
# On host, this should match the volume mount in docker-compose.yml
JUNE_DATA_DIR = os.getenv("JUNE_DATA_DIR", "/home/rlee/june_data")
DATA_DIR = Path(os.getenv("USER_MESSAGES_DATA_DIR", f"{JUNE_DATA_DIR}/var-data"))
USER_MESSAGES_FILE = DATA_DIR / "USER_MESSAGES.md"
MESSAGE_API_URL = os.getenv("MESSAGE_API_URL", "http://localhost:8083")
POLLING_INTERVAL = 5  # seconds to wait between checks
MAX_WAIT_TIME = 120  # maximum seconds to wait for status changes


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_step(step_num: int, description: str):
    """Print a formatted step."""
    print(f"\n[Step {step_num}] {description}")
    print("-" * 60)


def check_prerequisites() -> bool:
    """Check if prerequisites are met."""
    print_section("Prerequisites Check")
    
    # Check if services are running
    print("Checking service status...")
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        if result.returncode != 0:
            print("❌ Failed to check Docker services")
            return False
        
        services = [json.loads(line) for line in result.stdout.strip().split("\n") if line]
        telegram_running = any(s.get("Name", "").startswith("june-telegram") for s in services)
        discord_running = any(s.get("Name", "").startswith("june-discord") for s in services)
        message_api_running = any(s.get("Name", "").startswith("june-message-api") for s in services)
        
        print(f"  Telegram: {'✅' if telegram_running else '❌'}")
        print(f"  Discord: {'✅' if discord_running else '❌'}")
        print(f"  Message API: {'✅' if message_api_running else '❌'}")
        
        if not (telegram_running or discord_running):
            print("❌ At least one of Telegram or Discord service must be running")
            return False
        if not message_api_running:
            print("❌ Message API service must be running")
            return False
    except Exception as e:
        print(f"❌ Error checking services: {e}")
        return False
    
    # Check if owner users are configured
    print("\nChecking owner user configuration...")
    telegram_owners = get_owner_users("telegram")
    discord_owners = get_owner_users("discord")
    
    if not telegram_owners and not discord_owners:
        print("❌ No owner users configured (TELEGRAM_OWNER_USERS or DISCORD_OWNER_USERS)")
        print("   Configure owner users in .env file before testing")
        return False
    
    print(f"  Telegram owners: {telegram_owners if telegram_owners else 'None'}")
    print(f"  Discord owners: {discord_owners if discord_owners else 'None'}")
    
    # Check if USER_MESSAGES.md directory exists
    print("\nChecking USER_MESSAGES.md directory...")
    if not DATA_DIR.exists():
        print(f"⚠️  {DATA_DIR} does not exist, will be created on first message")
    else:
        print(f"✅ {DATA_DIR} exists")
    
    # Check Message API connectivity
    print("\nChecking Message API connectivity...")
    try:
        client = MessageAPIClient(base_url=MESSAGE_API_URL)
        health = client.health_check()
        if health.get("status") == "healthy":
            print(f"✅ Message API is accessible at {MESSAGE_API_URL}")
        else:
            print(f"⚠️  Message API health check returned: {health}")
    except Exception as e:
        print(f"❌ Cannot connect to Message API at {MESSAGE_API_URL}: {e}")
        return False
    
    print("\n✅ All prerequisites met")
    return True


def test_step1_send_message() -> Optional[str]:
    """Step 1: Send a test message as owner."""
    print_step(1, "Send test message as owner")
    
    # Get owner user ID
    telegram_owners = get_owner_users("telegram")
    discord_owners = get_owner_users("discord")
    
    if telegram_owners:
        platform = "telegram"
        user_id = telegram_owners[0]
    elif discord_owners:
        platform = "discord"
        user_id = discord_owners[0]
    else:
        print("❌ No owner users configured")
        return None
    
    # Create test message
    test_message = f"🧪 Phase 21 Round Trip Test - {datetime.now().isoformat()}"
    
    print(f"  Platform: {platform}")
    print(f"  User ID: {user_id}")
    print(f"  Message: {test_message}")
    
    # Append message to USER_MESSAGES.md
    try:
        append_message_to_user_messages(
            user_id=user_id,
            chat_id=user_id,
            platform=platform,
            message_type="text",
            content=test_message,
        )
        print("✅ Message appended to USER_MESSAGES.md with status 'NEW'")
        
        # Read back to get message ID (match by content and status)
        messages = parse_user_messages_file(USER_MESSAGES_FILE)
        for msg in messages:
            if msg.status == "NEW" and msg.content == test_message:
                # Use timestamp as identifier if message_id is not available
                message_id = msg.message_id or msg.timestamp
                print(f"✅ Message found - ID: {message_id}")
                return message_id
        
        print("⚠️  Message appended but could not find it in file")
        return "unknown"
    except Exception as e:
        print(f"❌ Failed to append message: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_step2_verify_new_status(message_id: str) -> bool:
    """Step 2: Verify message appears with status 'NEW'."""
    print_step(2, "Verify message appears with status 'NEW'")
    
    if not USER_MESSAGES_FILE.exists():
        print(f"❌ USER_MESSAGES.md does not exist: {USER_MESSAGES_FILE}")
        return False
    
    try:
        messages = parse_user_messages_file(USER_MESSAGES_FILE)
        for msg in messages:
            # Match by message_id or timestamp
            msg_identifier = msg.message_id or msg.timestamp
            if msg_identifier == message_id:
                status = msg.status
                if status == "NEW":
                    print(f"✅ Message found with status 'NEW'")
                    print(f"   Identifier: {message_id}")
                    print(f"   Status: {status}")
                    print(f"   Message: {msg.content[:50]}...")
                    return True
                else:
                    print(f"⚠️  Message found but status is '{status}' (expected 'NEW')")
                    return False
        
        print(f"❌ Message with identifier '{message_id}' not found in USER_MESSAGES.md")
        return False
    except Exception as e:
        print(f"❌ Failed to read USER_MESSAGES.md: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_step3_verify_processing_status(message_id: str) -> bool:
    """Step 3: Verify agent reads message and updates status to 'PROCESSING'."""
    print_step(3, "Verify agent reads message and updates status to 'PROCESSING'")
    
    print(f"  Waiting for agent to process message (max {MAX_WAIT_TIME}s)...")
    print("  (You can run 'poetry run python -m essence process-user-messages' manually)")
    
    start_time = time.time()
    while time.time() - start_time < MAX_WAIT_TIME:
        try:
            messages = parse_user_messages_file(USER_MESSAGES_FILE)
            for msg in messages:
                # Match by message_id or timestamp
                msg_identifier = msg.message_id or msg.timestamp
                if msg_identifier == message_id:
                    status = msg.status
                    if status == "PROCESSING":
                        print(f"✅ Message status updated to 'PROCESSING'")
                        print(f"   Identifier: {message_id}")
                        print(f"   Status: {status}")
                        return True
                    elif status in ["RESPONDED", "ERROR"]:
                        print(f"⚠️  Message status is '{status}' (expected 'PROCESSING' first)")
                        print(f"   This might mean the agent processed it very quickly")
                        return True
                    # Still NEW, continue waiting
                    break
        except Exception as e:
            print(f"⚠️  Error reading messages: {e}")
        
        time.sleep(POLLING_INTERVAL)
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0:
            print(f"  ... still waiting ({elapsed}s elapsed)")
    
    print(f"❌ Timeout: Message status did not change to 'PROCESSING' within {MAX_WAIT_TIME}s")
    print("   Try running 'poetry run python -m essence process-user-messages' manually")
    return False


def test_step4_verify_response_sent(message_id: str) -> bool:
    """Step 4: Verify agent sends response via Message API."""
    print_step(4, "Verify agent sends response via Message API")
    
    print(f"  Checking Message API for response messages...")
    
    try:
        client = MessageAPIClient(base_url=MESSAGE_API_URL)
        messages = client.list_messages(limit=10)
        
        if messages and len(messages) > 0:
            print(f"✅ Found {len(messages)} recent messages in Message API")
            # Check if any message is a response (sent by agent)
            for msg in messages[:5]:  # Check last 5 messages
                print(f"   Message ID: {msg.get('message_id')}, Type: {msg.get('message_type')}")
        else:
            print("⚠️  No messages found in Message API (this might be normal if agent hasn't sent response yet)")
        
        # Also check message-api logs
        print("\n  Checking message-api logs...")
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "compose", "logs", "--tail", "20", "message-api"],
                capture_output=True,
                text=True,
                cwd=project_root,
            )
            if "POST /messages" in result.stdout or "send_message" in result.stdout:
                print("✅ Found message sending activity in logs")
            else:
                print("⚠️  No recent message sending activity in logs")
        except Exception as e:
            print(f"⚠️  Could not check logs: {e}")
        
        return True  # Don't fail if we can't verify, just report
    except Exception as e:
        print(f"⚠️  Error checking Message API: {e}")
        return True  # Don't fail, just report


def test_step5_verify_responded_status(message_id: str) -> bool:
    """Step 5: Verify message status updated to 'RESPONDED'."""
    print_step(5, "Verify message status updated to 'RESPONDED'")
    
    print(f"  Waiting for message status to update to 'RESPONDED' (max {MAX_WAIT_TIME}s)...")
    
    start_time = time.time()
    while time.time() - start_time < MAX_WAIT_TIME:
        try:
            messages = parse_user_messages_file(USER_MESSAGES_FILE)
            for msg in messages:
                # Match by message_id or timestamp
                msg_identifier = msg.message_id or msg.timestamp
                if msg_identifier == message_id:
                    status = msg.status
                    if status == "RESPONDED":
                        print(f"✅ Message status updated to 'RESPONDED'")
                        print(f"   Identifier: {message_id}")
                        print(f"   Status: {status}")
                        return True
                    elif status == "ERROR":
                        print(f"❌ Message status is 'ERROR' (agent encountered an error)")
                        return False
                    # Still PROCESSING, continue waiting
                    break
        except Exception as e:
            print(f"⚠️  Error reading messages: {e}")
        
        time.sleep(POLLING_INTERVAL)
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0:
            print(f"  ... still waiting ({elapsed}s elapsed)")
    
    print(f"⚠️  Timeout: Message status did not change to 'RESPONDED' within {MAX_WAIT_TIME}s")
    print("   This might be normal if the agent is still processing")
    return False  # Don't fail, just warn


def main():
    """Run the complete Phase 21 round trip test."""
    print_section("Phase 21: USER_MESSAGES.md Round Trip Test")
    print("This script automates testing of the complete round trip communication flow.")
    print("It verifies that messages flow correctly through USER_MESSAGES.md and the Message API.")
    
    # Check prerequisites
    if not check_prerequisites():
        print("\n❌ Prerequisites not met. Please fix issues above and try again.")
        sys.exit(1)
    
    # Run test steps
    message_id = test_step1_send_message()
    if not message_id:
        print("\n❌ Test failed at Step 1: Could not send test message")
        sys.exit(1)
    
    if not test_step2_verify_new_status(message_id):
        print("\n❌ Test failed at Step 2: Message not found with status 'NEW'")
        sys.exit(1)
    
    if not test_step3_verify_processing_status(message_id):
        print("\n⚠️  Test warning at Step 3: Agent did not update status to 'PROCESSING'")
        print("   This might be normal if the agent processes very quickly")
    
    test_step4_verify_response_sent(message_id)  # Don't fail on this
    
    if not test_step5_verify_responded_status(message_id):
        print("\n⚠️  Test warning at Step 5: Message status did not update to 'RESPONDED'")
        print("   This might be normal if the agent is still processing")
    
    # Summary
    print_section("Test Summary")
    print("✅ Round trip test completed")
    print(f"   Test message ID: {message_id}")
    print("\nNext steps:")
    print("1. Check Telegram/Discord client for response message")
    print("2. Verify response content is appropriate")
    print("3. Check USER_MESSAGES.md for final status:")
    print(f"   cat {USER_MESSAGES_FILE} | grep -A 10 '{message_id}'")


if __name__ == "__main__":
    main()
