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
    
    Note: This requires the bot to be in a server with the user.
    """
    try:
        import discord
        from discord.ext import commands
        
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not bot_token:
            print("❌ DISCORD_BOT_TOKEN not set in .env")
            print("   Cannot query Discord API without bot token")
            return
        
        intents = discord.Intents.default()
        intents.members = True
        
        bot = commands.Bot(command_prefix="!", intents=intents)
        
        @bot.event
        async def on_ready():
            print(f"✅ Bot connected as {bot.user}")
            print(f"   Searching for user: {username}")
            print()
            
            # Search through all guilds the bot is in
            found = False
            for guild in bot.guilds:
                try:
                    # Try to find user by username
                    member = discord.utils.get(guild.members, name=username)
                    if member:
                        print(f"✅ Found user: {member.name}")
                        print(f"   User ID: {member.id}")
                        print(f"   Display Name: {member.display_name}")
                        print()
                        print(f"Add this to .env:")
                        print(f"DISCORD_WHITELISTED_USERS={member.id}")
                        found = True
                        break
                except Exception as e:
                    print(f"⚠️  Error searching in guild {guild.name}: {e}")
            
            if not found:
                print(f"❌ Could not find user '{username}' in any server the bot is in")
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
