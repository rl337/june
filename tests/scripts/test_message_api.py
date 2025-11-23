#!/usr/bin/env python3
"""
Test script for Message API endpoints.

Tests all API endpoints to verify they work correctly.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env file
env_path = project_root / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

import httpx
from essence.chat.message_api_client import MessageAPIClient


def test_health_check():
    """Test health check endpoint."""
    print("\n" + "=" * 60)
    print("Testing GET /health")
    print("=" * 60)
    
    try:
        client = MessageAPIClient()
        result = client.health_check()
        print(f"✅ Health check passed: {result}")
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def test_list_messages():
    """Test GET /messages endpoint."""
    print("\n" + "=" * 60)
    print("Testing GET /messages")
    print("=" * 60)
    
    try:
        client = MessageAPIClient()
        result = client.list_messages(limit=5)
        print(f"✅ List messages successful")
        print(f"   Total: {result.get('total', 0)}")
        print(f"   Returned: {len(result.get('messages', []))}")
        return True
    except Exception as e:
        print(f"❌ List messages failed: {e}")
        return False


def test_send_message():
    """Test POST /messages endpoint."""
    print("\n" + "=" * 60)
    print("Testing POST /messages")
    print("=" * 60)
    
    telegram_user_id = os.getenv("TELEGRAM_WHITELISTED_USERS", "").strip()
    if not telegram_user_id:
        print("⚠️  TELEGRAM_WHITELISTED_USERS not set, skipping send test")
        return None
    
    try:
        client = MessageAPIClient()
        result = client.send_message(
            user_id=telegram_user_id,
            chat_id=telegram_user_id,  # For DMs, chat_id = user_id
            message="🧪 Test message from Message API! This verifies the API can send messages.",
            platform="telegram",
            message_type="text",
        )
        
        if result.get("success"):
            message_id = result.get("message_id")
            print(f"✅ Send message successful")
            print(f"   Message ID: {message_id}")
            print(f"   Platform: {result.get('platform')}")
            return message_id
        else:
            print(f"❌ Send message failed: {result.get('error')}")
            return None
    except Exception as e:
        print(f"❌ Send message failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_get_message(message_id: str):
    """Test GET /messages/{message_id} endpoint."""
    print("\n" + "=" * 60)
    print(f"Testing GET /messages/{message_id}")
    print("=" * 60)
    
    try:
        client = MessageAPIClient()
        result = client.get_message(message_id, platform="telegram")
        print(f"✅ Get message successful")
        print(f"   Content: {result.get('message_content', '')[:50]}...")
        return True
    except Exception as e:
        print(f"❌ Get message failed: {e}")
        return False


def test_edit_message(message_id: str):
    """Test PUT /messages/{message_id} endpoint."""
    print("\n" + "=" * 60)
    print(f"Testing PUT /messages/{message_id}")
    print("=" * 60)
    
    try:
        client = MessageAPIClient()
        result = client.edit_message(
            message_id=message_id,
            new_message="🧪 Edited test message from Message API! This verifies editing works.",
            platform="telegram",
        )
        
        if result.get("success"):
            print(f"✅ Edit message successful")
            return True
        else:
            print(f"❌ Edit message failed: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Edit message failed: {e}")
        return False


def test_append_message(message_id: str):
    """Test PATCH /messages/{message_id} endpoint."""
    print("\n" + "=" * 60)
    print(f"Testing PATCH /messages/{message_id}")
    print("=" * 60)
    
    try:
        client = MessageAPIClient()
        result = client.append_to_message(
            message_id=message_id,
            new_content="\n\n✅ This line was appended via PATCH endpoint!",
            platform="telegram",
        )
        
        if result.get("success"):
            print(f"✅ Append message successful")
            return True
        else:
            print(f"❌ Append message failed: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Append message failed: {e}")
        return False


def main():
    """Main test function."""
    print("\n" + "=" * 60)
    print("Message API Endpoint Tests")
    print("=" * 60)
    print("\nThis script tests all Message API endpoints.")
    print("Make sure message-api service is running:")
    print("  docker compose up -d message-api")
    print("  or")
    print("  poetry run python -m essence message-api-service")
    print()
    
    results = {}
    
    # Test 1: Health check
    results["health"] = test_health_check()
    
    # Test 2: List messages
    results["list"] = test_list_messages()
    
    # Test 3: Send message
    message_id = test_send_message()
    results["send"] = message_id is not None
    
    # Test 4: Get message (if we have a message_id)
    if message_id:
        results["get"] = test_get_message(message_id)
        
        # Test 5: Edit message
        results["edit"] = test_edit_message(message_id)
        
        # Test 6: Append to message
        results["append"] = test_append_message(message_id)
    else:
        print("\n⚠️  Skipping get/edit/append tests (no message_id)")
        results["get"] = None
        results["edit"] = None
        results["append"] = None
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test_name, result in results.items():
        if result is None:
            status = "⏭️  SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"{test_name:15} {status}")
    
    all_passed = all(r for r in results.values() if r is not None)
    if all_passed:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
