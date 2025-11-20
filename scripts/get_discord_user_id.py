#!/usr/bin/env python3
"""
Get Discord User ID from Username

This script helps find your Discord user ID using the bot token.
You can also find it manually by enabling Developer Mode in Discord.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def get_discord_user_id_from_username(username: str) -> None:
    """
    Attempt to get Discord user ID from username using the bot.
    
    Tries multiple methods:
    1. Search in servers the bot is in
    2. Check DM channels
    3. Use Discord HTTP API to fetch user info
    """
    try:
        import discord
        from discord.ext import commands
        import httpx
        
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not bot_token:
            print("❌ DISCORD_BOT_TOKEN not set in .env")
            print("   Cannot query Discord API without bot token")
            return
        
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        
        bot = commands.Bot(command_prefix="!", intents=intents)
        
        @bot.event
        async def on_ready():
            print(f"✅ Bot connected as {bot.user}")
            print(f"   Searching for user: {username}")
            print()
            
            found = False
            user_id = None
            found_name = None
            
            # First, search through all guilds the bot is in
            for guild in bot.guilds:
                try:
                    # Try to find user by username
                    member = discord.utils.get(guild.members, name=username)
                    if member:
                        user_id = member.id
                        found_name = member.name
                        found = True
                        break
                except Exception as e:
                    print(f"⚠️  Error searching in guild {guild.name}: {e}")
            
            # If not found in servers, check DM channels
            if not found:
                print("   Not found in servers, checking DM channels...")
                try:
                    print(f"   Found {len(bot.private_channels)} private channel(s)")
                    for channel in bot.private_channels:
                        if isinstance(channel, discord.DMChannel):
                            recipient = channel.recipient
                            if recipient:
                                print(f"   - DM with: {recipient.name} (ID: {recipient.id})")
                                # Check if the recipient matches the username (case-insensitive)
                                if recipient.name.lower() == username.lower():
                                    user_id = recipient.id
                                    found_name = recipient.name
                                    found = True
                                    print(f"   ✅ Match found!")
                                    break
                except Exception as e:
                    print(f"⚠️  Error checking DM channels: {e}")
            
            # If still not found, try fetching DM channels via HTTP API
            if not found:
                print("   Not found in cached channels, fetching DM channels via API...")
                try:
                    # Fetch DM channels via HTTP API (synchronous)
                    headers = {
                        "Authorization": f"Bot {bot_token}",
                        "Content-Type": "application/json"
                    }
                    with httpx.Client(timeout=10.0) as client:
                        # Get all DM channels for the bot
                        response = client.get(
                            "https://discord.com/api/v10/users/@me/channels",
                            headers=headers
                        )
                        if response.status_code == 200:
                            channels = response.json()
                            print(f"   Found {len(channels)} channel(s) via API")
                            if len(channels) == 0:
                                print("   ⚠️  No channels found. The bot may not have any DM channels yet.")
                                print("   💡 Try sending a message to the bot first to create a DM channel.")
                            for channel_data in channels:
                                if channel_data.get("type") == 1:  # DM channel (type 1)
                                    recipients = channel_data.get("recipients", [])
                                    for recipient in recipients:
                                        recipient_username = recipient.get("username", "")
                                        recipient_id = recipient.get("id", "")
                                        recipient_discriminator = recipient.get("discriminator", "")
                                        full_username = f"{recipient_username}#{recipient_discriminator}" if recipient_discriminator and recipient_discriminator != "0" else recipient_username
                                        print(f"   - DM with: {full_username} (ID: {recipient_id})")
                                        # Check if the recipient matches the username (case-insensitive)
                                        if recipient_username.lower() == username.lower():
                                            user_id = recipient_id
                                            found_name = recipient_username
                                            found = True
                                            print(f"   ✅ Match found!")
                                            break
                                    if found:
                                        break
                                elif channel_data.get("type") == 3:  # Group DM
                                    recipients = channel_data.get("recipients", [])
                                    print(f"   - Group DM with {len(recipients)} recipient(s)")
                                    for recipient in recipients:
                                        recipient_username = recipient.get("username", "")
                                        recipient_id = recipient.get("id", "")
                                        print(f"     - {recipient_username} (ID: {recipient_id})")
                                        if recipient_username.lower() == username.lower():
                                            user_id = recipient_id
                                            found_name = recipient_username
                                            found = True
                                            print(f"     ✅ Match found!")
                                            break
                                    if found:
                                        break
                        else:
                            print(f"   ⚠️  API returned status {response.status_code}")
                            try:
                                error_data = response.json()
                                print(f"   Error: {error_data}")
                            except:
                                print(f"   Error text: {response.text[:200]}")
                except Exception as e:
                    print(f"⚠️  Error fetching DM channels via API: {e}")
                    import traceback
                    traceback.print_exc()
            
            if found and user_id:
                print()
                print(f"✅ Found user: {found_name}")
                print(f"   User ID: {user_id}")
                print()
                print(f"Add this to .env:")
                print(f"DISCORD_WHITELISTED_USERS={user_id}")
            else:
                print(f"❌ Could not find user '{username}' in servers or DMs")
                print()
                print("Alternative method:")
                print("1. Enable Developer Mode in Discord:")
                print("   - Settings → Advanced → Developer Mode")
                print("2. Right-click on your username/avatar → Copy User ID")
                print("3. Add it to .env: DISCORD_WHITELISTED_USERS=<your_numeric_id>")
            
            await bot.close()
        
        print("Connecting to Discord...")
        bot.run(bot_token)
        
    except ImportError:
        print("❌ discord.py library not available")
        print("   Install it: poetry add discord.py")
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Main function."""
    print()
    print("🔍 Discord User ID Finder")
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
    
    username = os.getenv("DISCORD_AUTHORIZED_USERS", "").strip()
    if not username:
        print("❌ DISCORD_AUTHORIZED_USERS not set in .env")
        print()
        print("Usage:")
        print("  1. Set DISCORD_AUTHORIZED_USERS=your_username in .env")
        print("  2. Run this script: poetry run python scripts/get_discord_user_id.py")
        print()
        print("Or find it manually:")
        print("  1. Enable Developer Mode in Discord:")
        print("     - Settings → Advanced → Developer Mode")
        print("  2. Right-click on your username/avatar → Copy User ID")
        print("  3. Add it to .env: DISCORD_WHITELISTED_USERS=<your_numeric_id>")
        return
    
    print(f"Looking up Discord user ID for: {username}")
    print()
    get_discord_user_id_from_username(username)


if __name__ == "__main__":
    main()
