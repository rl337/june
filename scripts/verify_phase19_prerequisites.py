#!/usr/bin/env python3
"""
Verification script for Phase 19: Direct Agent-User Communication prerequisites.

This script checks all prerequisites needed for Phase 19 operational tasks:
1. Service health (Telegram, Discord, Message API, STT, TTS)
2. Environment variable configuration (whitelist, owner users)
3. USER_MESSAGES.md file accessibility
4. Message API connectivity
5. Service configuration verification

Usage:
    poetry run python scripts/verify_phase19_prerequisites.py
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import httpx
import subprocess

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configuration
JUNE_DATA_DIR = os.getenv("JUNE_DATA_DIR", "/home/rlee/june_data")
DATA_DIR = Path(os.getenv("USER_MESSAGES_DATA_DIR", f"{JUNE_DATA_DIR}/var-data"))
USER_MESSAGES_FILE = DATA_DIR / "USER_MESSAGES.md"
MESSAGE_API_URL = os.getenv("MESSAGE_API_URL", "http://localhost:8083")
TELEGRAM_HEALTH_URL = "http://localhost:8080/health"
DISCORD_HEALTH_URL = "http://localhost:8081/health"


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")


def print_check(label: str, status: bool, details: str = ""):
    """Print a check result."""
    icon = f"{Colors.GREEN}✅{Colors.RESET}" if status else f"{Colors.RED}❌{Colors.RESET}"
    print(f"{icon} {label}")
    if details:
        print(f"   {details}")


def print_warning(label: str, details: str = ""):
    """Print a warning."""
    print(f"{Colors.YELLOW}⚠️  {label}{Colors.RESET}")
    if details:
        print(f"   {details}")


def check_service_health(service_name: str, url: str) -> Tuple[bool, Optional[str]]:
    """Check if a service is healthy."""
    try:
        response = httpx.get(url, timeout=5.0)
        if response.status_code == 200:
            try:
                data = response.json()
                return True, json.dumps(data, indent=2)
            except json.JSONDecodeError:
                return True, response.text[:200]
        else:
            return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except httpx.ConnectError:
        return False, "Connection refused (service not running)"
    except httpx.TimeoutException:
        return False, "Timeout (service not responding)"
    except Exception as e:
        return False, f"Error: {str(e)}"


def check_docker_service(service_name: str) -> Tuple[bool, Optional[str]]:
    """Check if a Docker service is running."""
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json", service_name],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_root,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse JSON output
            lines = [line for line in result.stdout.strip().split("\n") if line]
            if lines:
                try:
                    data = json.loads(lines[0])
                    status = data.get("State", "unknown")
                    health = data.get("Health", "unknown")
                    return (
                        "running" in status.lower() or "up" in status.lower(),
                        f"Status: {status}, Health: {health}",
                    )
                except json.JSONDecodeError:
                    return True, "Service found"
        return False, "Service not found or not running"
    except subprocess.TimeoutExpired:
        return False, "Timeout checking service"
    except FileNotFoundError:
        return False, "docker compose command not found"
    except Exception as e:
        return False, f"Error: {str(e)}"


def check_environment_variable(var_name: str, required: bool = False) -> Tuple[bool, Optional[str]]:
    """Check if an environment variable is set."""
    value = os.getenv(var_name)
    if value:
        # Mask sensitive values
        if "TOKEN" in var_name or "KEY" in var_name:
            masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
            return True, f"Set (value: {masked})"
        else:
            return True, f"Set (value: {value})"
    else:
        if required:
            return False, "Not set (REQUIRED)"
        else:
            return False, "Not set (optional)"


def check_file_accessibility(file_path: Path) -> Tuple[bool, Optional[str]]:
    """Check if a file exists and is accessible."""
    try:
        if file_path.exists():
            stat = file_path.stat()
            size = stat.st_size
            return True, f"Exists ({size} bytes, modified: {stat.st_mtime})"
        else:
            return False, "File does not exist (will be created on first message)"
    except PermissionError:
        return False, "Permission denied"
    except Exception as e:
        return False, f"Error: {str(e)}"


def main():
    """Run all prerequisite checks."""
    print_header("Phase 19 Prerequisites Verification")
    
    all_checks_passed = True
    
    # 1. Check Docker services
    print_header("1. Docker Services Status")
    services_to_check = [
        ("telegram", "june-telegram-1"),
        ("discord", "june-discord-1"),
        ("message-api", "june-message-api"),
        ("stt", "june-stt-1"),
        ("tts", "june-tts-1"),
    ]
    
    service_status = {}
    for service_name, container_name in services_to_check:
        status, details = check_docker_service(service_name)
        service_status[service_name] = status
        print_check(f"{service_name} service", status, details)
        if not status:
            all_checks_passed = False
    
    # 2. Check service health endpoints
    print_header("2. Service Health Endpoints")
    
    if service_status.get("telegram"):
        health, details = check_service_health("Telegram", TELEGRAM_HEALTH_URL)
        print_check("Telegram health endpoint", health, details)
        if not health:
            all_checks_passed = False
    else:
        print_warning("Telegram service not running, skipping health check")
    
    if service_status.get("discord"):
        health, details = check_service_health("Discord", DISCORD_HEALTH_URL)
        print_check("Discord health endpoint", health, details)
        if not health:
            all_checks_passed = False
    else:
        print_warning("Discord service not running, skipping health check")
    
    if service_status.get("message-api"):
        health, details = check_service_health("Message API", f"{MESSAGE_API_URL}/health")
        print_check("Message API health endpoint", health, details)
        if not health:
            all_checks_passed = False
    else:
        print_warning("Message API service not running, skipping health check")
    
    # 3. Check environment variables
    print_header("3. Environment Variable Configuration")
    
    env_vars_to_check = [
        ("TELEGRAM_BOT_TOKEN", True),
        ("TELEGRAM_WHITELISTED_USERS", False),
        ("TELEGRAM_OWNER_USERS", False),
        ("DISCORD_BOT_TOKEN", False),
        ("DISCORD_WHITELISTED_USERS", False),
        ("DISCORD_OWNER_USERS", False),
        ("MESSAGE_API_URL", False),
    ]
    
    for var_name, required in env_vars_to_check:
        status, details = check_environment_variable(var_name, required)
        if required:
            print_check(f"{var_name}", status, details)
            if not status:
                all_checks_passed = False
        else:
            if status:
                print_check(f"{var_name}", status, details)
            else:
                print_warning(f"{var_name}", details)
    
    # 4. Check USER_MESSAGES.md file
    print_header("4. USER_MESSAGES.md File")
    
    file_status, file_details = check_file_accessibility(USER_MESSAGES_FILE)
    print_check("USER_MESSAGES.md file", file_status, file_details)
    
    if file_status:
        try:
            content = USER_MESSAGES_FILE.read_text()
            lines = content.split("\n")
            message_count = content.count("## [")
            print(f"   File contains {message_count} message entries")
            print(f"   File has {len(lines)} lines")
        except Exception as e:
            print_warning(f"Could not read file contents: {e}")
    
    # 5. Check Message API connectivity
    print_header("5. Message API Connectivity")
    
    if service_status.get("message-api"):
        try:
            # Try to list messages
            response = httpx.get(f"{MESSAGE_API_URL}/messages", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                message_count = len(data.get("messages", []))
                total = data.get("total", 0)
                print_check("Message API list endpoint", True, f"Connected ({message_count} messages, {total} total)")
            elif response.status_code == 404:
                # 404 might mean endpoint doesn't exist or service not fully initialized
                print_warning("Message API list endpoint", f"HTTP 404 - Endpoint may not be available yet")
            else:
                print_warning("Message API list endpoint", f"HTTP {response.status_code}: {response.text[:200]}")
        except httpx.ConnectError:
            print_check("Message API list endpoint", False, "Connection refused")
            all_checks_passed = False
        except Exception as e:
            print_warning("Message API list endpoint", f"Error: {str(e)}")
    else:
        print_warning("Message API service not running, skipping connectivity check")
    
    # 6. Summary and recommendations
    print_header("Summary")
    
    if all_checks_passed:
        print(f"{Colors.GREEN}✅ All critical checks passed!{Colors.RESET}")
        print("\nYou are ready to proceed with Phase 19 operational tasks:")
        print("  1. Test end-to-end communication")
        print("  2. Verify message syncing and polling")
        print("  3. Test message grouping and editing")
    else:
        print(f"{Colors.YELLOW}⚠️  Some checks failed or warnings were found.{Colors.RESET}")
        print("\nPlease address the issues above before proceeding with Phase 19 operational tasks.")
        print("\nCommon fixes:")
        print("  - Start services: docker compose up -d")
        print("  - Configure whitelist in .env file:")
        print("    TELEGRAM_WHITELISTED_USERS=user_id1,user_id2")
        print("    TELEGRAM_OWNER_USERS=user_id1")
        print("  - Ensure Message API is running: docker compose up -d message-api")
    
    print("\nFor detailed setup instructions, see:")
    print("  - scripts/setup_phase19_operational.sh")
    print("  - docs/OPERATIONAL_READINESS.md")
    
    return 0 if all_checks_passed else 1


if __name__ == "__main__":
    sys.exit(main())
