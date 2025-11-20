#!/usr/bin/env python3
"""
Get Discord User ID from Recent Messages

This script fetches recent messages from DM channels to extract user IDs.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def get_discord_user_id_from_messages() -> None:
    """Get Discord user ID from recent messages in DM channels."""
    try:
        import httpx
        
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not bot_token:
            print("❌ DISCORD_BOT_TOKEN not set in .env")
            return
        
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }
        
        print("Fetching DM channels...")
        with httpx.Client(timeout=10.0) as client:
            # Get all DM channels
            response = client.get(
                "https://discord.com/api/v10/users/@me/channels",
                headers=headers
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to fetch channels: {response.status_code}")
                print(f"   {response.text[:200]}")
                return
            
            channels = response.json()
            print(f"✅ Found {len(channels)} channel(s)")
            print()
            
            if len(channels) == 0:
                print("⚠️  No DM channels found.")
                print("   The bot may need to receive a message first to create a DM channel.")
                return
            
            # Check each DM channel for recent messages
            for channel_data in channels:
                channel_type = channel_data.get("type")
                channel_id = channel_data.get("id")
                
                if channel_type == 1:  # DM channel
                    recipients = channel_data.get("recipients", [])
                    for recipient in recipients:
                        recipient_username = recipient.get("username", "")
                        recipient_id = recipient.get("id", "")
                        print(f"📱 DM Channel with: {recipient_username} (ID: {recipient_id})")
                        
                        # Try to get recent messages from this channel
                        try:
                            msg_response = client.get(
                                f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=5",
                                headers=headers
                            )
                            if msg_response.status_code == 200:
                                messages = msg_response.json()
                                if messages:
                                    print(f"   Found {len(messages)} recent message(s)")
                                    # Get user ID from the most recent message
                                    latest_msg = messages[0]
                                    author_id = latest_msg.get("author", {}).get("id", "")
                                    author_username = latest_msg.get("author", {}).get("username", "")
                                    print(f"   Latest message from: {author_username} (ID: {author_id})")
                                    
                                    # If this matches the username we're looking for, we found it
                                    if recipient_username.lower() == "morntheluriang".lower():
                                        print()
                                        print(f"✅ Found your Discord user ID!")
                                        print(f"   Username: {author_username}")
                                        print(f"   User ID: {author_id}")
                                        print()
                                        print(f"Add this to .env:")
                                        print(f"DISCORD_WHITELISTED_USERS={author_id}")
                                        return
                        except Exception as e:
                            print(f"   ⚠️  Error fetching messages: {e}")
                        print()
            
            # If we got here, list all found user IDs
            print("📋 All Discord user IDs found in DM channels:")
            for channel_data in channels:
                if channel_data.get("type") == 1:
                    recipients = channel_data.get("recipients", [])
                    for recipient in recipients:
                        recipient_username = recipient.get("username", "")
                        recipient_id = recipient.get("id", "")
                        print(f"   - {recipient_username}: {recipient_id}")
            
    except ImportError:
        print("❌ httpx library not available")
        print("   Install it: poetry add httpx")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main function."""
    print()
    print("🔍 Discord User ID Finder (from messages)")
    print()
    
    # Load .env file
    env_path = project_root / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
    
    get_discord_user_id_from_messages()


if __name__ == "__main__":
    main()
