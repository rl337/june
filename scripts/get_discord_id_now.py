#!/usr/bin/env python3
"""Quick script to get Discord user ID from next message."""
import os
import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

env_path = project_root / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

import discord

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = discord.Client(intents=intents)
user_id_captured = None

@bot.event
async def on_ready():
    print(f"✅ Bot connected: {bot.user}")
    print("📱 Waiting for your message...")
    print("   (Send a message to the bot in Discord now)")
    print()

@bot.event
async def on_message(message):
    global user_id_captured
    
    # Ignore bot's own messages
    if message.author == bot.user:
        return
    
    # Only process DMs
    if isinstance(message.channel, discord.DMChannel):
        user_id_captured = str(message.author.id)
        username = message.author.name
        
        print("=" * 60)
        print("✅ MESSAGE RECEIVED!")
        print("=" * 60)
        print(f"Username: {username}")
        print(f"User ID: {user_id_captured}")
        print()
        print("Add to .env:")
        print(f"DISCORD_WHITELISTED_USERS={user_id_captured}")
        print("=" * 60)
        
        await bot.close()

if __name__ == "__main__":
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token:
        print("❌ DISCORD_BOT_TOKEN not set")
        sys.exit(1)
    
    try:
        bot.run(bot_token)
        if user_id_captured:
            print(f"\n✅ Captured User ID: {user_id_captured}")
        else:
            print("\n⚠️  No message received - user ID not captured")
    except KeyboardInterrupt:
        print("\n⚠️  Cancelled")
