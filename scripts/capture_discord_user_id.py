#!/usr/bin/env python3
"""
Capture Discord User ID from Next Message

This script connects to Discord and waits for the next message to capture the user ID.
Run this, then send a message to the bot in Discord.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def capture_user_id():
    """Capture user ID from next Discord message."""
    try:
        import discord
        from discord.ext import commands
        
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not bot_token:
            print("❌ DISCORD_BOT_TOKEN not set in .env")
            return
        
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        bot = commands.Bot(command_prefix="!", intents=intents)
        
        user_id_captured = False
        
        @bot.event
        async def on_ready():
            print(f"✅ Bot connected as {bot.user}")
            print()
            print("📱 Waiting for a message in Discord...")
            print("   Please send a message to the bot now.")
            print("   (The script will exit after capturing your user ID)")
            print()
            
            # Also check existing DM channels
            if bot.private_channels:
                print(f"   Found {len(bot.private_channels)} cached DM channel(s):")
                for channel in bot.private_channels:
                    if isinstance(channel, discord.DMChannel) and channel.recipient:
                        print(f"   - {channel.recipient.name} (ID: {channel.recipient.id})")
                        if channel.recipient.name.lower() == "morntheluriang".lower():
                            nonlocal user_id_captured
                            user_id_captured = True
                            print()
                            print("=" * 60)
                            print("✅ Found user ID from cached channel!")
                            print("=" * 60)
                            print(f"   Username: {channel.recipient.name}")
                            print(f"   User ID: {channel.recipient.id}")
                            print()
                            print(f"Add this to .env:")
                            print(f"DISCORD_WHITELISTED_USERS={channel.recipient.id}")
                            print()
                            print("=" * 60)
                            await bot.close()
                            return
        
        @bot.event
        async def on_message(message):
            # Ignore bot's own messages
            if message.author == bot.user:
                return
            
            # Only process DMs
            if isinstance(message.channel, discord.DMChannel):
                user_id = message.author.id
                username = message.author.name
                
                print()
                print("=" * 60)
                print("✅ Message received!")
                print("=" * 60)
                print(f"   Username: {username}")
                print(f"   User ID: {user_id}")
                print()
                print(f"Add this to .env:")
                print(f"DISCORD_WHITELISTED_USERS={user_id}")
                print()
                print("=" * 60)
                
                nonlocal user_id_captured
                user_id_captured = True
                await bot.close()
        
        print("Connecting to Discord...")
        try:
            bot.run(bot_token)
        except KeyboardInterrupt:
            if not user_id_captured:
                print("\n\n⚠️  Cancelled - user ID not captured")
        
    except ImportError:
        print("❌ discord.py library not available")
        print("   Install it: poetry add discord.py")
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main function."""
    print()
    print("🔍 Discord User ID Capture")
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
    
    capture_user_id()


if __name__ == "__main__":
    main()
