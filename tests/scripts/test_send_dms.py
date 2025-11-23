#!/usr/bin/env python3
"""
Test script to send DMs to user on both Telegram and Discord.

This verifies that the agent can actually send messages before refactoring to API.
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

from essence.chat.agent_communication import (
    CommunicationChannel,
    send_message_to_user,
)


def test_telegram_message():
    """Test sending a message via Telegram."""
    print("\n" + "=" * 60)
    print("Testing Telegram DM")
    print("=" * 60)
    
    telegram_user_id = os.getenv("TELEGRAM_WHITELISTED_USERS", "").strip()
    if not telegram_user_id:
        print("❌ TELEGRAM_WHITELISTED_USERS not set in .env")
        return False
    
    # Use the user ID as chat_id for DM (Telegram uses same ID for user and chat in DMs)
    chat_id = telegram_user_id
    
    print(f"📱 Sending test message to Telegram user: {telegram_user_id}")
    print(f"   Chat ID: {chat_id}")
    
    try:
        result = send_message_to_user(
            user_id=telegram_user_id,
            chat_id=chat_id,
            message="🧪 Test message from agent! This is a verification that I can send DMs via Telegram.",
            platform=CommunicationChannel.TELEGRAM,
            message_type="text",
            require_service_stopped=True,
        )
        
        if result.get("success"):
            print(f"✅ Telegram message sent successfully!")
            print(f"   Message ID: {result.get('message_id', 'N/A')}")
            print(f"   Platform: {result.get('platform', 'N/A')}")
            return True
        else:
            print(f"❌ Failed to send Telegram message: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending Telegram message: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_discord_message():
    """Test sending a message via Discord."""
    print("\n" + "=" * 60)
    print("Testing Discord DM")
    print("=" * 60)
    
    discord_user_id = os.getenv("DISCORD_WHITELISTED_USERS", "").strip()
    if not discord_user_id:
        print("❌ DISCORD_WHITELISTED_USERS not set in .env")
        return False
    
    # For Discord, we need to create/get the DM channel first
    # Discord requires creating a DM channel via API before sending messages
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token:
        print("❌ DISCORD_BOT_TOKEN not set in .env")
        return False
    
    print(f"💬 Creating/getting DM channel for Discord user: {discord_user_id}")
    
    try:
        import httpx
        
        # Create or get DM channel
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }
        payload = {"recipient_id": discord_user_id}
        
        with httpx.Client(timeout=10.0) as client:
            # Create DM channel
            response = client.post(
                "https://discord.com/api/v10/users/@me/channels",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            channel_data = response.json()
            chat_id = channel_data.get("id")
            
            if not chat_id:
                print("❌ Failed to get DM channel ID from Discord API")
                return False
            
            print(f"   DM Channel ID: {chat_id}")
            
            # Now send the message
            result = send_message_to_user(
                user_id=discord_user_id,
                chat_id=chat_id,
                message="🧪 Test message from agent! This is a verification that I can send DMs via Discord.",
                platform=CommunicationChannel.DISCORD,
                message_type="text",
                require_service_stopped=True,
            )
            
            if result.get("success"):
                print(f"✅ Discord message sent successfully!")
                print(f"   Message ID: {result.get('message_id', 'N/A')}")
                print(f"   Platform: {result.get('platform', 'N/A')}")
                return True
            else:
                print(f"❌ Failed to send Discord message: {result.get('error', 'Unknown error')}")
                return False
                
    except Exception as e:
        print(f"❌ Error sending Discord message: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function."""
    print("\n" + "=" * 60)
    print("Agent DM Test - Verification Before API Refactoring")
    print("=" * 60)
    print("\nThis script tests that the agent can send DMs to you on both platforms.")
    print("Services should be stopped before running this test.\n")
    
    # Check if services are running
    import subprocess
    result = subprocess.run(
        ["docker", "compose", "ps", "telegram", "discord"],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    
    if "Up" in result.stdout or "Running" in result.stdout:
        print("⚠️  WARNING: Telegram or Discord services appear to be running!")
        print("   Please stop them first: docker compose stop telegram discord")
        print("   Continuing anyway...\n")
    
    telegram_success = test_telegram_message()
    discord_success = test_discord_message()
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Telegram: {'✅ SUCCESS' if telegram_success else '❌ FAILED'}")
    print(f"Discord:  {'✅ SUCCESS' if discord_success else '❌ FAILED'}")
    
    if telegram_success and discord_success:
        print("\n✅ All tests passed! Agent can send DMs on both platforms.")
        print("   Ready to proceed with API refactoring.")
        return 0
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
