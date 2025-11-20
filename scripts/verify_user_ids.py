#!/usr/bin/env python3
"""
Verify Telegram and Discord User IDs

This script helps verify that the user IDs in .env are correct for direct agent-user communication.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def verify_telegram_id():
    """Verify Telegram user ID."""
    print("=" * 60)
    print("Telegram User ID Verification")
    print("=" * 60)
    
    telegram_id = os.getenv("TELEGRAM_WHITELISTED_USERS", "").strip()
    if not telegram_id:
        print("❌ TELEGRAM_WHITELISTED_USERS not set in .env")
        return False
    
    # Check if it's in docker-compose.yml default
    docker_compose_path = project_root / "docker-compose.yml"
    if docker_compose_path.exists():
        content = docker_compose_path.read_text()
        if telegram_id in content:
            print(f"✅ Telegram ID {telegram_id} found in docker-compose.yml")
            print(f"   This ID is configured as the default for TELEGRAM_AUTHORIZED_USERS")
        else:
            print(f"⚠️  Telegram ID {telegram_id} not found in docker-compose.yml")
    
    print(f"📱 Telegram User ID: {telegram_id}")
    print(f"   This should be your personal Telegram account ID")
    print()
    return True


def verify_discord_id():
    """Verify Discord user ID."""
    print("=" * 60)
    print("Discord User ID Verification")
    print("=" * 60)
    
    discord_id = os.getenv("DISCORD_WHITELISTED_USERS", "").strip()
    discord_username = os.getenv("DISCORD_AUTHORIZED_USERS", "").strip()
    
    if not discord_id:
        print("❌ DISCORD_WHITELISTED_USERS not set in .env")
        print()
        print("To find your Discord user ID:")
        print("1. Enable Developer Mode in Discord:")
        print("   - Settings → Advanced → Developer Mode")
        print("2. Right-click on your username/avatar → Copy User ID")
        print("3. Add it to .env: DISCORD_WHITELISTED_USERS=<your_numeric_id>")
        print()
        if discord_username:
            print(f"   Note: You currently have username '{discord_username}' in DISCORD_AUTHORIZED_USERS")
            print(f"   But we need the numeric user ID (usually 17-18 digits), not the username")
        return False
    
    print(f"✅ Discord User ID found: {discord_id}")
    print(f"   This should be your personal Discord account ID (numeric, 17-18 digits)")
    
    # Validate format (Discord IDs are typically 17-18 digits)
    if not discord_id.isdigit():
        print(f"⚠️  Warning: Discord ID should be numeric, but got: {discord_id}")
    elif len(discord_id) < 17 or len(discord_id) > 19:
        print(f"⚠️  Warning: Discord IDs are typically 17-18 digits, but got {len(discord_id)} digits")
    else:
        print(f"✅ Discord ID format looks correct ({len(discord_id)} digits)")
    
    print()
    return True


def main():
    """Main verification function."""
    print()
    print("🔍 Verifying User IDs for Direct Agent-User Communication")
    print()
    
    # Load .env file if it exists
    env_path = project_root / ".env"
    if env_path.exists():
        print(f"📄 Loading environment from {env_path}")
        # Simple .env parser (doesn't handle all edge cases, but works for our use)
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
        print()
    else:
        print(f"⚠️  .env file not found at {env_path}")
        print("   Make sure you've created .env from .env.example")
        print()
    
    telegram_ok = verify_telegram_id()
    discord_ok = verify_discord_id()
    
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    if telegram_ok and discord_ok:
        print("✅ Both Telegram and Discord user IDs are configured")
        print()
        print("These IDs will be used for direct agent-user communication:")
        print(f"  - Telegram: {os.getenv('TELEGRAM_WHITELISTED_USERS', 'NOT SET')}")
        print(f"  - Discord: {os.getenv('DISCORD_WHITELISTED_USERS', 'NOT SET')}")
        print()
        print("⚠️  IMPORTANT: These are your personal account IDs.")
        print("   Make sure they are correct before enabling the services.")
    else:
        print("❌ Some user IDs are missing or incorrect")
        print("   Please verify and update .env file")
    print()


if __name__ == "__main__":
    main()
